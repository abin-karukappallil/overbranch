"""
opencode/image_refs.py — ``\\includegraphics`` paths that point at nothing.

A figure imported from an attached paper is saved as ``assets/system-architecture.png``
and the tool returns that path. Several steps later the model writes the slide and
types ``assets/fig2-system-architecture.png`` — close, plausible, and not a file.
(Observed on a real run: the import result had been compacted out of the
conversation by then, so the path was reconstructed from the caption.)

Nothing downstream notices. The compiler deliberately draws a "SAMPLE IMAGE"
placeholder for a missing image, so templates with absent artwork still build —
which also means the compile gate passes, the user gets a deck with a grey box
where the architecture diagram should be, and the real file sits unreferenced.

So the paths are checked directly, after every edit of a run that imported
figures:

* a new reference that resolves to no file is matched against the files this run
  imported (then the project's other images) by the words of its name, and
  rewritten when exactly one is clearly meant;
* what cannot be matched is reported — to the model once, and in the result.

Only runs that imported something are checked, and only references the run
itself introduced: a template's placeholder artwork and an image the user has
not uploaded yet are none of this module's business.
"""

from __future__ import annotations

import difflib
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Set, Tuple

if TYPE_CHECKING:
    from .shadow_workspace import ShadowWorkspace

logger = logging.getLogger("opencode.image_refs")

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".pdf", ".eps", ".webp")
MATCH_MIN = 0.6        # similarity a candidate needs…
MATCH_MARGIN = 0.15    # …and its lead over the runner-up
MAX_FIXES = 12

_RE_INCLUDE = re.compile(r"\\includegraphics\*?\s*(?:\[[^\]]*\])?\s*\{([^{}]+)\}")
_RE_GRAPHICSPATH = re.compile(r"\\graphicspath\s*\{((?:\s*\{[^{}]*\}\s*)+)\}")
# Words that label a figure rather than describe it: fig2, figure, table3, p5, f1, img, 12.
_RE_LABEL_TOKEN = re.compile(r"^(?:fig(?:ure)?\d*|tab(?:le)?\d*|img\d*|image\d*|p\d+|[ft]\d+|\d+)$")


def image_refs(code: str) -> List[Tuple[str, int, int]]:
    """``(path, start, end)`` of every ``\\includegraphics`` path that is not in a comment or verbatim."""
    from edit_validator import clean_latex_for_validation

    try:
        masked = clean_latex_for_validation(code)
    except Exception:  # noqa: BLE001 — an unmaskable document is still searched
        masked = code
    if len(masked) != len(code):
        masked = code
    out = []
    for m in _RE_INCLUDE.finditer(masked):
        raw = code[m.start(1):m.end(1)]
        path = raw.strip().strip('"').strip("'")
        if path:
            lead = len(raw) - len(raw.lstrip())
            out.append((path, m.start(1) + lead, m.start(1) + lead + len(raw.strip())))
    return out


def project_root(ws: "ShadowWorkspace") -> Optional[Path]:
    assets = getattr(ws, "_assets_dir", None)
    return Path(assets).parent if assets else None


def _graphics_dirs(code: str) -> List[str]:
    dirs = [""]
    m = _RE_GRAPHICSPATH.search(code)
    if m:
        dirs += [d.strip() for d in re.findall(r"\{([^{}]*)\}", m.group(1)) if d.strip()]
    return dirs


def resolves(path: str, root: Path, code: str = "") -> bool:
    """Whether TeX would find ``path`` in the project (with its default extensions and \\graphicspath)."""
    has_ext = Path(path).suffix.lower() in IMAGE_EXTS
    for d in _graphics_dirs(code):
        base = root / d / path
        if has_ext:
            if base.is_file():
                return True
        elif any(base.with_name(base.name + ext).is_file() for ext in IMAGE_EXTS):
            return True
    return False


def _tokens(path: str) -> Set[str]:
    stem = Path(path).stem.lower()
    return {t for t in re.split(r"[^a-z0-9]+", stem) if t and not _RE_LABEL_TOKEN.match(t)}


def similarity(a: str, b: str) -> float:
    """How likely two image paths name the same figure, from the words of their file names."""
    ta, tb = _tokens(a), _tokens(b)
    if ta and tb:
        common = ta & tb
        jaccard = len(common) / len(ta | tb)
        # One name wholly contained in the other ("system-architecture" in
        # "fig2-system-architecture-diagram", "accuracy" in "fig3-accuracy-versus-epoch").
        # A single shared word only counts when it is a distinctive one.
        whole = len(common) == min(len(ta), len(tb))
        distinctive = len(common) >= 2 or any(len(t) >= 6 for t in common)
        return max(jaccard, 0.9 if (whole and distinctive) else 0.0)
    return difflib.SequenceMatcher(None, Path(a).stem.lower(), Path(b).stem.lower()).ratio() * 0.8


def _project_images(root: Path) -> List[str]:
    out: List[str] = []
    try:
        for f in sorted(root.rglob("*")):
            if f.is_file() and f.suffix.lower() in IMAGE_EXTS:
                out.append(str(f.relative_to(root)))
    except OSError:
        pass
    return out


def new_unresolved_refs(ws: "ShadowWorkspace") -> List[str]:
    """Image paths this run introduced that no project file answers to (in order, de-duplicated)."""
    root = project_root(ws)
    if root is None or not root.is_dir():
        return []
    code = ws.get_buffer()
    before = {p for p, _s, _e in image_refs(ws.get_original())}
    seen: List[str] = []
    for path, _s, _e in image_refs(code):
        if path in before or path in seen or resolves(path, root, code):
            continue
        seen.append(path)
    return seen


def _best(path: str, candidates: Sequence[str]) -> Optional[str]:
    scored = sorted(((similarity(path, c), c) for c in candidates), reverse=True)
    if not scored or scored[0][0] < MATCH_MIN:
        return None
    if len(scored) > 1 and scored[0][0] - scored[1][0] < MATCH_MARGIN:
        return None
    return scored[0][1]


def reconcile_image_refs(ws: "ShadowWorkspace") -> Dict[str, Any]:
    """
    Rewrites new image paths that point at nothing to the file that was meant.
    Returns ``{"fixed": [{"from", "to"}], "missing": [paths still unresolved]}``.

    Does nothing unless this run imported figures: that is when a path is typed
    from memory instead of copied, and the only time there is a list of files the
    model certainly meant to use.
    """
    imported = list(getattr(ws, "imported_assets", []) or [])
    known = dict(ws.__dict__.get("_imported_figures", {}) or {})
    imported += [v.get("path") for v in known.values() if v.get("path") and v.get("path") not in imported]
    if not imported:
        return {"fixed": [], "missing": []}
    root = project_root(ws)
    if root is None or not root.is_dir():
        return {"fixed": [], "missing": []}

    fixed: List[Dict[str, str]] = []
    for _ in range(MAX_FIXES):
        unresolved = new_unresolved_refs(ws)
        if not unresolved:
            break
        code = ws.get_buffer()
        referenced = {p for p, _s, _e in image_refs(code)}
        free = [p for p in imported if p not in referenced]   # an imported figure is placed once
        target: Optional[Tuple[str, str]] = None
        for path in unresolved:
            # By name only. "One path that is no file, one figure not yet placed" is tempting
            # to pair up, and wrong: the model may simply have invented a chart, and putting
            # the architecture diagram under its caption is worse than a placeholder.
            match = _best(path, free) or _best(path, imported)
            if match is None:
                match = _best(path, [c for c in _project_images(root) if c not in imported])
            if match:
                target = (path, match)
                break
        if target is None:
            break
        old, new = target
        span = next(((s, e) for p, s, e in image_refs(code) if p == old), None)
        if span is None:
            break
        with ws._lock:  # noqa: SLF001 — the workspace's own write gate, as its edit methods use it
            res = ws._splice(span[0], span[1], new, op="fix_image_path")  # noqa: SLF001
        if not res.get("success"):
            logger.warning(f"Could not correct image path {old} -> {new}: {res.get('error')}")
            break
        fixed.append({"from": old, "to": new})
    if fixed:
        logger.info(f"Corrected {len(fixed)} image path(s): {fixed}")
    return {"fixed": fixed, "missing": new_unresolved_refs(ws)}


def available_images(ws: "ShadowWorkspace", limit: int = 20) -> List[str]:
    """Image files the document may reference: this run's imports first, then the project's."""
    imported = list(getattr(ws, "imported_assets", []) or [])
    root = project_root(ws)
    others = [p for p in (_project_images(root) if root and root.is_dir() else []) if p not in imported]
    return (imported + others)[:limit]
