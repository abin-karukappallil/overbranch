"""
project_import.py — FastAPI router that turns an uploaded .zip of LaTeX sources into a NEW project.

Endpoint:
- POST /api/projects/import-zip   multipart (file, project_name?) -> {project_id, name, files_count, ...}

Safety model (all checks run before a project row or any file exists):
- upload size cap, ZIP structure validation (BadZipFile / LargeZipFile)
- per member: encryption, symlinks, absolute / ".." / drive-letter paths, per-file size
- whole archive: member count, total uncompressed size, compression ratio (zip bombs)
- members are read one at a time with zf.read (never extractall) and written through
  project_storage.get_project_disk_path, which re-validates every destination path.

Errors are HTTPException(detail=<machine code>); the frontend maps codes to sentences.
Any failure after the project row exists rolls back the row(s) and the extracted folder.
"""

import asyncio
import io
import logging
import os
import re
import shutil
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

import project_storage
from auth import get_current_user_or_guest
from rate_limiter import RateLimiter

logger = logging.getLogger("project_import")

router = APIRouter(tags=["project_import"])

MB = 1024 * 1024
IMPORT_ZIP_MAX_MB = int(os.getenv("IMPORT_ZIP_MAX_MB", "50"))
IMPORT_ZIP_MAX_UNCOMPRESSED_MB = int(os.getenv("IMPORT_ZIP_MAX_UNCOMPRESSED_MB", "200"))
IMPORT_ZIP_MAX_FILE_MB = int(os.getenv("IMPORT_ZIP_MAX_FILE_MB", "25"))
IMPORT_ZIP_RATIO_LIMIT = int(os.getenv("IMPORT_ZIP_RATIO_LIMIT", "100"))
IMPORT_ZIP_MAX_MEMBERS = int(os.getenv("IMPORT_ZIP_MAX_MEMBERS", "5000"))
# The ratio check only applies to archives whose compressed payload exceeds this.
RATIO_MIN_COMPRESSED_BYTES = 1 * MB

IMPORTS_PER_HOUR = 10
_rate_limit = RateLimiter(times=IMPORTS_PER_HOUR, seconds=3600, key_prefix="rl_zip_import")

_SYMLINK_MODE = 0o120000
_S_IFMT = 0o170000
_DOCCLASS_RE = re.compile(r"^[^%\n]*\\documentclass", re.MULTILINE)
_NOISE_PARTS = {"__MACOSX"}


def _bad(code: str, status: int = 400) -> HTTPException:
    return HTTPException(status_code=status, detail=code)


# ---------------------------------------------------------------------------
# Member-safety pass (pure; unit-tested)
# ---------------------------------------------------------------------------

def _check_member_path(name: str) -> PurePosixPath:
    if "\x00" in name:
        raise _bad("unsafe-path")
    norm = name.replace("\\", "/")
    p = PurePosixPath(norm)
    if p.is_absolute() or any(part == ".." for part in p.parts):
        raise _bad("unsafe-path")
    if p.parts and re.fullmatch(r"[A-Za-z]:", p.parts[0]):  # Windows drive letter
        raise _bad("unsafe-path")
    return p


def analyze_archive(zf: zipfile.ZipFile) -> List[Tuple[zipfile.ZipInfo, str]]:
    """
    Validates every member and returns [(ZipInfo, project-relative path)] for the files to
    extract (directories, hidden and OS-noise members dropped, common top-level folder stripped).
    Raises HTTPException(400, <code>) on the first violation.
    """
    infos = zf.infolist()
    if len(infos) > IMPORT_ZIP_MAX_MEMBERS:
        raise _bad("too-many-files")

    max_file = IMPORT_ZIP_MAX_FILE_MB * MB
    candidates: List[Tuple[zipfile.ZipInfo, PurePosixPath]] = []
    for zi in infos:
        if zi.flag_bits & 0x1:
            raise _bad("encrypted")
        if (zi.external_attr >> 16) & _S_IFMT == _SYMLINK_MODE:
            raise _bad("unsafe-symlink")
        p = _check_member_path(zi.filename)
        if zi.file_size > max_file:
            raise _bad("file-too-large")
        if zi.is_dir():
            continue
        parts = [x for x in p.parts if x not in ("", ".")]
        if not parts:
            continue
        if any(x.startswith(".") or x in _NOISE_PARTS for x in parts):
            logger.info("zip import: skipping hidden member %r", zi.filename)
            continue
        candidates.append((zi, PurePosixPath(*parts)))

    if not candidates:
        raise _bad("empty-archive")

    total_uncompressed = sum(zi.file_size for zi, _ in candidates)
    total_compressed = sum(zi.compress_size for zi, _ in candidates)
    if total_uncompressed > IMPORT_ZIP_MAX_UNCOMPRESSED_MB * MB:
        raise _bad("too-large")
    if (total_compressed > RATIO_MIN_COMPRESSED_BYTES
            and total_uncompressed / total_compressed > IMPORT_ZIP_RATIO_LIMIT):
        raise _bad("ratio-exceeded")

    # Strip a single wrapping top-level folder ("project-name/…").
    strip = 0
    firsts = {p.parts[0] for _, p in candidates}
    if len(firsts) == 1 and all(len(p.parts) > 1 for _, p in candidates):
        strip = 1

    kept: Dict[str, zipfile.ZipInfo] = {}
    for zi, p in candidates:
        kept[PurePosixPath(*p.parts[strip:]).as_posix()] = zi  # a duplicate name: the last one wins
    return [(zi, rel) for rel, zi in kept.items()]


# ---------------------------------------------------------------------------
# Supabase helpers (all best-effort: the backend runs disk-only without Supabase)
# ---------------------------------------------------------------------------

def _supabase():
    try:
        return project_storage.get_supabase_client()
    except Exception as e:
        logger.warning("Supabase unavailable; importing to disk only: %s", e)
        return None


def _mirror(sb, project_id: str, rel: str, data: bytes) -> bool:
    """Mirrors one file into latex_documents. Returns True when it is a text file."""
    is_text = Path(rel).suffix.lower() in project_storage.TEXT_SUFFIXES
    if sb is not None:
        try:
            if is_text:
                project_storage.upsert_latex_document(sb, project_id, rel, data.decode("utf-8", errors="ignore"))
            else:
                project_storage.upsert_latex_document(
                    sb, project_id, rel, f"[Binary Asset: {Path(rel).name}, Size: {len(data)} bytes]")
        except Exception as e:
            logger.warning("DB record for %s failed: %s", rel, e)
    return is_text


def _project_dir(project_id: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", project_id)
    return project_storage.UPLOADS_BASE_DIR / safe


def _rollback(project_id: str, sb) -> None:
    shutil.rmtree(_project_dir(project_id), ignore_errors=True)
    if sb is None:
        return
    for table in ("latex_documents", "guest_projects", "project_members"):
        try:
            sb.table(table).delete().eq("project_id", project_id).execute()
        except Exception as e:
            logger.warning("rollback: deleting %s rows for %s failed: %s", table, project_id, e)
    try:
        sb.table("projects").delete().eq("id", project_id).execute()
    except Exception as e:
        logger.warning("rollback: deleting project row %s failed: %s", project_id, e)


# ---------------------------------------------------------------------------
# Extraction (sync; runs in a worker thread)
# ---------------------------------------------------------------------------

def _pick_main_candidate(disk_paths: Dict[str, Path]) -> Optional[str]:
    """A .tex with \\documentclass, preferring the shallowest path, then alphabetical."""
    tex = sorted((r for r in disk_paths if r.lower().endswith(".tex")), key=lambda r: (r.count("/"), r))
    for rel in tex:
        try:
            with open(disk_paths[rel], "rb") as fh:
                head = fh.read(256 * 1024).decode("utf-8", errors="ignore")
        except OSError:
            continue
        if _DOCCLASS_RE.search(head):
            return rel
    return None


def _extract(zf: zipfile.ZipFile, members: List[Tuple[zipfile.ZipInfo, str]], project_id: str, sb) -> Dict[str, Any]:
    files = assets = 0
    disk_paths: Dict[str, Path] = {}
    for zi, rel in members:
        data = zf.read(zi)
        dest = project_storage.get_project_disk_path(project_id, rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        disk_paths[rel] = dest
        if _mirror(sb, project_id, rel, data):
            files += 1
        else:
            assets += 1

    created_main = False
    main_dest = project_storage.get_project_disk_path(project_id, "main.tex")
    if "main.tex" not in disk_paths:
        src_rel = _pick_main_candidate(disk_paths)
        if src_rel is not None:
            os.replace(disk_paths[src_rel], main_dest)  # also overwrites the empty seeded main.tex
            text = main_dest.read_text(encoding="utf-8", errors="ignore")
            if sb is not None:
                project_storage.upsert_latex_document(sb, project_id, "main.tex", text)
                try:
                    sb.table("latex_documents").delete().eq("project_id", project_id).eq("file_path", src_rel).execute()
                except Exception as e:
                    logger.warning("could not remove old row for %s: %s", src_rel, e)
        else:
            main_dest.parent.mkdir(parents=True, exist_ok=True)
            main_dest.write_text("", encoding="utf-8")
            if sb is not None:
                project_storage.upsert_latex_document(sb, project_id, "main.tex", "")
            created_main = True
            files += 1
    return {"files_count": files, "assets_count": assets, "main_tex_path": "main.tex",
            "created_main_tex": created_main}


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

async def _read_limited(upload: UploadFile, limit: int) -> bytes:
    buf = io.BytesIO()
    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            break
        buf.write(chunk)
        if buf.tell() > limit:
            raise _bad("too-large", 413)
    return buf.getvalue()


def _open_and_analyze(data: bytes) -> Tuple[zipfile.ZipFile, List[Tuple[zipfile.ZipInfo, str]]]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, zipfile.LargeZipFile):
        raise _bad("bad-zip")
    try:
        return zf, analyze_archive(zf)
    except BaseException:
        zf.close()
        raise


@router.post("/import-zip", dependencies=[Depends(_rate_limit)])
async def import_zip(
    file: UploadFile = File(...),
    project_name: Optional[str] = Form(None),
    auth: Dict[str, Any] = Depends(get_current_user_or_guest),
):
    filename = file.filename or "project.zip"
    if not filename.lower().endswith(".zip"):
        raise _bad("bad-zip")
    data = await _read_limited(file, IMPORT_ZIP_MAX_MB * MB)

    zf, members = await asyncio.to_thread(_open_and_analyze, data)
    try:
        owner_id: str = auth["user_id"]
        guest_session_id = auth.get("session_id") if auth.get("is_guest") else None
        name_hint = (project_name or "").strip() or Path(filename).stem

        project = await asyncio.to_thread(
            project_storage.create_empty_project, owner_id, name_hint, guest_session_id, "ZIP Import")
        project_id = project["project_id"]
        sb = _supabase()
        try:
            result = await asyncio.to_thread(_extract, zf, members, project_id, sb)
        except BaseException as e:
            logger.exception("zip import %s failed; rolling back", project_id)
            await asyncio.to_thread(_rollback, project_id, sb)
            if isinstance(e, (KeyboardInterrupt, SystemExit, asyncio.CancelledError)):
                raise
            # The code is the contract with the client; the cause stays in the server log.
            raise HTTPException(status_code=500, detail="extract-failed")
    finally:
        zf.close()
    return {"project_id": project_id, "name": project["name"], **result}
