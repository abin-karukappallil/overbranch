"""
opencode/visual_tools.py — ``view_rendered_pages``: the agent looks at the compiled page.

"The title overlaps the picture on slide 3", "this text is unreadable", "the
columns are not aligned" are statements about a rendered page. None of them can
be answered from LaTeX source: the source of an overlapping title and of a
well-placed one differ by a length somewhere, and nothing says which.

So this tool compiles the buffer, finds the page(s) the request is about, and
hands back two things:

* the **page image**, for a model that can see; and
* a **measured report** of the same render — overlapping text, text crossing an
  image, content off the page, low contrast, plus the layout defects
  ``justify_content`` already measures — each mapped to the source lines that
  produced it.

Both, because the image depends on the provider accepting image input and the
measurements do not. A run on a text-only gateway still gets "“Results”
overlaps “Figure 2” at lines 118–121", which is enough to act on.

The tool only looks. What to change is the model's decision — moving the title,
scaling the image and recolouring the text are all valid fixes for different
content — and its edit goes through the same write gate and compile gate as any
other.
"""

from __future__ import annotations

import logging
import os
import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Tuple

if TYPE_CHECKING:
    from .shadow_workspace import ShadowWorkspace

logger = logging.getLogger("opencode.visual_tools")

MAX_VIEW_PAGES = 3
VIEW_DPI = int(os.getenv("AGENT_VIEW_DPI", "110") or 110)
MAX_ISSUES = 24
THUMBNAIL_PX = 360

SCAN_PAGES = 40           # pages measured when no target is given, to find the ones with defects

_RE_NORM = re.compile(r"[^a-z0-9]+")
_SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}


def is_unambiguous(issue: Any) -> bool:
    """
    Defects that are wrong in any document: text or an image cut off at the edge of
    the page, and things printed on top of each other.

    These are the only classes checked without being asked. Measured over every
    bundled template (29 documents that are right as they stand), they raise no
    report at all — while the width, table and contrast checks raise dozens, because
    a theme's coloured bars, a CV's column layout and a navigation bar's dimmed
    entries all look like defects to a measurement. Those stay available to a
    request that asks about them; they are not grounds to send a new document back.
    """
    kind = getattr(issue, "type", None) or (issue.get("type") if isinstance(issue, dict) else None)
    evidence = getattr(issue, "evidence", None) or (issue.get("evidence") if isinstance(issue, dict) else None) or {}
    if kind in ("TEXT_OVERLAP", "ELEMENT_OVERLAP", "OFF_PAGE"):
        return True
    return kind == "MARGIN_VIOLATION" and "page_width" in evidence     # past the paper, not past the margin

# Requests about how the output looks. Deliberately about *appearance*: "add a
# visualisation" or "render the table as a figure" are content requests.
_RE_VISUAL_REQUEST = re.compile(
    r"\b(?:overlap\w*|overlaid|on top of (?:each other|one another|the)|collid\w*|"
    r"mis-?align\w*|not aligned|align(?:ment|ed)?|cut ?off|clipp?ed|truncated|"
    r"invisible|not visible|visibility|unreadable|illegible|hard to (?:read|see)|"
    r"can(?:no|')?t (?:read|see)|low contrast|contrast|"
    r"looks? (?:broken|wrong|bad|off|weird|odd|ugly|messy|cramped|squished)|"
    r"(?:how|when|once) it (?:is )?(?:renders?|rendered|compiles?|compiled)|rendered (?:page|slide|output|pdf)|"
    r"visually|visual (?:issue|problem|bug|glitch)s?|"
    r"(?:out|outside) of (?:the )?(?:page|slide|frame|margins?)|off (?:the )?(?:page|slide)|"
    r"goes? (?:off|outside|beyond)|overflow\w*|spacing|too (?:close|cramped|crowded))\b", re.I)


def is_visual_request(instruction: str) -> bool:
    """Whether a request is about how the compiled output looks."""
    return bool(_RE_VISUAL_REQUEST.search(instruction or ""))


def auto_target(ws: "ShadowWorkspace", instruction: str) -> Dict[str, Any]:
    """
    Arguments for ``view_rendered_pages`` from the request itself: the block it names
    ("the Results slide", "slide 3", "the last slide"), else nothing — and the tool
    then goes to the pages where it measures defects.
    """
    try:
        from document_index import index_nodes
        from .context_builder import match_nodes

        code = ws.get_buffer()
        for node, _why in match_nodes(code, index_nodes(code), instruction):
            if node.kind not in ("preamble", "document"):
                return {"node_id": node.node_id}
    except Exception as e:  # noqa: BLE001 — no target is a valid outcome
        logger.debug(f"Could not derive a visual target: {e}")
    return {}


def pages_with_defects(ws: "ShadowWorkspace", run: Dict[str, Any], code: str, page_count: int,
                       limit: int = MAX_VIEW_PAGES) -> List[int]:
    """The pages carrying the heaviest measured defects, worst first (empty if none)."""
    from latex_layout.visual import detect_visual_issues
    from .layout_tools import _scan

    pages = list(range(1, min(page_count, SCAN_PAGES) + 1))
    weight: Dict[int, float] = {}
    try:
        for issue in list(_scan(ws, run, code, pages=pages)) + detect_visual_issues(run["pdf"], pages):
            weight[issue.page] = weight.get(issue.page, 0.0) + max(issue.weight, 1.0)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"Defect scan failed: {e}")
    return sorted(sorted(weight, key=lambda n: -weight[n])[:limit])


def _norm(text: str) -> str:
    return _RE_NORM.sub(" ", (text or "").lower()).strip()


def parse_pages(value: Any, page_count: int) -> List[int]:
    """Pages from 3, "3", "2-4", "1,3" or [1, 3] — 1-based, in range, de-duplicated, in order."""
    raw: List[int] = []
    if isinstance(value, bool) or value in (None, ""):
        return []
    if isinstance(value, (int, float)):
        raw = [int(value)]
    elif isinstance(value, (list, tuple)):
        for v in value:
            raw.extend(parse_pages(v, page_count))
        return list(dict.fromkeys(raw))
    else:
        for part in re.split(r"[,\s;]+", str(value)):
            m = re.fullmatch(r"(\d+)\s*(?:-|–|to)\s*(\d+)", part)
            if m:
                a, b = int(m.group(1)), int(m.group(2))
                raw.extend(range(min(a, b), max(a, b) + 1))
            elif part.isdigit():
                raw.append(int(part))
    return list(dict.fromkeys(p for p in raw if 1 <= p <= page_count))


def pages_for_text(pdf_bytes: bytes, source_text: str, limit: int = MAX_VIEW_PAGES) -> List[int]:
    """
    The rendered pages a piece of LaTeX source ended up on.

    Compared as printed text: the source's visible lines against each page's
    text. Phrases first (a heading or a sentence is distinctive), then the share
    of the block's own words a page carries — a slide of three-word bullets has
    no long phrase to find. A Beamer frame with overlays occupies several
    consecutive pages; all of them (up to ``limit``) are returned.
    """
    import pymupdf
    from latex_layout.metrics import latex_to_plain

    plain = latex_to_plain(source_text or "")
    phrases = []
    for line in plain.splitlines():
        n = _norm(line)
        if len(n) >= 12 and len(n.split()) >= 2:
            phrases.append(n[:60])
    phrases = sorted(set(phrases), key=len, reverse=True)[:14]
    words = {w for w in _norm(plain).split() if len(w) >= 4}

    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        texts = [_norm(page.get_text()) for page in doc]

    phrase_scores = [sum(1 for p in phrases if p in t) for t in texts]
    best = max(phrase_scores, default=0)
    if best > 0:
        cut = max(1, (best + 1) // 2)
        return [i + 1 for i, s in enumerate(phrase_scores) if s >= cut][:limit]

    if not words:
        return []
    word_scores = []
    for t in texts:
        page_words = set(t.split())
        word_scores.append(len(words & page_words) / len(words))
    best_w = max(word_scores, default=0.0)
    if best_w < 0.5:
        return []
    return [i + 1 for i, s in enumerate(word_scores) if s >= best_w - 0.1][:limit]


def downscale(data: bytes, max_px: int, jpeg: bool = False) -> Tuple[bytes, str]:
    """An image no larger than ``max_px`` on its long side. Returns (bytes, mime)."""
    import pymupdf

    pix = pymupdf.Pixmap(data)
    if pix.alpha:
        pix = pymupdf.Pixmap(pix, 0)
    longest = max(pix.width, pix.height)
    if longest > max_px:
        s = max_px / longest
        pix = pymupdf.Pixmap(pix, max(1, int(pix.width * s)), max(1, int(pix.height * s)), None)
    if jpeg:
        try:
            return pix.tobytes("jpeg", jpg_quality=72), "image/jpeg"
        except Exception:  # noqa: BLE001 — fall through to PNG
            pass
    return pix.tobytes("png"), "image/png"


def thumbnail_data_url(data: bytes, max_px: int = THUMBNAIL_PX) -> Optional[str]:
    """A small JPEG data URL of an image, for the reasoning feed (never the full render)."""
    import base64
    try:
        small, mime = downscale(data, max_px, jpeg=True)
        return f"data:{mime};base64,{base64.b64encode(small).decode('ascii')}"
    except Exception as e:  # noqa: BLE001
        logger.debug(f"Thumbnail failed: {e}")
        return None


def _source_lines(text: str, span: Tuple[int, int]) -> Tuple[int, int]:
    first = text.count("\n", 0, span[0]) + 1
    last = text.count("\n", 0, max(span[0], span[1] - 1)) + 1
    return first, last


def _excerpt(text: str, first: int, last: int, limit: int = 4) -> str:
    lines = text.splitlines()
    out = [f"{i}: {lines[i - 1]}" for i in range(first, min(last, first + limit - 1) + 1) if 0 < i <= len(lines)]
    if last - first + 1 > limit:
        out.append("…")
    return "\n".join(out)


def _probe(issue: Any, text: str) -> Any:
    from latex_layout.issues import LayoutIssue
    return LayoutIssue(page=issue.page, type=issue.type, description=issue.description, text=text,
                       severity=issue.severity, region=issue.region, source=None, evidence={})


def _locate(issue: Any, sources: Sequence[Tuple[str, str]], main_path: str,
            ws: "ShadowWorkspace") -> Optional[Tuple[str, str, Tuple[int, int]]]:
    """
    (file, text, span) of the source lines that printed an issue's text.

    The exact lines, not the paragraph around them: ``justify_content`` widens to
    the paragraph because its repairs act on one, but a model fixing an overlap
    needs to be pointed at the line that is in the wrong place.
    """
    from .layout_tools import map_issue_to_source

    single = len(sources) == 1
    for path, text in sources:
        # TeX's line numbers describe the file it was reading; with several
        # sources they cannot be applied to the main buffer (see locate_issue).
        probe = issue if (single and path == main_path) else _probe(issue, issue.text)
        try:
            span = map_issue_to_source(probe, text, ws)
        except Exception as e:  # noqa: BLE001 — an unplaced issue is still worth reporting
            logger.debug(f"Could not map issue to source: {e}")
            span = None
        if span is not None:
            return path, text, span
    return None


def view_rendered_pages_tool(ws: "ShadowWorkspace", args: Dict[str, Any]) -> Dict[str, Any]:
    from latex_layout.issues import issue_counts, sort_issues
    from latex_layout.vision import render_pages
    from latex_layout.visual import detect_visual_issues
    from .layout_tools import _compile, _project_sources, _scan

    run = _compile(ws)
    if run.get("infra") or not run.get("pdf"):
        return {"success": False, "skipped": True,
                "error": "No PDF to look at (the compiler is unavailable or the document does not compile).",
                "new_errors": (run.get("new_errors") or [])[:3]}
    pdf: bytes = run["pdf"]

    import pymupdf
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        page_count = doc.page_count
        sizes = {i + 1: (round(p.rect.width, 1), round(p.rect.height, 1)) for i, p in enumerate(doc)}

    code = ws.get_buffer()
    resolved_from = ""
    pages = parse_pages(args.get("pages", args.get("page")), page_count)
    node_id = str(args.get("node_id") or "").strip()
    phrase = str(args.get("text") or "").strip()
    whole_document = str(args.get("scan") or "").strip().lower() == "document"
    min_severity = str(args.get("min_severity") or "").strip().lower()

    if whole_document:
        # Every page is measured; the images shown are the pages with the heaviest defects.
        pages = list(range(1, min(page_count, SCAN_PAGES) + 1))
        resolved_from = "every page of the document"
    elif pages:
        resolved_from = "the pages requested"
    elif node_id:
        node = ws.resolve_node(node_id)
        if node is None:
            return {"success": False, "error": f"No block '{node_id}' in the document. "
                                               f"Call inspect_document for the node IDs, or pass pages."}
        pages = pages_for_text(pdf, code[node.start:node.end])
        resolved_from = f"block {node.node_id}"
        if not pages:
            return {"success": False, "page_count": page_count,
                    "error": f"Could not tell which page block '{node.node_id}' was typeset on "
                             f"(its text was not found in the PDF). Pass pages=<number> instead."}
    elif phrase:
        pages = pages_for_text(pdf, phrase)
        resolved_from = f"the text “{phrase[:40]}”"
        if not pages:
            return {"success": False, "page_count": page_count,
                    "error": "That text was not found on any rendered page. Pass pages=<number> instead."}
    else:
        # No target: go where the measurable problems are, rather than to page 1.
        pages = pages_with_defects(ws, run, code, page_count)
        resolved_from = "the pages with measured defects (no target given)"
        if not pages:
            pages = list(range(1, min(page_count, MAX_VIEW_PAGES) + 1))
            resolved_from = "the first pages (no target given, no defects measured anywhere)"

    truncated = (not whole_document) and len(pages) > MAX_VIEW_PAGES
    if not whole_document:
        pages = pages[:MAX_VIEW_PAGES]

    issues = list(_scan(ws, run, code, pages=pages)) + detect_visual_issues(pdf, pages)
    if min_severity in _SEVERITY_RANK:
        issues = [i for i in issues if _SEVERITY_RANK.get(i.severity, 9) <= _SEVERITY_RANK[min_severity]]
    if args.get("unambiguous_only"):
        issues = [i for i in issues if is_unambiguous(i)]
    scanned = len(pages)
    if whole_document:
        weight: Dict[int, float] = {}
        for i in issues:
            weight[i.page] = weight.get(i.page, 0.0) + max(i.weight, 1.0)
        pages = sorted(sorted(weight, key=lambda n: -weight[n])[:2]) or pages[:1]
    sources = _project_sources(ws)
    main_path = getattr(ws, "_file_path", "main.tex")
    issues = sort_issues(issues)
    reported: List[Dict[str, Any]] = []
    for issue in issues[:MAX_ISSUES]:
        item = issue.as_dict()
        located = _locate(issue, sources, main_path, ws)
        if located:
            path, text, span = located
            first, last = _source_lines(text, span)
            item["file"] = path
            item["source_lines"] = [first, last]
            item["source"] = _excerpt(text, first, last)
            other = (issue.evidence or {}).get("other_text")
            if other:  # the second party of an overlap is usually the line that has to move
                second = _locate(_probe(issue, other), sources, main_path, ws)
                if second:
                    o_first, o_last = _source_lines(second[1], second[2])
                    item["other_source_lines"] = [o_first, o_last]
                    item["other_source"] = _excerpt(second[1], o_first, o_last)
        reported.append(item)

    rendered = render_pages(pdf, pages, dpi=VIEW_DPI)
    images = [{"data": png, "mime": "image/png", "label": f"page {n}"} for n, png in rendered]

    affected = sorted({i.page for i in issues})
    if whole_document and not reported:
        summary = f"No text off the page, overlap or low contrast was measured on any of the {scanned} page(s)."
    elif whole_document:
        summary = (f"{len(issues)} measured defect(s) on page(s) {', '.join(map(str, affected))} of {scanned}. "
                   f"Fix them with edits to the source lines shown.")
    elif reported:
        summary = (f"{len(reported)} measured defect(s) on page(s) {', '.join(map(str, pages))}. "
                   f"Fix them with edits to the source lines shown, then call view_rendered_pages again to confirm.")
    else:
        summary = (f"No overlap, off-page content, low contrast or overflow was measured on page(s) "
                   f"{', '.join(map(str, pages))}. Judge alignment and spacing from the image.")

    return {
        "success": True,
        "pages": pages,
        "page_count": page_count,
        "page_size_pt": {str(n): list(sizes[n]) for n in pages},
        "resolved_from": resolved_from,
        "more_pages_not_shown": truncated,
        "scanned_pages": scanned if whole_document else None,
        "unambiguous_only": bool(args.get("unambiguous_only")),
        "pages_with_issues": affected,
        "issue_total": len(issues),
        "issues": reported,
        "issue_counts": issue_counts(issues),
        "summary": summary,
        "note": ("The rendered page image(s) accompany this result when the model accepts images. "
                 "The measurements above come from the same render and do not depend on that."),
        "_images": images,
    }
