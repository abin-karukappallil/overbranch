"""
opencode/template_registry.py — Template and Theme Registry for OpenCode Agent
==============================================================================
Discovers, indexes, and extracts LaTeX templates and theme styling (preambles,
color themes, layout structures) from backend/templates/ for PPT/Beamer,
IEEE papers, theses/reports, resumes/CVs, letters, and lab assignments.

Supports extracting:
- "preamble": Colors, themes, package declarations for redesigning existing documents
- "structure": High-level frame/section skeletons
- "all": Full compilable template code
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("opencode.template_registry")

TEMPLATES_ROOT = Path(__file__).resolve().parent.parent / "templates"

CATEGORY_MAP = {
    "ppt": "ppt",
    "presentation": "ppt",
    "beamer": "ppt",
    "slide": "ppt",
    "slides": "ppt",
    "deck": "ppt",
    "paper": "papers",
    "papers": "papers",
    "ieee": "papers",
    "article": "papers",
    "conference": "papers",
    "thesis": "thesis",
    "theissie": "thesis",
    "report": "thesis",
    "dissertation": "thesis",
    "seminar": "thesis",
    "resume": "resume",
    "cv": "resume",
    "curriculum": "resume",
    "letter": "letters",
    "letters": "letters",
    "cover_letter": "letters",
    "assignment": "assignments",
    "assignments": "assignments",
    "lab_report": "assignments",
    "lab": "assignments",
}


def normalize_category(category: Optional[str]) -> str:
    if not category:
        return "ppt"
    cat_clean = category.lower().strip().replace("-", "_").replace(" ", "_")
    return CATEGORY_MAP.get(cat_clean, cat_clean)


def list_available_themes(category: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Returns a list of all indexed templates and themes, optionally filtered by category.
    """
    target_cat = normalize_category(category) if category else None
    results: List[Dict[str, Any]] = []

    if not TEMPLATES_ROOT.exists():
        return results

    categories_to_scan = [target_cat] if target_cat and (TEMPLATES_ROOT / target_cat).exists() else [
        p.name for p in TEMPLATES_ROOT.iterdir() if p.is_dir()
    ]

    for cat in sorted(categories_to_scan):
        cat_dir = TEMPLATES_ROOT / cat
        if not cat_dir.is_dir():
            continue

        for item in sorted(cat_dir.iterdir()):
            if not item.is_dir():
                continue

            main_tex = item / "main.tex"
            if not main_tex.exists():
                continue

            meta_file = item / "metadata.json"
            meta: Dict[str, Any] = {}
            if meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                except Exception:
                    pass

            theme_id = meta.get("id", item.name.lower().replace(" ", "-"))
            theme_name = meta.get("name", item.name)
            description = meta.get("description", f"LaTeX template for {cat.upper()}: {item.name}")
            declared_cat = meta.get("category", cat.upper())

            results.append({
                "id": theme_id,
                "name": theme_name,
                "category": declared_cat,
                "folder_name": item.name,
                "has_metadata": meta_file.exists(),
                "description": description,
            })

    return results


def _extract_preamble(latex_code: str) -> str:
    """
    Extracts the document preamble (everything before \\begin{document}).
    Contains \\documentclass, \\usepackage, \\usetheme, \\setbeamercolor, \\definecolor, etc.
    """
    pos = latex_code.find(r"\begin{document}")
    if pos != -1:
        return latex_code[:pos].strip()
    return latex_code.strip()


def _extract_structure_skeleton(latex_code: str) -> str:
    """
    Extracts high-level environment skeletons (frames for Beamer, chapters/sections for reports).
    """
    lines = latex_code.splitlines()
    skeleton_lines: List[str] = []
    
    for line in lines:
        stripped = line.strip()
        if (
            stripped.startswith(("\\chapter", "\\section", "\\subsection", "\\subsubsection", "\\begin{frame}", "\\frametitle", "\\title{", "\\author{"))
            or stripped in ("\\begin{document}", "\\end{document}", "\\maketitle", "\\tableofcontents", "\\titlepage")
        ):
            skeleton_lines.append(line)
        elif stripped.startswith("\\end{frame}"):
            skeleton_lines.append(line)

    return "\n".join(skeleton_lines)


def get_template_theme(
    category: Optional[str] = None,
    theme_name: Optional[str] = None,
    extract_section: str = "all",
) -> Dict[str, Any]:
    """
    Fetches template source or theme styling for a given category and theme.

    Args:
        category: 'ppt', 'papers', 'thesis', 'resume', 'letters', 'assignments'
        theme_name: Specific theme name or keyword (e.g. 'nordlight', 'prism', 'ieee', 'madrid')
        extract_section: 'preamble' (styling/themes only), 'structure' (skeleton), or 'all' (complete code)

    Returns:
        Dict with status, theme metadata, and extracted LaTeX content.
    """
    target_cat = normalize_category(category)
    cat_dir = TEMPLATES_ROOT / target_cat

    if not cat_dir.exists():
        available_cats = [p.name for p in TEMPLATES_ROOT.iterdir() if p.is_dir()] if TEMPLATES_ROOT.exists() else []
        return {
            "success": False,
            "error": f"Unknown category '{category}'. Available categories: {', '.join(available_cats)}",
            "available_categories": available_cats,
        }

    # If no theme specified or theme_name == "list", return catalog
    if not theme_name or theme_name.lower() in ("list", "all", "help", ""):
        catalog = list_available_themes(target_cat)
        return {
            "success": True,
            "category": target_cat,
            "available_themes": catalog,
            "message": f"Found {len(catalog)} themes in {target_cat}. Specify theme_name to get code.",
        }

    theme_lower = theme_name.lower().strip()
    candidate_dirs = [p for p in cat_dir.iterdir() if p.is_dir() and (p / "main.tex").exists()]

    # Match strategy: exact match, id match, or substring match
    matched_dir: Optional[Path] = None

    # 1. Exact or ID match
    for cdir in candidate_dirs:
        meta_file = cdir / "metadata.json"
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                if meta.get("id", "").lower() == theme_lower or meta.get("name", "").lower() == theme_lower:
                    matched_dir = cdir
                    break
            except Exception:
                pass
        if cdir.name.lower() == theme_lower or cdir.name.lower().replace(" ", "-") == theme_lower:
            matched_dir = cdir
            break

    # 2. Substring match
    if not matched_dir:
        for cdir in candidate_dirs:
            if theme_lower in cdir.name.lower():
                matched_dir = cdir
                break

    # 3. Fallback to first available if none matched
    if not matched_dir and candidate_dirs:
        matched_dir = candidate_dirs[0]

    if not matched_dir:
        return {
            "success": False,
            "error": f"No templates found for category '{target_cat}' and theme '{theme_name}'.",
            "available_themes": [c.name for c in candidate_dirs],
        }

    main_tex = matched_dir / "main.tex"
    try:
        raw_code = main_tex.read_text(encoding="utf-8")
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to read template file: {e}",
        }

    meta = {}
    meta_file = matched_dir / "metadata.json"
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    section_mode = (extract_section or "all").lower().strip()
    if section_mode == "preamble":
        content = _extract_preamble(raw_code)
        usage_note = "Extracted styling preamble (packages, colors, themes). Use str_replace on the document preamble to redesign while preserving slide/section content."
    elif section_mode == "structure":
        content = _extract_structure_skeleton(raw_code)
        usage_note = "Extracted structural outline skeleton."
    else:
        content = raw_code
        usage_note = "Extracted complete template source."

    return {
        "success": True,
        "theme_id": meta.get("id", matched_dir.name.lower().replace(" ", "-")),
        "theme_name": meta.get("name", matched_dir.name),
        "category": meta.get("category", target_cat.upper()),
        "description": meta.get("description", f"Template for {target_cat}"),
        "section_type": section_mode,
        "content": content,
        "usage_note": usage_note,
    }
