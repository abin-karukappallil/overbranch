"""
opencode/attachment_tools.py — Figures from attached files into the project.

``list_attachment_figures`` says what there is; ``import_attachment_figure``
writes one into ``assets/`` and returns the LaTeX to place it. The model
decides *where* a figure belongs — that is a judgement about the content — and
never has to invent a filename: the only paths it may reference are ones a tool
returned.

An imported file is real (the shadow compile has to find it), so the run keeps
a list and removes what the final document does not reference, or everything
when the run is rolled back.

For a document being *built from* the attached material the figures are imported
before the model's first turn (``auto_import_figures``): the configured model
does not reliably reach for a tool it was only told about, and a seminar made
from a paper without the paper's figures is the outcome that was reported.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional

if TYPE_CHECKING:
    from .shadow_workspace import ShadowWorkspace

logger = logging.getLogger("opencode.attachment_tools")

MAX_SLUG = 48
PREVIEW_PX = 1024
AUTO_IMPORT_FIGURES = int(os.getenv("AGENT_ATTACH_AUTO_FIGURES", "6") or 6)   # figures placed in the project up front
AUTO_IMPORT_TABLES = int(os.getenv("AGENT_ATTACH_AUTO_TABLES", "2") or 2)     # …and compact tables
MIN_AUTO_PX = 120            # smaller than this on a side is an icon, not a figure worth a slide
MAX_TABLE_AUTO_PX = 900      # a taller table image is an appendix, not slide material


def _slug(text: str, fallback: str) -> str:
    s = re.sub(r"\.[A-Za-z0-9]{2,4}$", "", (text or "").strip())
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return (s[:MAX_SLUG].rstrip("-")) or fallback


def _default_name(figure: Dict[str, Any]) -> str:
    """fig2-system-architecture, from "Fig. 2. System architecture of the proposed …"."""
    caption = figure.get("caption") or ""
    body = re.sub(r"^\s*(?:Fig(?:ure)?\.?|FIG(?:URE)?\.?|Table|TABLE|Tab\.)\s*(?:\d+[a-z]?|[IVXLC]+)\s*[.:|\-–—]?\s*",
                  "", caption)
    body = re.sub(r"^\(Continued\.?\)\s*", "", body, flags=re.I)
    words = re.findall(r"[A-Za-z0-9]+", body)[:5]
    label = "table" if figure.get("kind") == "table" else "fig"
    prefix = (f"{label}{str(figure['number']).lower()}" if figure.get("number")
              else f"{'table' if label == 'table' else 'figure'}-p{figure.get('page', 1)}")
    return _slug("-".join([prefix] + words), prefix)


def _is_beamer(code: str) -> bool:
    return bool(re.search(r"\\documentclass(?:\[[^\]]*\])?\{beamer\}", code))


def _latex_for(path: str, figure: Dict[str, Any], source: str, beamer: bool) -> str:
    from pdf2latex.texutil import latex_text

    caption = latex_text(re.sub(r"\s+", " ", figure.get("caption") or "").strip())
    w, h = figure.get("width_px") or 0, figure.get("height_px") or 0
    tall = bool(w and h and h > 0.8 * w)
    if beamer:
        # A slide is wide and short: bound the height, or a tall figure pushes the text off it.
        size = r"width=0.9\linewidth,height=0.62\textheight,keepaspectratio"
        return ("\\begin{center}\n"
                f"  \\includegraphics[{size}]{{{path}}}\\\\[2pt]\n"
                f"  {{\\footnotesize {caption}}}\n"
                "\\end{center}")
    width = "0.6" if tall else "0.9"
    return ("\\begin{figure}[htbp]\n"
            "  \\centering\n"
            f"  \\includegraphics[width={width}\\linewidth]{{{path}}}\n"
            f"  \\caption{{{caption} (Source: {latex_text(source)})}}\n"
            "\\end{figure}")


def list_attachment_figures_tool(ws: "ShadowWorkspace", args: Dict[str, Any]) -> Dict[str, Any]:
    from attached_context import attached_context_store as store
    from attachment_figures import figures_for

    wanted = str(args.get("filename") or "").strip()
    records = store.get_attachments(ws.session_id)
    if wanted:
        match = store.find_attachment(ws.session_id, wanted)
        if match is None:
            return {"success": False, "error": f"No attached file named '{wanted}'.",
                    "attached": [r.get("filename") for r in records]}
        records = [match]
    if not records:
        return {"success": False, "error": "No files are attached to this chat."}

    out: List[Dict[str, Any]] = []
    for record in records:
        for f in figures_for(record, store):
            out.append({"figure_id": f["id"], "filename": f.get("filename"), "page": f["page"],
                        "caption": f["caption"], "kind": f["kind"],
                        "size_px": [f.get("width_px", 0), f.get("height_px", 0)]})
    return {
        "success": True,
        "figures": out,
        "count": len(out),
        "hint": ("Import the ones the document should show with import_attachment_figure(figure_id=…); "
                 "it returns the path and the LaTeX to place it." if out else
                 "No figures were found in the attached file(s)."),
    }


def import_attachment_figure_tool(ws: "ShadowWorkspace", args: Dict[str, Any]) -> Dict[str, Any]:
    from attached_context import attached_context_store as store
    from attachment_figures import figure_bytes, find_figure
    from project_storage import get_project_disk_path, save_project_asset_bytes

    figure_id = str(args.get("figure_id") or args.get("id") or "").strip()
    if not figure_id:
        return {"success": False, "error": "figure_id is required (see list_attachment_figures)."}
    found = find_figure(ws.session_id, figure_id, store)
    if found is None:
        return {"success": False,
                "error": f"No figure '{figure_id}' in the attached files. Call list_attachment_figures for the IDs."}
    record, figure = found

    done: Dict[str, Dict[str, Any]] = ws.__dict__.setdefault("_imported_figures", {})
    if figure["id"] in done:
        return {**done[figure["id"]], "note": "Already imported in this run; reuse this path."}

    payload = figure_bytes(record, figure, store)
    if payload is None:
        return {"success": False, "error": "The attached file is no longer available; ask the user to attach it again."}
    data, ext = payload

    project_id = getattr(ws, "_project_id", None) or "default"
    name = _slug(str(args.get("asset_name") or ""), "") or _default_name(figure)
    digest = hashlib.sha256(data).hexdigest()
    rel = f"assets/{name}.{ext}"
    reused = False
    for n in range(1, 50):
        candidate = f"assets/{name}.{ext}" if n == 1 else f"assets/{name}-{n}.{ext}"
        target = get_project_disk_path(project_id, candidate)
        if not target.exists():
            rel = candidate
            break
        if hashlib.sha256(target.read_bytes()).hexdigest() == digest:
            rel, reused = candidate, True   # the same figure is already in the project
            break
    else:
        return {"success": False, "error": f"Could not find a free filename for '{name}'."}

    if not reused:
        save_project_asset_bytes(project_id, rel, data, label=Path(rel).name)
        ws.imported_assets.append(rel)
    ws.set_assets_dir(str(get_project_disk_path(project_id, "assets")))

    # The buffer of a deck being created is still empty; the loop says what is being built.
    beamer = _is_beamer(ws.get_buffer()) or bool(ws.__dict__.get("_target_slides"))
    result: Dict[str, Any] = {
        "success": True,
        "path": rel,
        "figure_id": figure["id"],
        "source": record.get("filename"),
        "page": figure.get("page"),
        "caption": figure.get("caption"),
        "size_px": [figure.get("width_px", 0), figure.get("height_px", 0)],
        "latex": _latex_for(rel, figure, record.get("filename") or "attached document", beamer),
        "note": ("Saved to the project. Place it with insert_block / replace_block in the slide or section that "
                 "discusses it, using the LaTeX above (adjust the width if the slide also carries text). "
                 "Reference exactly this path."),
    }
    done[figure["id"]] = dict(result)
    try:
        from .visual_tools import downscale
        small, mime = downscale(data, PREVIEW_PX)
        result["_images"] = [{"data": small, "mime": mime, "label": f"figure {figure['id']}"}]
    except Exception as e:  # noqa: BLE001 — the preview is optional
        logger.debug(f"Figure preview failed: {e}")
    return result


def _is_referenced(rel: str, haystack: str) -> bool:
    """
    Whether a document uses an imported file. By file name, not by exact path: the
    same image can be written with or without its extension, or through a
    ``\\graphicspath``, and a figure the document shows must never be deleted over
    how its path was spelled.
    """
    stem = Path(rel).stem
    return bool(re.search(r"(?<![A-Za-z0-9_-])" + re.escape(stem) + r"(?![A-Za-z0-9_-])", haystack))


def cleanup_imported_assets(ws: "ShadowWorkspace", final_texts: Optional[Iterable[str]]) -> List[str]:
    """
    Removes imported assets the run did not end up using. ``final_texts`` is the
    text of every file the run leaves behind; ``None`` means the run was rolled
    back and nothing it imported is wanted. Returns the paths that were kept.
    """
    from project_storage import delete_project_asset

    imported = list(getattr(ws, "imported_assets", []) or [])
    if not imported:
        return []
    haystack = "\n".join(final_texts) if final_texts is not None else ""
    project_id = getattr(ws, "_project_id", None) or "default"
    kept: List[str] = []
    for rel in imported:
        if final_texts is not None and _is_referenced(rel, haystack):
            kept.append(rel)
        else:
            delete_project_asset(project_id, rel)
    ws.imported_assets = kept
    return kept


def auto_import_figures(ws: "ShadowWorkspace") -> List[Dict[str, Any]]:
    """
    Imports the figures of the attached files before the model's first turn, for a
    document that is being built from them. Captioned figures first, in reading
    order, then a few compact tables (as images — often the only form their numbers
    survive in). Returns the import results (path, caption, page, source, size).
    """
    from attached_context import attached_context_store as store
    from attachment_figures import figures_for

    figures: List[Dict[str, Any]] = []
    tables: List[Dict[str, Any]] = []
    for record in store.get_attachments(ws.session_id):
        try:
            found = figures_for(record, store)
        except Exception as e:  # noqa: BLE001 — one unreadable attachment must not stop the others
            logger.warning(f"Could not list figures of '{record.get('filename')}': {e}")
            continue
        for f in found:
            w, h = f.get("width_px") or 0, f.get("height_px") or 0
            if min(w, h) < MIN_AUTO_PX:
                continue
            if f.get("kind") == "table":
                if h <= MAX_TABLE_AUTO_PX and "continued" not in (f.get("caption") or "").lower():
                    tables.append(f)
            elif f.get("captioned") or record.get("kind") == "image":
                figures.append(f)

    imported: List[Dict[str, Any]] = []
    for f in figures[:AUTO_IMPORT_FIGURES] + tables[:AUTO_IMPORT_TABLES]:
        res = import_attachment_figure_tool(ws, {"figure_id": f["id"]})
        res.pop("_images", None)
        if res.get("success"):
            res["kind"] = f.get("kind")
            imported.append(res)
    return imported


def imported_figures_block(imported: List[Dict[str, Any]], beamer: bool) -> str:
    """What the model is told about figures that are already in the project."""
    rows = []
    for r in imported:
        size = "×".join(str(v) for v in (r.get("size_px") or []))
        what = "table image" if r.get("kind") == "table" else "figure"
        rows.append(f"  {r['path']}  —  {str(r.get('caption') or '')[:140]}  "
                    f"({what}, {r.get('source')} p.{r.get('page')}, {size} px)")
    if beamer:
        how = ("  \\begin{center}\\includegraphics[width=0.9\\linewidth,height=0.62\\textheight,keepaspectratio]"
               "{<path>}\\end{center}   (on a slide with little other text; give a wide figure its own slide)")
    else:
        how = ("  \\begin{figure}[htbp]\\centering\\includegraphics[width=0.9\\linewidth]{<path>}"
               "\\caption{<caption> (Source: <file>)}\\end{figure}")
    return (
        "FIGURES ALREADY IN THE PROJECT (imported from the attached files for this request):\n"
        + "\n".join(rows) + "\n\n"
        "USE THEM. A presentation or report built from this material must show its figures: put each one on "
        "the slide / in the section that discusses what it shows — the architecture figure where the system is "
        "explained, a results figure or table beside the results — like this:\n" + how + "\n"
        "Reference EXACTLY the paths listed above (they are real files; any other path shows a placeholder). "
        "Leave a figure out only when nothing in the document discusses it. A table image is for a table whose "
        "numbers you are not retyping as a LaTeX table."
    )
