import os
import re
import uuid
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Request, HTTPException, status, UploadFile, File, Form, Depends
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from supabase import create_client, Client
from auth import get_current_user_or_guest, verify_project_ownership_or_member
from rate_limiter import RateLimiter

load_dotenv()

logger = logging.getLogger("project_storage")
logging.basicConfig(level=logging.INFO)

router = APIRouter()

UPLOADS_BASE_DIR = Path(os.getenv("UPLOADS_BASE_DIR", os.path.join(os.path.dirname(__file__), "..", "uploads", "projects"))).resolve()


class SaveDocumentRequest(BaseModel):
    project_id: str = Field(..., description="Project ID or UUID")
    file_path: str = Field(..., description="Path of the file relative to project root (e.g. main.tex)")
    raw_code: str = Field(..., description="LaTeX code or text content")
    user_id: Optional[str] = Field(None, description="Requesting User ID for authorization check")


def verify_project_access(supabase: Client, project_id: str, user_id: Optional[str] = None, is_guest: bool = False):
    """Verifies that project exists and user is owner or member."""
    if not project_id or not user_id:
        return
    verify_project_ownership_or_member(supabase, project_id, user_id, is_guest=is_guest)


def get_project_disk_path(project_id: str, file_path: str) -> Path:
    safe_project = re.sub(r'[^a-zA-Z0-9_-]', '_', project_id)
    target_path = (UPLOADS_BASE_DIR / safe_project / file_path).resolve()
    if not str(target_path).startswith(str(UPLOADS_BASE_DIR)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path (path traversal detected)."
        )
    return target_path


# ============================================================================
# Main document (the file the project compiles)
# ============================================================================
# A project's main document is stored in `projects.default_branch` (schema
# default "main.tex"). The DB is not always reachable (disk-only/local/tests),
# so the same value is also kept on disk in a marker file next to the project's
# sources. The marker is written only by set_main_document, which writes both.

DEFAULT_MAIN_DOCUMENT = "main.tex"
MAIN_MARKER = ".obmain"

_MAIN_DOCCLASS_RE = re.compile(r"^[^%\n]*\\documentclass\s*(?:\[[^\]]*\])?\s*\{", re.MULTILINE)
_MAIN_BEGIN_DOC_RE = re.compile(r"^[^%\n]*\\begin\s*\{document\}", re.MULTILINE)
_TEX_ROOT_RE = re.compile(r"^\s*%\s*!\s*TeX\s+root\s*=\s*(\S[^\n]*?)\s*$", re.IGNORECASE | re.MULTILINE)
MAIN_SCAN_BYTES = 256 * 1024


def project_dir(project_id: str) -> Path:
    safe_project = re.sub(r'[^a-zA-Z0-9_-]', '_', project_id)
    return UPLOADS_BASE_DIR / safe_project


def _clean_rel(rel: Optional[str]) -> Optional[str]:
    """A safe project-relative POSIX path, or None."""
    if not rel:
        return None
    r = str(rel).strip().replace("\\", "/")
    while r.startswith("./"):
        r = r[2:]
    if not r or r.startswith("/") or any(p in ("..", "") for p in r.split("/")):
        return None
    return r


def is_main_document_text(head: str) -> bool:
    """An uncommented \\documentclass and \\begin{document}: a compilable root file."""
    return bool(_MAIN_DOCCLASS_RE.search(head or "") and _MAIN_BEGIN_DOC_RE.search(head or ""))


def detect_main_document(read_head, rel_paths) -> Optional[str]:
    """
    Picks a project's main document from its file paths. ``read_head(rel)``
    returns the first MAIN_SCAN_BYTES of a file as text (or None).

    1. A ``% !TeX root = …`` magic comment that points at an existing root
       document (the most-referenced one wins).
    2. A root-level main.tex that is a root document.
    3. The shallowest, then alphabetical, .tex file with an uncommented
       \\documentclass and \\begin{document} in its first 256 KB.
    4. The same, with \\documentclass alone.
    """
    tex = sorted({r for r in rel_paths if r.lower().endswith(".tex")}, key=lambda r: (r.count("/"), r))
    heads: Dict[str, str] = {}

    def head(rel: str) -> str:
        if rel not in heads:
            try:
                heads[rel] = read_head(rel) or ""
            except Exception:
                heads[rel] = ""
        return heads[rel]

    texset = set(tex)
    votes: Dict[str, int] = {}
    for rel in tex:
        m = _TEX_ROOT_RE.search("\n".join(head(rel).splitlines()[:40]))
        if not m:
            continue
        target = m.group(1).strip().strip('"').strip("'")
        if not target.lower().endswith(".tex"):
            target += ".tex"
        base = rel.rsplit("/", 1)[0] if "/" in rel else ""
        parts: List[str] = []
        for part in ((base + "/" + target) if base else target).split("/"):
            if part in ("", "."):
                continue
            if part == "..":
                if not parts:
                    parts = ["\0"]  # escapes the project
                    break
                parts.pop()
            else:
                parts.append(part)
        resolved = "/".join(parts)
        if resolved in texset and resolved != rel and is_main_document_text(head(resolved)):
            votes[resolved] = votes.get(resolved, 0) + 1
    if votes:
        return sorted(votes.items(), key=lambda kv: (-kv[1], kv[0].count("/"), kv[0]))[0][0]
    if DEFAULT_MAIN_DOCUMENT in texset and is_main_document_text(head(DEFAULT_MAIN_DOCUMENT)):
        return DEFAULT_MAIN_DOCUMENT
    for rel in tex:
        if is_main_document_text(head(rel)):
            return rel
    for rel in tex:
        if _MAIN_DOCCLASS_RE.search(head(rel)):
            return rel
    return None


def detect_main_document_in_dir(root: Path) -> Optional[str]:
    """detect_main_document over the .tex files under ``root`` on disk."""
    root = Path(root)
    rels = []
    try:
        for p in root.rglob("*.tex"):
            if p.is_file():
                rels.append(p.relative_to(root).as_posix())
    except OSError:
        return None

    def read_head(rel: str) -> str:
        with open(root / rel, "rb") as fh:
            return fh.read(MAIN_SCAN_BYTES).decode("utf-8", errors="ignore")

    return detect_main_document(read_head, rels)


def _read_marker(project_id: str) -> Optional[str]:
    try:
        marker = project_dir(project_id) / MAIN_MARKER
        if marker.is_file():
            return _clean_rel(marker.read_text(encoding="utf-8").strip())
    except Exception:
        pass
    return None


def _read_default_branch(project_id: str) -> Optional[str]:
    try:
        sb = get_supabase_client()
        res = sb.table("projects").select("default_branch").eq("id", project_id).limit(1).execute()
        rows = res.data or []
        if rows:
            return _clean_rel(rows[0].get("default_branch"))
    except Exception:
        pass
    return None


def get_main_document(project_id: str, exists=None) -> str:
    """
    The project's main document path (project-relative). Order: the on-disk
    marker, then projects.default_branch, then main.tex. ``exists(rel)``, when
    given, filters out a recorded path whose file is gone; if none of the
    recorded paths exist the project's files are scanned for a root document.
    """
    if exists is None:
        def exists(rel: str) -> bool:
            try:
                return get_project_disk_path(project_id, rel).is_file()
            except Exception:
                return False
    seen: List[str] = []
    for source in (_read_marker, _read_default_branch, lambda _pid: DEFAULT_MAIN_DOCUMENT):
        cand = source(project_id)  # lazily: the DB is only asked when the marker is absent
        if cand and cand not in seen:
            seen.append(cand)
            if exists(cand):
                return cand
    found = detect_main_document_in_dir(project_dir(project_id))
    return found or (seen[0] if seen else DEFAULT_MAIN_DOCUMENT)


def set_main_document(project_id: str, rel_path: str, sb=None) -> str:
    """
    Records ``rel_path`` as the project's main document: projects.default_branch
    (best effort) and the on-disk marker. Returns the stored path.
    """
    rel = _clean_rel(rel_path)
    if rel is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid main document path.")
    pdir = project_dir(project_id)
    marker = pdir / MAIN_MARKER
    try:
        if rel == DEFAULT_MAIN_DOCUMENT:
            if marker.exists():
                marker.unlink()
        else:
            pdir.mkdir(parents=True, exist_ok=True)
            marker.write_text(rel, encoding="utf-8")
    except OSError as e:
        logger.warning(f"Could not write main document marker for {project_id}: {e}")
    try:
        client = sb if sb is not None else get_supabase_client()
        client.table("projects").update({"default_branch": rel}).eq("id", project_id).execute()
    except Exception as e:
        logger.warning(f"Could not store default_branch for {project_id}: {e}")
    return rel


def is_main_document(project_id: str, rel_path: str) -> bool:
    rel = _clean_rel(rel_path)
    if rel is None:
        return False
    return rel.lower() == get_main_document(project_id).lower()


_supabase_client: Optional[Client] = None

def get_supabase_client() -> Client:
    """Returns a cached Supabase client singleton to prevent socket/connection leaks."""
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_KEY")
        or os.getenv("SUPABASE_ANON_KEY")
    )
    if not supabase_url or not supabase_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Supabase credentials are not configured in environment."
        )
    # Catches the "keys swapped" misconfiguration that silently degrades the
    # backend to anon access and makes every write look like it worked while
    # Supabase quietly rejects it under RLS. sb_publishable_* is the browser
    # key; the server-side client must be sb_secret_* (or a legacy JWT).
    if supabase_key.startswith("sb_publishable_"):
        logger.error(
            "SUPABASE_SERVICE_ROLE_KEY is set to a publishable (anon) key. "
            "Writes to latex_documents will be blocked by RLS. Expected an "
            "sb_secret_* key."
        )
    _supabase_client = create_client(supabase_url, supabase_key)
    return _supabase_client


def reset_supabase_client():
    """Allows resetting the client in case of connection resets or credentials rotation."""
    global _supabase_client
    _supabase_client = None


def upsert_latex_document(supabase: Client, project_id: str, file_path: str, raw_code: str):
    """Safely updates or inserts a latex_documents record without relying on DB unique constraints."""
    try:
        existing = (
            supabase.table("latex_documents")
            .select("id")
            .eq("project_id", project_id)
            .eq("file_path", file_path)
            .execute()
        )
        if existing.data and len(existing.data) > 0:
            rec_id = existing.data[0]["id"]
            supabase.table("latex_documents").update({
                "raw_code": raw_code
            }).eq("id", rec_id).execute()
        else:
            supabase.table("latex_documents").insert({
                "project_id": project_id,
                "file_path": file_path,
                "raw_code": raw_code
            }).execute()
    except Exception as e:
        logger.warning(f"Failed to upsert latex_document ({file_path}): {e}")


# Suffixes whose content is mirrored into latex_documents as text; everything else
# gets a "[Binary Asset: ...]" placeholder row (the bytes live on disk only).
TEXT_SUFFIXES = {".tex", ".sty", ".cls", ".bib", ".txt", ".md", ".bst", ".bbl", ".def", ".cfg", ".ltx", ".csv"}


def create_empty_project(owner_id: str, name_hint: str, guest_session_id: Optional[str],
                         template_tag: str) -> Dict[str, Any]:
    """
    Creates a project (and, for guests, the 24h guest_projects record) with an empty main.tex
    seeded on disk. Shared by the PDF importer ("PDF Import") and the ZIP importer ("ZIP Import").
    Degrades to disk-only when Supabase is not configured (local/tests).
    """
    kind = template_tag[: -len(" Import")] if template_tag.endswith(" Import") else template_tag
    fallback_name = f"Imported {kind}"
    project_id = str(uuid.uuid4())
    clean_name = re.sub(r"[^\w\s\-().]", "", name_hint or fallback_name).strip()[:80] or fallback_name
    slug = re.sub(r"[^a-z0-9]+", "-", clean_name.lower()).strip("-") or fallback_name.lower().replace(" ", "-")

    # Seed an empty main.tex on disk, mirroring trpc projects.createProject
    main = get_project_disk_path(project_id, "main.tex")
    main.parent.mkdir(parents=True, exist_ok=True)
    main.write_text("", encoding="utf-8")

    try:
        sb = get_supabase_client()
    except Exception as e:  # HTTPException when Supabase is not configured (local/tests)
        logger.warning(f"Supabase unavailable; writing project files to disk only: {e}")
        return {"project_id": project_id, "name": clean_name}

    if owner_id.startswith("guest_"):
        try:
            from services.guest_identity import ensure_guest_user_row
            ensure_guest_user_row(sb, owner_id)
        except Exception as e:
            logger.warning(f"Could not ensure guest user row for {owner_id}: {e}")
    try:
        sb.table("projects").insert({
            "id": project_id,
            "owner_id": owner_id,
            "name": clean_name,
            "description": f"Imported from {kind}",
            "repository": f"prostack/{slug}",
            "default_branch": "main.tex",
            "language": "latex",
            "status": "active",
            "is_public": False,
            "is_favorite": False,
            "template": template_tag,
            "stars_count": 0,
        }).execute()
        sb.table("project_members").insert({
            "id": str(uuid.uuid4()), "project_id": project_id, "user_id": owner_id, "role": "Owner",
        }).execute()
    except Exception as e:
        logger.warning(f"Project row creation failed: {e}")

    if guest_session_id:
        now = datetime.now(timezone.utc)
        try:
            sb.table("guest_projects").insert({
                "id": str(uuid.uuid4()),
                "guest_session_id": guest_session_id,
                "project_id": project_id,
                "migrated_to_user_id": None,
                "migrated_at": None,
                "expires_at": (now + timedelta(hours=24)).isoformat(),
                "created_at": now.isoformat(),
            }).execute()
        except Exception as e:
            logger.warning(f"guest_projects record failed: {e}")
    return {"project_id": project_id, "name": clean_name}


# ============================================================================
# Binary assets
# ============================================================================

def save_project_asset_bytes(project_id: str, file_path: str, content: bytes, label: Optional[str] = None) -> Path:
    """
    Writes a binary asset (image, PDF, font, class file) into the project: the
    file on local disk, plus the ``latex_documents`` row that makes it appear in
    the file tree. Shared by the upload endpoint and by the agent, which imports
    figures from attached PDFs through the same path a user upload takes.
    """
    target_path = get_project_disk_path(project_id, file_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(content)
    try:
        asset_meta = f"[Binary Asset: {label or target_path.name}, Size: {len(content)} bytes]"
        upsert_latex_document(get_supabase_client(), project_id, file_path, asset_meta)
    except Exception as db_err:  # the file on disk is what compiles; the row is only the listing
        logger.warning(f"Asset metadata DB insert warning: {db_err}")
    return target_path


def delete_project_asset(project_id: str, file_path: str) -> None:
    """Removes a binary asset from disk and from the file listing (best effort)."""
    try:
        target_path = get_project_disk_path(project_id, file_path)
        if target_path.is_file():
            target_path.unlink()
    except Exception as e:
        logger.warning(f"Could not delete asset '{file_path}': {e}")
    try:
        get_supabase_client().table("latex_documents").delete() \
            .eq("project_id", project_id).eq("file_path", file_path).execute()
    except Exception as e:
        logger.warning(f"Could not delete asset row '{file_path}': {e}")


# ============================================================================
# Reusable document read/write helpers
# ============================================================================
# These were previously inlined in the HTTP handlers. The realtime
# collaboration layer (backend/collab) persists CRDT document state through the
# exact same disk + Supabase path, so the two must not drift apart.

def write_document_text(
    project_id: str,
    file_path: str,
    raw_code: str,
    from_room: bool = False,
) -> Path:
    """
    Writes a text document to local disk and upserts it into Supabase
    `latex_documents`. Returns the disk path written.

    Supabase failures are logged and swallowed: local disk is the primary store
    (`get_project_file` reads it first), and losing the mirror must not lose the
    user's text.

    If a realtime collaboration room for this project is open, the new text is
    first applied *into* that room's CRDT (see backend/collab/inject.py), so
    everyone currently editing receives it instead of discovering later that
    their session and the database had diverged. `from_room=True` is how the
    room's own flush opts out of that round trip — it is the source of the write.
    """
    if not from_room:
        try:
            from collab.inject import inject_document_text

            inject_document_text(project_id, file_path, raw_code)
        except Exception as collab_err:
            logger.warning(f"Collaboration injection skipped for '{file_path}': {collab_err}")

    target_path = get_project_disk_path(project_id, file_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(raw_code, encoding="utf-8")

    try:
        upsert_latex_document(get_supabase_client(), project_id, file_path, raw_code)
    except Exception as db_err:
        logger.warning(f"Supabase mirror write failed for '{file_path}': {db_err}")

    return target_path


def read_document_text(project_id: str, file_path: str) -> Optional[str]:
    """
    Reads a text document, disk first then the Supabase mirror. Returns None
    when the file exists in neither — the caller decides whether that means
    "new file" or "not found".
    """
    try:
        target_path = get_project_disk_path(project_id, file_path)
    except HTTPException:
        raise
    if target_path.exists():
        try:
            return target_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as e:
            logger.warning(f"Could not read '{file_path}' from disk as text: {e}")

    try:
        res = (
            get_supabase_client()
            .table("latex_documents")
            .select("raw_code")
            .eq("project_id", project_id)
            .eq("file_path", file_path)
            .execute()
        )
        rows = res.data or []
        if rows:
            return rows[0].get("raw_code") or ""
    except Exception as e:
        logger.warning(f"Supabase read failed for '{file_path}': {e}")

    return None


@router.post(
    "/api/projects/save-file",
    dependencies=[Depends(RateLimiter(times=60, seconds=60, key_prefix="rl_save_file"))],
)
def save_project_file(
    req: SaveDocumentRequest,
    request: Request,
    auth_info: Dict[str, Any] = Depends(get_current_user_or_guest),
):
    """
    Saves LaTeX document code:
    1. Verifies server-side authorization access with token or session.
    2. Writes to local system disk storage under uploads/projects/<project_id>/<file_path>.
    3. Upserts document in Supabase latex_documents database table.
    """
    try:
        supabase = get_supabase_client()
        user_id = auth_info.get("user_id") or req.user_id
        is_guest = bool(auth_info.get("is_guest"))
        verify_project_access(supabase, req.project_id, user_id, is_guest=is_guest)

        # 1 + 2. Local disk (primary) + Supabase latex_documents mirror.
        # Shared with the realtime collaboration persister so both write the
        # document exactly the same way.
        target_path = write_document_text(req.project_id, req.file_path, req.raw_code)
        logger.info(f"Saved file to local disk: '{target_path}'")

        return {
            "success": True,
            "project_id": req.project_id,
            "file_path": req.file_path,
            "saved_to_disk": str(target_path),
            "saved_to_db": True
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving project file: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Save project file failed: {str(e)}"
        )


@router.post(
    "/api/projects/upload-asset",
    dependencies=[Depends(RateLimiter(times=30, seconds=60, key_prefix="rl_upload_asset"))],
)
async def upload_project_asset(
    request: Request,
    project_id: str = Form(...),
    file_path: str = Form(...),
    file: UploadFile = File(...),
    auth_info: Dict[str, Any] = Depends(get_current_user_or_guest),
):
    """Uploads binary assets (images, PDFs, fonts, class files) to local disk & records in DB."""
    try:
        supabase = get_supabase_client()
        user_id = auth_info.get("user_id")
        is_guest = bool(auth_info.get("is_guest"))
        verify_project_access(supabase, project_id, user_id, is_guest=is_guest)

        content = await file.read()
        target_path = save_project_asset_bytes(project_id, file_path, content, label=file.filename)
        logger.info(f"Uploaded binary asset to local disk: '{target_path}'")

        return {
            "success": True,
            "project_id": project_id,
            "file_path": file_path,
            "size_bytes": len(content),
            "saved_to_disk": str(target_path)
        }
    except Exception as e:
        logger.error(f"Error uploading asset: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Upload asset failed: {str(e)}"
        )


@router.get(
    "/api/projects/get-file",
    dependencies=[Depends(RateLimiter(times=120, seconds=60, key_prefix="rl_get_file"))],
)
def get_project_file(
    request: Request,
    project_id: str,
    file_path: str = "main.tex",
    raw: bool = False,
    download: bool = False,
    auth_info: Dict[str, Any] = Depends(get_current_user_or_guest),
):
    """
    Retrieves project file content from local disk or Supabase latex_documents table.
    Includes auto-creation fallback for main.tex when missing and main.tex is the
    project's main document.
    Returns FileResponse directly for binary assets or when raw/download is True.
    """
    supabase = get_supabase_client()
    user_id = auth_info.get("user_id")
    is_guest = bool(auth_info.get("is_guest"))
    verify_project_access(supabase, project_id, user_id, is_guest=is_guest)

    target_path = get_project_disk_path(project_id, file_path)

    binary_extensions = (
        ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".ico", ".tiff",
        ".pdf", ".zip", ".tar", ".gz", ".7z", ".rar",
        ".otf", ".ttf", ".woff", ".woff2", ".eot"
    )
    is_binary = file_path.lower().endswith(binary_extensions)

    # 1. Check local disk first
    if target_path.exists():
        if is_binary or raw or download:
            return FileResponse(target_path, filename=target_path.name)
        try:
            content = target_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return FileResponse(target_path, filename=target_path.name)
        return {
            "project_id": project_id,
            "file_path": file_path,
            "raw_code": content,
            "source": "local_disk"
        }

    # 2. Check Supabase DB
    try:
        supabase = get_supabase_client()
        res = (
            supabase.table("latex_documents")
            .select("raw_code")
            .eq("project_id", project_id)
            .eq("file_path", file_path)
            .execute()
        )
        data = res.data or []
        if data:
            raw_code = data[0].get("raw_code", "")
            # Save back to local disk
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(raw_code, encoding="utf-8")
            if raw or download or is_binary:
                return FileResponse(target_path, filename=target_path.name)
            return {
                "project_id": project_id,
                "file_path": file_path,
                "raw_code": raw_code,
                "source": "supabase_db"
            }
    except Exception as e:
        logger.warning(f"Error querying Supabase for file: {e}")

    # 3. Auto-creation fallback for main.tex if missing from disk & DB — only when
    # main.tex really is the project's main document. An imported project whose
    # main document lives elsewhere (thesis/main.tex) must not grow a stray
    # starter main.tex at the root just because something asked for it.
    if file_path == DEFAULT_MAIN_DOCUMENT and get_main_document(project_id) == DEFAULT_MAIN_DOCUMENT:
        starter_code = r"""\documentclass[12pt]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage{hyperref}

\title{LaTeX Workspace}
\author{OverBranch Author}
\date{\today}

\begin{document}

\maketitle

\section{Introduction}
Welcome to your OverBranch LaTeX document! You can start typing LaTeX equations, text, figures, and tables here.

\section{Mathematics Example}
Here is a sample equation:
\begin{equation}
E = mc^2
\end{equation}

\end{document}
"""
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(starter_code, encoding="utf-8")
        try:
            supabase = get_supabase_client()
            upsert_latex_document(supabase, project_id, file_path, starter_code)
        except Exception:
            pass

        if raw or download:
            return FileResponse(target_path, filename=target_path.name)

        return {
            "project_id": project_id,
            "file_path": file_path,
            "raw_code": starter_code,
            "source": "auto_generated"
        }

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"File '{file_path}' for project '{project_id}' not found."
    )


@router.get(
    "/api/projects/list-files",
    dependencies=[Depends(RateLimiter(times=120, seconds=60, key_prefix="rl_list_files"))],
)
def list_project_files(
    request: Request,
    project_id: str,
    auth_info: Dict[str, Any] = Depends(get_current_user_or_guest),
):
    """Lists all files and assets for a project from disk and Supabase DB."""
    supabase = get_supabase_client()
    user_id = auth_info.get("user_id")
    is_guest = bool(auth_info.get("is_guest"))
    verify_project_access(supabase, project_id, user_id, is_guest=is_guest)

    files_map: Dict[str, Dict[str, Any]] = {}

    # 1. Check local disk
    safe_project = re.sub(r'[^a-zA-Z0-9_-]', '_', project_id)
    project_dir = UPLOADS_BASE_DIR / safe_project
    if project_dir.exists():
        for path in project_dir.rglob("*"):
            if path.is_file():
                rel_path = path.relative_to(project_dir).as_posix()
                if rel_path == MAIN_MARKER:
                    continue
                ext = path.suffix.lower()
                is_img = ext in [".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"]
                files_map[rel_path] = {
                    "path": rel_path,
                    "name": path.name,
                    "size": path.stat().st_size,
                    "type": "image" if is_img else "document",
                    "ext": ext,
                }

    # 2. Query Supabase latex_documents for any DB records
    try:
        res = supabase.table("latex_documents").select("file_path").eq("project_id", project_id).execute()
        for row in res.data or []:
            f_path = row.get("file_path")
            if f_path and f_path not in files_map:
                name = os.path.basename(f_path)
                ext = os.path.splitext(name)[1].lower()
                is_img = ext in [".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"]
                files_map[f_path] = {
                    "path": f_path,
                    "name": name,
                    "size": 0,
                    "type": "image" if is_img else "document",
                    "ext": ext,
                }
    except Exception as e:
        logger.warning(f"Error fetching files list from Supabase: {e}")

    main_file = get_main_document(project_id, exists=lambda rel: rel in files_map)
    # The main document is always listed (get-file seeds a starter main.tex), but
    # a phantom main.tex is no longer added when the real main document is elsewhere.
    if main_file not in files_map:
        files_map[main_file] = {
            "path": main_file,
            "name": os.path.basename(main_file),
            "size": 0,
            "type": "document",
            "ext": os.path.splitext(main_file)[1].lower(),
        }
    for entry in files_map.values():
        entry["is_main"] = entry["path"] == main_file

    return {"project_id": project_id, "main_file": main_file, "files": list(files_map.values())}


class RenameFileRequest(BaseModel):
    project_id: str = Field(..., description="Project ID or UUID")
    old_path: str = Field(..., description="Current relative path of the file")
    new_path: str = Field(..., description="New relative path of the file")
    user_id: Optional[str] = Field(None, description="Requesting User ID for authorization check")


@router.post(
    "/api/projects/rename-file",
    dependencies=[Depends(RateLimiter(times=30, seconds=60, key_prefix="rl_rename_file"))],
)
def rename_project_file(
    req: RenameFileRequest,
    request: Request,
    auth_info: Dict[str, Any] = Depends(get_current_user_or_guest),
):
    """
    Renames a project file/asset on local disk and in Supabase DB.
    The project's main document cannot be renamed or replaced.
    """
    old_clean = req.old_path.strip()
    new_clean = req.new_path.strip()

    main_doc = get_main_document(req.project_id)
    if old_clean.lower() == main_doc.lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Primary {main_doc} file cannot be renamed."
        )
    if new_clean.lower() == main_doc.lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot rename file to {main_doc} as {main_doc} is the primary document."
        )
    if old_clean == MAIN_MARKER or new_clean == MAIN_MARKER:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reserved file name.")
    if not new_clean:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New file name cannot be empty."
        )

    supabase = get_supabase_client()
    user_id = auth_info.get("user_id") or req.user_id
    is_guest = bool(auth_info.get("is_guest"))
    verify_project_access(supabase, req.project_id, user_id, is_guest=is_guest)

    old_disk_path = get_project_disk_path(req.project_id, old_clean)
    new_disk_path = get_project_disk_path(req.project_id, new_clean)

    if not old_disk_path.exists():
        res = (
            supabase.table("latex_documents")
            .select("file_path")
            .eq("project_id", req.project_id)
            .eq("file_path", old_clean)
            .execute()
        )
        if not (res.data or []):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"File '{old_clean}' for project '{req.project_id}' not found."
            )

    new_disk_path.parent.mkdir(parents=True, exist_ok=True)
    if old_disk_path.exists():
        old_disk_path.rename(new_disk_path)
        logger.info(f"Renamed file on disk: '{old_disk_path}' -> '{new_disk_path}'")

    try:
        supabase.table("latex_documents").update({"file_path": new_clean}).eq("project_id", req.project_id).eq("file_path", old_clean).execute()
        logger.info(f"Updated file path in Supabase latex_documents from '{old_clean}' to '{new_clean}'")
    except Exception as e:
        logger.warning(f"Error updating file path in Supabase DB: {e}")

    return {
        "success": True,
        "project_id": req.project_id,
        "old_path": old_clean,
        "new_path": new_clean
    }


@router.delete(
    "/api/projects/delete-file",
    dependencies=[Depends(RateLimiter(times=30, seconds=60, key_prefix="rl_delete_file"))],
)
def delete_project_file(
    request: Request,
    project_id: str,
    file_path: str,
    auth_info: Dict[str, Any] = Depends(get_current_user_or_guest),
):
    """Deletes a file from local disk and Supabase DB."""
    main_doc = get_main_document(project_id)
    if file_path.strip().lower() == main_doc.lower():
        raise HTTPException(status_code=400, detail=f"Cannot delete primary {main_doc} document.")
    if file_path.strip() == MAIN_MARKER:
        raise HTTPException(status_code=400, detail="Reserved file name.")

    supabase = get_supabase_client()
    user_id = auth_info.get("user_id")
    is_guest = bool(auth_info.get("is_guest"))
    verify_project_access(supabase, project_id, user_id, is_guest=is_guest)

    target_path = get_project_disk_path(project_id, file_path)
    if target_path.exists():
        target_path.unlink()
        logger.info(f"Deleted file from local disk: '{target_path}'")

    try:
        supabase.table("latex_documents").delete().eq("project_id", project_id).eq("file_path", file_path).execute()
        logger.info(f"Deleted file record from Supabase DB: '{file_path}'")
    except Exception as e:
        logger.warning(f"Error deleting from Supabase DB: {e}")

    return {"success": True, "project_id": project_id, "file_path": file_path}


