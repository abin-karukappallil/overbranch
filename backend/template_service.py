import os
import re
import json
import uuid
import shutil
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from project_storage import UPLOADS_BASE_DIR, get_supabase_client

logger = logging.getLogger("template_service")
logging.basicConfig(level=logging.INFO)

router = APIRouter()

PPT_TEMPLATES_DIR = Path(os.path.join(os.path.dirname(__file__), "templates", "ppt")).resolve()


def slugify(text: str) -> str:
    s = text.lower()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    return s.strip('-')


def discover_ppt_templates() -> List[Dict[str, Any]]:
    """
    Scans backend/templates/ppt directory for presentation templates.
    A valid template is any folder containing at least one .tex file.
    Reads optional metadata from metadata.json. If missing, auto-generates fields.
    """
    templates = []
    if not PPT_TEMPLATES_DIR.exists():
        logger.warning(f"Templates directory not found at {PPT_TEMPLATES_DIR}")
        return templates

    for item in sorted(PPT_TEMPLATES_DIR.iterdir()):
        if not item.is_dir():
            continue

        tex_files = list(item.glob("*.tex")) + list(item.glob("**/*.tex"))
        if not tex_files:
            continue

        folder_name = item.name
        auto_id = slugify(folder_name)
        
        metadata_file = item / "metadata.json"
        meta: Dict[str, Any] = {}
        if metadata_file.exists():
            try:
                meta = json.loads(metadata_file.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"Error parsing metadata.json in {item}: {e}")

        tmpl_id = meta.get("id", auto_id)
        name = meta.get("name", folder_name)
        folder_lower = folder_name.lower()
        if "report" in folder_lower:
            default_cat = "Report"
        elif "letter" in folder_lower:
            default_cat = "Letter"
        elif "resume" in folder_lower or "cv" in folder_lower:
            default_cat = "Resume"
        else:
            default_cat = "PPT"

        description = meta.get("description", "LaTeX presentation template")
        category = meta.get("category", default_cat)

        has_thumbnail = any((item / f"thumbnail.{ext}").exists() for ext in ["png", "jpg", "jpeg", "webp"])

        templates.append({
            "id": tmpl_id,
            "name": name,
            "description": description,
            "category": category,
            "path": str(item),
            "folderName": folder_name,
            "hasThumbnail": has_thumbnail,
            "thumbnail": f"/api/templates/ppt/{tmpl_id}/thumbnail",
        })

    return templates


def generate_svg_thumbnail(name: str, category: str) -> str:
    """Generates a sleek, high-contrast SVG preview thumbnail for templates without an explicit thumbnail image."""
    escaped_name = name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    escaped_category = category.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    
    words = escaped_name.split()
    line1 = name
    line2 = ""
    if len(escaped_name) > 24 and len(words) > 1:
        mid = len(words) // 2
        line1 = " ".join(words[:mid])
        line2 = " ".join(words[mid:])

    line2_svg = f'<text x="50" y="215" font-family="system-ui, -apple-system, sans-serif" font-size="22" font-weight="700" fill="#F4F4F5">{line2}</text>' if line2 else ''
    title_y = 185 if line2 else 200

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="600" height="400" viewBox="0 0 600 400" fill="none">
  <defs>
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#09090B"/>
      <stop offset="100%" stop-color="#18181B"/>
    </linearGradient>
    <pattern id="grid" width="30" height="30" patternUnits="userSpaceOnUse">
      <path d="M 30 0 L 0 0 0 30" fill="none" stroke="#27272A" stroke-width="1" stroke-opacity="0.4"/>
    </pattern>
  </defs>

  <rect width="600" height="400" fill="url(#bgGrad)"/>
  <rect width="600" height="400" fill="url(#grid)"/>

  <rect x="30" y="30" width="540" height="340" rx="16" fill="#121215" stroke="#27272A" stroke-width="2"/>
  
  <rect x="30" y="30" width="540" height="48" rx="16" fill="#18181B"/>
  <rect x="30" y="62" width="540" height="16" fill="#18181B"/>
  <line x1="30" y1="78" x2="570" y2="78" stroke="#00CC68" stroke-width="2"/>

  <rect x="50" y="45" width="110" height="20" rx="6" fill="#00CC68" fill-opacity="0.15" stroke="#00CC68" stroke-opacity="0.3"/>
  <text x="105" y="59" font-family="monospace" font-size="10" font-weight="700" fill="#00CC68" text-anchor="middle" letter-spacing="1">LaTeX BEAMER</text>

  <rect x="50" y="105" width="90" height="22" rx="6" fill="#27272A"/>
  <text x="95" y="120" font-family="monospace" font-size="11" font-weight="600" fill="#A1A1AA" text-anchor="middle">{escaped_category.upper()}</text>

  <text x="50" y="{title_y}" font-family="system-ui, -apple-system, sans-serif" font-size="24" font-weight="800" fill="#FFFFFF">{line1}</text>
  {line2_svg}

  <circle cx="58" cy="260" r="4" fill="#00CC68"/>
  <rect x="74" y="256" width="340" height="8" rx="4" fill="#27272A"/>
  
  <circle cx="58" cy="285" r="4" fill="#00CC68"/>
  <rect x="74" y="281" width="280" height="8" rx="4" fill="#27272A"/>

  <circle cx="58" cy="310" r="4" fill="#00CC68"/>
  <rect x="74" y="306" width="380" height="8" rx="4" fill="#27272A"/>

  <rect x="470" y="240" width="70" height="80" rx="8" fill="#1E1E24" stroke="#27272A"/>
  <path d="M 485 295 L 500 270 L 515 285 L 530 260 L 530 305 L 485 305 Z" fill="#00CC68" fill-opacity="0.2"/>
  <circle cx="520" cy="260" r="6" fill="#00CC68"/>
</svg>"""
    return svg


class UseTemplateRequest(BaseModel):
    user_id: Optional[str] = Field(None, description="Requesting user ID")
    name: Optional[str] = Field(None, description="Custom name for new project")


@router.get("/api/templates/ppt")
def list_ppt_templates():
    """Returns list of all LaTeX Beamer presentation templates discovered on disk."""
    templates = discover_ppt_templates()
    return [
        {
            "id": t["id"],
            "name": t["name"],
            "description": t["description"],
            "category": t["category"],
            "thumbnail": t["thumbnail"],
            "hasThumbnail": t["hasThumbnail"]
        }
        for t in templates
    ]


@router.get("/api/templates/ppt/{template_id}/thumbnail")
def get_template_thumbnail(template_id: str):
    """Serves template thumbnail image or dynamically generated SVG preview."""
    templates = discover_ppt_templates()
    target = next((t for t in templates if t["id"] == template_id), None)
    
    if not target:
        raise HTTPException(status_code=404, detail="Template not found")

    tmpl_path = Path(target["path"])
    for ext in ["png", "jpg", "jpeg", "webp"]:
        thumb_path = tmpl_path / f"thumbnail.{ext}"
        if thumb_path.exists():
            return FileResponse(thumb_path)

    svg_content = generate_svg_thumbnail(target["name"], target["category"])
    return Response(content=svg_content, media_type="image/svg+xml")


@router.post("/api/templates/ppt/{template_id}/use")
def use_ppt_template(template_id: str, req: UseTemplateRequest = UseTemplateRequest()):
    """
    Creates a new project workspace by duplicating the entire template directory.
    - Preserves all .tex, .sty, .cls, images, fonts, bibliography, assets, hidden files.
    - Renames template.tex / pre.tex to main.tex.
    - Registers project and files in database.
    """
    templates = discover_ppt_templates()
    target = next((t for t in templates if t["id"] == template_id), None)

    if not target:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found.")

    src_dir = Path(target["path"])
    if not src_dir.exists():
        raise HTTPException(status_code=404, detail="Template source directory missing.")

    supabase = get_supabase_client()
    user_id = req.user_id

    if not user_id:
        try:
            users_res = supabase.table("user").select("id").limit(1).execute()
            if users_res.data:
                user_id = users_res.data[0]["id"]
        except Exception as e:
            logger.warning(f"Could not retrieve user fallback: {e}")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User ID is required to create a project from template."
        )

    project_id = str(uuid.uuid4())
    project_name = req.name.strip() if req.name and req.name.strip() else target["name"]

    safe_project = re.sub(r'[^a-zA-Z0-9_-]', '_', project_id)
    dest_dir = UPLOADS_BASE_DIR / safe_project

    # 1. Copy ENTIRE template directory recursively (including hidden files)
    try:
        if dest_dir.exists():
            shutil.rmtree(dest_dir)
        shutil.copytree(src_dir, dest_dir, symlinks=True, ignore=None)
        logger.info(f"Copied template directory '{src_dir}' to '{dest_dir}'")
    except Exception as copy_err:
        logger.error(f"Failed to copy template files: {copy_err}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to duplicate template files: {str(copy_err)}"
        )

    # 2. Rename primary entry .tex file to main.tex
    # Priority: template.tex -> pre.tex -> main.tex -> first top-level .tex -> first nested .tex
    main_tex_path = dest_dir / "main.tex"
    if not main_tex_path.exists():
        if (dest_dir / "template.tex").exists():
            (dest_dir / "template.tex").rename(main_tex_path)
            logger.info(f"Renamed 'template.tex' to 'main.tex' in workspace {project_id}")
        elif (dest_dir / "pre.tex").exists():
            (dest_dir / "pre.tex").rename(main_tex_path)
            logger.info(f"Renamed 'pre.tex' to 'main.tex' in workspace {project_id}")
        else:
            top_tex = list(dest_dir.glob("*.tex"))
            if top_tex:
                top_tex[0].rename(main_tex_path)
                logger.info(f"Renamed '{top_tex[0].name}' to 'main.tex' in workspace {project_id}")

    # 3. Create database records in Supabase (projects & project_members)
    try:
        repo_slug = f"prostack/{slugify(project_name)}"
        proj_record = {
            "id": project_id,
            "owner_id": user_id,
            "name": project_name,
            "description": target["description"],
            "repository": repo_slug,
            "default_branch": "main.tex",
            "language": "latex",
            "status": "active",
            "is_public": False,
            "is_favorite": False,
            "template": target["name"],
            "stars_count": 0,
        }
        supabase.table("projects").insert(proj_record).execute()

        member_record = {
            "id": str(uuid.uuid4()),
            "project_id": project_id,
            "user_id": user_id,
            "role": "Owner"
        }
        supabase.table("project_members").insert(member_record).execute()

        # 4. Populate latex_documents table for copied files
        text_extensions = {".tex", ".sty", ".cls", ".bib", ".txt", ".json", ".md", ".cfg"}
        for fpath in dest_dir.rglob("*"):
            if fpath.is_file():
                rel_path = str(fpath.relative_to(dest_dir))
                ext = fpath.suffix.lower()
                if ext in text_extensions:
                    try:
                        content = fpath.read_text(encoding="utf-8")
                    except Exception:
                        content = fpath.read_text(encoding="latin-1", errors="ignore")
                else:
                    content = f"[Binary Asset: {fpath.name}, Size: {fpath.stat().st_size} bytes]"

                doc_record = {
                    "project_id": project_id,
                    "file_path": rel_path,
                    "raw_code": content
                }
                supabase.table("latex_documents").upsert(doc_record, on_conflict="project_id, file_path").execute()

    except Exception as db_err:
        logger.error(f"Error creating project database records: {db_err}", exc_info=True)

    return {
        "success": True,
        "projectId": project_id,
        "id": project_id,
        "name": project_name,
        "template": target["name"]
    }
