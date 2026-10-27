"""
project_export.py — FastAPI router that exports projects as .zip archives.

Endpoints (mounted under /api/projects):
- GET /{project_id}/export.zip   one project -> "<name>.zip", every file under a single
                                 top-level folder named after the project.
- GET /export-all.zip            every project the caller can access -> "overbranch-projects.zip",
                                 one top-level folder per project (a Prism-style multi-project
                                 archive: POST /import-zip re-imports it as N projects).

Access control is exactly get-file's: project_storage.verify_project_access (owner / member /
guest-of-project), so a non-member gets 403.

What goes in a project's folder:
- every real file under uploads/projects/<id>, at its project-relative path;
- DB-only text rows (latex_documents rows with no copy on disk);
- NOT "[Binary Asset: …]" placeholder rows (the bytes are gone), NOT the internal main-document
  marker, NOT VCS / OS junk (the same filter the importer applies);
- the template .cls/.sty (and similar) files the compiler would inject for this project
  (compiler.find_matched_template_roots), so the zip also compiles on Overleaf.

Before reading anything, the project's live collab room is flushed to disk (the same helper
/api/compile uses) so unsaved edits are exported.

The archive is built into a SpooledTemporaryFile (memory up to SPOOL_MEMORY_BYTES, then disk) and
streamed to the client in chunks.
"""

import asyncio
import logging
import os
import re
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterator, List, Optional, Tuple
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

import project_storage
from auth import get_current_user_or_guest
from rate_limiter import RateLimiter
from routes.project_import import _NOISE_PARTS

logger = logging.getLogger("project_export")

router = APIRouter(tags=["project_export"])

SPOOL_MEMORY_BYTES = 16 * 1024 * 1024
CHUNK_BYTES = 256 * 1024
FLUSH_TIMEOUT_SECONDS = 2.0

_rate_limit = RateLimiter(times=30, seconds=60, key_prefix="rl_export")

# Template files worth shipping unconditionally; anything else from a matched template (images,
# included .tex) only when the project's text mentions it by name.
_TEMPLATE_STYLE_EXTS = {".cls", ".sty", ".clo", ".bst", ".def", ".cfg", ".fd", ".ldf", ".bbx", ".cbx", ".lbx"}
_TEMPLATE_SKIP_NAMES = {"main.tex", "metadata.json", "thumbnail.png"}
_COMPRESSED_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".zip", ".gz", ".7z", ".woff", ".woff2"}
_BINARY_PLACEHOLDER = "[Binary Asset:"


# ---------------------------------------------------------------------------
# Naming
# ---------------------------------------------------------------------------

def safe_name(name: Optional[str], fallback: str = "project") -> str:
    """A folder / file name safe on every OS (unicode is kept)."""
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name or "").strip(" .")
    return cleaned[:80].strip(" .") or fallback


def _unique(name: str, taken: set) -> str:
    candidate, n = name, 2
    while candidate.lower() in taken:
        candidate = f"{name} ({n})"
        n += 1
    taken.add(candidate.lower())
    return candidate


def _content_disposition(filename: str) -> str:
    ascii_name = re.sub(r"[^\x20-\x7E]", "_", filename).replace('"', "'")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename, safe='')}"


# ---------------------------------------------------------------------------
# Collab flush
# ---------------------------------------------------------------------------

async def _flush_collab_room(project_id: str) -> None:
    """
    Persist the project's live collab room before reading its files. Reuses main.py's
    /api/compile helper when the app module is loaded (it is, in the real server); the
    fallback is the same logic so a router mounted on its own (tests) behaves alike.
    Never raises.
    """
    main_mod = sys.modules.get("main")
    helper = getattr(main_mod, "_flush_collab_room_before_compile", None)
    if helper is not None:
        await helper(project_id)
        return
    try:
        from collab import config as collab_config, room_manager

        if not collab_config.enabled:
            return
        room = room_manager.get(project_id)
        if room is None:
            return
        await asyncio.wait_for(asyncio.shield(room.flush()), timeout=FLUSH_TIMEOUT_SECONDS)
    except Exception as e:  # incl. asyncio.TimeoutError: export what is on disk
        logger.warning("collab flush before export of %s skipped: %r", project_id, e)


# ---------------------------------------------------------------------------
# Single-project builder
# ---------------------------------------------------------------------------

def _is_noise(rel: str) -> bool:
    parts = [p for p in PurePosixPath(rel).parts if p not in ("", ".")]
    return any(p in _NOISE_PARTS or p.startswith("._") for p in parts)


def _clean_rel(rel: str) -> Optional[str]:
    """Normalised project-relative path, or None when it is unsafe or empty."""
    if not rel or "\x00" in rel:
        return None
    p = PurePosixPath(rel.replace("\\", "/"))
    if p.is_absolute() or any(part == ".." for part in p.parts):
        return None
    parts = [x for x in p.parts if x not in ("", ".")]
    if not parts or re.fullmatch(r"[A-Za-z]:", parts[0]):
        return None
    return PurePosixPath(*parts).as_posix()


def _db_rows(sb, project_id: str) -> List[Dict[str, Any]]:
    if sb is None:
        return []
    try:
        res = sb.table("latex_documents").select("file_path, raw_code").eq("project_id", project_id).execute()
        return list(res.data or [])
    except Exception as e:
        logger.warning("export: latex_documents query for %s failed: %s", project_id, e)
        return []


def _template_extras(existing: Dict[str, Any], text_by_rel: Dict[str, str]) -> List[Tuple[str, Path]]:
    """
    Template assets the compiler would inject for this project and the project does not
    already hold: [(project-relative path, source file)].
    """
    try:
        import compiler
        corpus = "\n".join(text_by_rel.values())
        roots = compiler.find_matched_template_roots(corpus)
    except Exception as e:
        logger.warning("export: template asset lookup unavailable: %s", e)
        return []
    out: List[Tuple[str, Path]] = []
    for root in roots:
        for f in sorted(root.rglob("*")):
            if not f.is_file() or f.name in _TEMPLATE_SKIP_NAMES:
                continue
            rel = f.relative_to(root).as_posix()
            if rel == "main.tex" or rel in existing or _is_noise(rel):
                continue
            if f.suffix.lower() not in _TEMPLATE_STYLE_EXTS and f.name not in corpus and f.stem not in corpus:
                continue  # an image / chapter of the template the project never mentions
            existing[rel] = f
            out.append((rel, f))
    return out


def add_project_to_zip(zf: zipfile.ZipFile, project_id: str, top: str, sb=None) -> int:
    """Writes one project into ``zf`` under the folder ``top``. Returns the number of files."""
    disk: Dict[str, Path] = {}
    root = project_storage.project_dir(project_id)
    if root.is_dir():
        for path in sorted(root.rglob("*")):
            if path.is_symlink() or not path.is_file():
                continue
            rel = _clean_rel(path.relative_to(root).as_posix())
            if rel is None or _is_noise(rel):
                continue
            disk[rel] = path

    db_text: Dict[str, str] = {}
    for row in _db_rows(sb, project_id):
        rel = _clean_rel(row.get("file_path") or "")
        if rel is None or rel in disk or _is_noise(rel):
            continue
        code = row.get("raw_code")
        if code is None:
            code = ""
        if code.startswith(_BINARY_PLACEHOLDER):
            continue  # bytes are gone; a placeholder string would be a corrupt "image"
        db_text[rel] = code

    text_by_rel: Dict[str, str] = dict(db_text)
    for rel, path in disk.items():
        if rel.lower().endswith((".tex", ".sty", ".cls", ".bib")):
            try:
                text_by_rel[rel] = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                pass
    known: Dict[str, Any] = {**disk, **db_text}
    extras = _template_extras(known, text_by_rel)

    count = 0
    for rel, path in {**disk, **dict(extras)}.items():
        method = zipfile.ZIP_STORED if path.suffix.lower() in _COMPRESSED_EXTS else zipfile.ZIP_DEFLATED
        try:
            zf.write(path, f"{top}/{rel}", compress_type=method)
            count += 1
        except OSError as e:
            logger.warning("export: could not add %s: %s", rel, e)
    for rel, code in db_text.items():
        zf.writestr(f"{top}/{rel}", code.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
        count += 1
    if count == 0:
        zf.writestr(zipfile.ZipInfo(f"{top}/"), b"")  # keep an empty project a valid archive
    return count


def build_zip(entries: List[Tuple[str, str]], sb=None) -> tempfile.SpooledTemporaryFile:
    """[(project_id, top-level folder)] -> a SpooledTemporaryFile rewound to the start."""
    tmp = tempfile.SpooledTemporaryFile(max_size=SPOOL_MEMORY_BYTES)
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            for project_id, top in entries:
                add_project_to_zip(zf, project_id, top, sb)
        tmp.seek(0)
        return tmp
    except BaseException:
        tmp.close()
        raise


def _stream(tmp) -> Iterator[bytes]:
    try:
        while True:
            chunk = tmp.read(CHUNK_BYTES)
            if not chunk:
                break
            yield chunk
    finally:
        tmp.close()


def _zip_response(tmp, filename: str) -> StreamingResponse:
    tmp.seek(0, os.SEEK_END)
    size = tmp.tell()
    tmp.seek(0)
    return StreamingResponse(
        _stream(tmp),
        media_type="application/zip",
        headers={
            "Content-Disposition": _content_disposition(filename),
            "Content-Length": str(size),
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


# ---------------------------------------------------------------------------
# Supabase lookups
# ---------------------------------------------------------------------------

def _supabase():
    return project_storage.get_supabase_client()  # raises like get-file when unconfigured


def _project_name(sb, project_id: str) -> str:
    try:
        res = sb.table("projects").select("name").eq("id", project_id).limit(1).execute()
        rows = res.data or []
        if rows and rows[0].get("name"):
            return str(rows[0]["name"])
    except Exception as e:
        logger.warning("export: project name lookup for %s failed: %s", project_id, e)
    return "project"


def list_accessible_projects(sb, auth: Dict[str, Any]) -> List[Dict[str, str]]:
    """[{id, name}] of every project the caller owns, belongs to, or (guest) created."""
    user_id = auth.get("user_id")
    if not user_id:
        return []
    ids: List[str] = []

    def collect(table: str, column: str, value: str, id_col: str):
        try:
            res = sb.table(table).select(id_col).eq(column, value).execute()
            for row in res.data or []:
                pid = row.get(id_col)
                if pid and pid not in ids:
                    ids.append(pid)
        except Exception as e:
            logger.warning("export-all: %s lookup failed: %s", table, e)

    if auth.get("is_guest") or str(user_id).startswith("guest"):
        sess = auth.get("session_id") or str(user_id).replace("guest_", "").replace("guest-", "")
        collect("guest_projects", "guest_session_id", sess, "project_id")
    else:
        collect("projects", "owner_id", user_id, "id")
        collect("project_members", "user_id", user_id, "project_id")

    out: List[Dict[str, str]] = []
    for pid in ids:
        try:
            res = sb.table("projects").select("id, name").eq("id", pid).limit(1).execute()
            rows = res.data or []
        except Exception as e:
            logger.warning("export-all: project row %s lookup failed: %s", pid, e)
            rows = []
        if rows:
            out.append({"id": pid, "name": str(rows[0].get("name") or "project")})
    return out


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/export-all.zip", dependencies=[Depends(_rate_limit)])
async def export_all_projects(auth: Dict[str, Any] = Depends(get_current_user_or_guest)):
    sb = _supabase()
    projects = await asyncio.to_thread(list_accessible_projects, sb, auth)
    if not projects:
        raise HTTPException(status_code=404, detail="No projects to export.")

    taken: set = set()
    entries: List[Tuple[str, str]] = []
    for p in projects:
        await _flush_collab_room(p["id"])
        entries.append((p["id"], _unique(safe_name(p["name"]), taken)))

    tmp = await asyncio.to_thread(build_zip, entries, sb)
    return _zip_response(tmp, "overbranch-projects.zip")


@router.get("/{project_id}/export.zip", dependencies=[Depends(_rate_limit)])
async def export_project(project_id: str, auth: Dict[str, Any] = Depends(get_current_user_or_guest)):
    sb = _supabase()
    # Same gate as get-file: 403 for anyone who is not owner / member / the guest creator.
    await asyncio.to_thread(
        project_storage.verify_project_access, sb, project_id, auth.get("user_id"),
        bool(auth.get("is_guest")))

    await _flush_collab_room(project_id)

    name = await asyncio.to_thread(_project_name, sb, project_id)
    folder = safe_name(name)
    tmp = await asyncio.to_thread(build_zip, [(project_id, folder)], sb)

    # Nothing at all (unknown project id): the placeholder-only archive is not an export.
    with zipfile.ZipFile(tmp) as probe:
        empty = all(n.endswith("/") for n in probe.namelist())
    if empty:
        tmp.close()
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' has no files to export.")
    tmp.seek(0)
    return _zip_response(tmp, f"{folder}.zip")
