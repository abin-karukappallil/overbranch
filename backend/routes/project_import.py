"""
project_import.py — FastAPI router that turns an uploaded .zip of LaTeX sources into a NEW project.

Endpoint:
- POST /api/projects/import-zip   multipart (file, project_name?) ->
      {project_id, name, files_count, assets_count, main_file, main_tex_path, created_main_tex,
       projects: [{project_id, name, files_count, assets_count, main_file, main_tex_path,
                   created_main_tex, folder}]}
  The top-level fields describe the FIRST project (back-compat). An archive holding several
  projects (Prism exports one per top-level folder) creates one project per folder; every
  one of them is in ``projects``.

Files keep their archived paths (a main document in a sub-folder is NOT moved to the root:
that broke its relative \input / \includegraphics / \bibliography paths). The main
document is detected and recorded as the project's main document (projects.default_branch
+ an on-disk marker, see project_storage.set_main_document). Dotfiles such as .latexmkrc
are stored (never executed); only VCS / OS junk is dropped.

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
# Path parts that are VCS / OS junk, never project content.
_NOISE_PARTS = {"__MACOSX", ".git", ".svn", ".hg", ".DS_Store", "Thumbs.db", "desktop.ini",
                ".Trashes", ".Spotlight-V100", ".fseventsd", ".idea", ".vscode",
                project_storage.MAIN_MARKER}


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
        if any(x in _NOISE_PARTS or x.startswith("._") for x in parts):
            logger.info("zip import: skipping VCS/OS junk member %r", zi.filename)
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

def _member_head(zf: zipfile.ZipFile, zi: zipfile.ZipInfo) -> str:
    with zf.open(zi) as fh:
        return fh.read(project_storage.MAIN_SCAN_BYTES).decode("utf-8", errors="ignore")


def detect_main(zf: zipfile.ZipFile, members: List[Tuple[zipfile.ZipInfo, str]]) -> Optional[str]:
    """The main document of one project's members (see project_storage.detect_main_document)."""
    by_rel = {rel: zi for zi, rel in members}
    return project_storage.detect_main_document(lambda rel: _member_head(zf, by_rel[rel]), list(by_rel))


def split_projects(zf: zipfile.ZipFile, members: List[Tuple[zipfile.ZipInfo, str]]
                   ) -> List[Tuple[Optional[str], List[Tuple[zipfile.ZipInfo, str]]]]:
    """
    [(folder, members relative to that folder)]. An archive with no loose root files
    and two or more top-level folders that EACH hold their own main document is
    several projects (a Prism multi-project export); anything else is one project
    ``[(None, members)]``.
    """
    if any("/" not in rel for _, rel in members):
        return [(None, members)]
    groups: Dict[str, List[Tuple[zipfile.ZipInfo, str]]] = {}
    for zi, rel in members:
        top, rest = rel.split("/", 1)
        groups.setdefault(top, []).append((zi, rest))
    if len(groups) < 2:
        return [(None, members)]
    for sub in groups.values():
        if detect_main(zf, sub) is None:
            return [(None, members)]
    return [(name, groups[name]) for name in sorted(groups)]


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

    # Every file stays at its archived path; the main document is only RECORDED.
    created_main = False
    main_rel = detect_main(zf, members)
    main_dest = project_storage.get_project_disk_path(project_id, project_storage.DEFAULT_MAIN_DOCUMENT)
    if main_rel is None:
        main_rel = project_storage.DEFAULT_MAIN_DOCUMENT
        if project_storage.DEFAULT_MAIN_DOCUMENT not in disk_paths:
            # Nothing compilable in the archive: keep the empty main.tex seeded by
            # create_empty_project so the editor has a document to open.
            main_dest.parent.mkdir(parents=True, exist_ok=True)
            if not main_dest.exists():
                main_dest.write_text("", encoding="utf-8")
            if sb is not None:
                project_storage.upsert_latex_document(sb, project_id, project_storage.DEFAULT_MAIN_DOCUMENT, "")
            created_main = True
            files += 1
    elif project_storage.DEFAULT_MAIN_DOCUMENT not in disk_paths:
        # create_empty_project seeded an empty root main.tex; the real main document is
        # elsewhere, so the stray placeholder goes.
        try:
            if main_dest.is_file() and main_dest.stat().st_size == 0:
                main_dest.unlink()
        except OSError as e:
            logger.warning("could not remove seeded main.tex for %s: %s", project_id, e)
    project_storage.set_main_document(project_id, main_rel, sb=sb)
    return {"files_count": files, "assets_count": assets, "main_file": main_rel,
            "main_tex_path": main_rel, "created_main_tex": created_main}


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
    created: List[Dict[str, Any]] = []
    sb = None
    try:
        owner_id: str = auth["user_id"]
        guest_session_id = auth.get("session_id") if auth.get("is_guest") else None
        name_hint = (project_name or "").strip() or Path(filename).stem

        groups = await asyncio.to_thread(split_projects, zf, members)
        multi = len(groups) > 1
        sb = _supabase()
        for folder, group_members in groups:
            hint = folder if multi and folder else name_hint
            project = await asyncio.to_thread(
                project_storage.create_empty_project, owner_id, hint, guest_session_id, "ZIP Import")
            project_id = project["project_id"]
            created.append({"project_id": project_id, "name": project["name"], "folder": folder})
            result = await asyncio.to_thread(_extract, zf, group_members, project_id, sb)
            created[-1].update(result)
    except BaseException as e:
        if created:
            logger.exception("zip import failed; rolling back %d project(s)", len(created))
            for entry in created:
                await asyncio.to_thread(_rollback, entry["project_id"], sb)
        if isinstance(e, HTTPException) and not created:
            raise
        if isinstance(e, (KeyboardInterrupt, SystemExit, asyncio.CancelledError)):
            raise
        # The code is the contract with the client; the cause stays in the server log.
        raise HTTPException(status_code=500, detail="extract-failed")
    finally:
        zf.close()
    first = created[0]
    return {**{k: v for k, v in first.items() if k != "folder"}, "projects": created,
            "projects_count": len(created)}
