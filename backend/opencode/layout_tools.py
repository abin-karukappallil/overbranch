"""
opencode/layout_tools.py — Agent tools over latex_layout.

``justify_content`` is the layout-quality operation. "Fix the justification of
this document" is not a request to insert ``\\justifying``: it means *find the
places where the rendered pages look wrong and repair them*, and neither half
of that can be answered from the LaTeX source. Only the compiled PDF knows
that a file path ran into the margin, that a table is wider than the page, or
that a row is printing over the footer.

So the tool closes a loop the source cannot close on its own:

    compile → render → measure → map back to source → repair →
    recompile → re-measure → keep or roll back

Three properties make that loop safe to run unattended:

* **The model does not write the LaTeX.** It decides *that* the document
  should be tidied; ``latex_layout.repair`` decides *how*, from a closed set
  of operations. There is no path by which "fix the formatting" becomes a
  rewrite.
* **Nothing is kept on faith.** A repair survives only if the document still
  compiles *and* the measured layout got better. Compiling is not evidence
  that a layout fix worked — the broken version compiled too.
* **One defect at a time.** Each repair is its own transaction, applied and
  judged alone, so a fix that makes another page worse is rolled back by
  itself instead of taking the good ones with it.

``detect_overflow`` and ``inspect_pdf_geometry`` stay read-only, and
``detect_overflow`` is expressed over the same detector so the tool that
reports and the tool that repairs can never disagree about what is wrong.
"""

from __future__ import annotations

import logging
import os
import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, Tuple

from latex_layout.blocks import text_blocks_from_pdf
from latex_layout.issues import (LayoutIssue, OVERFLOW, SEVERITY, TABLE_CELL_OVERFLOW,
                                 TABLE_WIDTH, VERTICAL_OVERFLOW, detect_layout_issues,
                                 issue_counts, layout_score, sort_issues)
from latex_layout.justify import FontSpec, fit_fragment, probe_page_geometry, split_preamble, tex_probe
from latex_layout.overflow import detect_overflow, text_right_edge
from latex_layout.repair import RepairOp, find_tabular, plan_repairs

if TYPE_CHECKING:
    from .shadow_workspace import ShadowWorkspace

logger = logging.getLogger("opencode.layout_tools")

MAX_FIXES_DEFAULT = 12
MAX_PAGES = int(os.environ.get("JUSTIFY_MAX_PAGES", "40") or 40)
VISION_ENABLED = os.environ.get("JUSTIFY_VISION", "0") == "1"

_FAMILY_BY_PACKAGE = (
    ("carlito", "carlito"), ("arimo", "arimo"), ("tinos", "tinos"), ("caladea", "caladea"),
    ("helvet", "helvetica"), ("mathptmx", "times"), ("times", "times"), ("newtxtext", "times"),
    ("mathpazo", "palatino"), ("palatino", "palatino"), ("courier", "courier"),
)


def document_font(code: str) -> FontSpec:
    """Best-effort main font of a document, for metric-based measurement."""
    pre = split_preamble(code)
    family = "lmodern"
    for pkg, fam in _FAMILY_BY_PACKAGE:
        if re.search(r"\\usepackage(?:\[[^\]]*\])?\{[^}]*\b" + pkg + r"\b", pre):
            family = fam
            break
    if family in ("helvetica",) or "\\sfdefault" in pre or re.search(r"\\documentclass(?:\[[^\]]*\])?\{beamer\}", pre):
        family = family if family != "lmodern" else "lmsans"
    m = re.search(r"\\documentclass\[([^\]]*)\]", pre)
    size = 10.0
    if m:
        sm = re.search(r"(\d+(?:\.\d+)?)pt", m.group(1))
        if sm:
            size = float(sm.group(1))
    elif re.search(r"\\documentclass\{beamer\}", pre):
        size = 11.0
    return FontSpec(family=family, size=size)


def _compile(ws: "ShadowWorkspace") -> Dict[str, Any]:
    from .shadow_compiler import compile_workspace
    return compile_workspace(ws)


def _geometry(ws: "ShadowWorkspace", code: str) -> Optional[Dict[str, float]]:
    """The document's text area, probed once per buffer and cached."""
    cache = ws.__dict__.setdefault("_layout_geometry", {})
    pre = split_preamble(code)
    key = hash(pre)
    if key not in cache:
        try:
            cache[key] = probe_page_geometry(pre, dict(getattr(ws, "_aux_files", {})))
        except Exception as e:
            logger.debug(f"Geometry probe failed: {e}")
            cache[key] = None
    return cache[key]


def _scan(ws: "ShadowWorkspace", run: Dict[str, Any], code: str,
          pages: Optional[Sequence[int]] = None) -> List[LayoutIssue]:
    """Every measured layout defect of the current buffer's rendered output."""
    log = run.get("log") or ""
    return detect_layout_issues(run.get("pdf"), log, geometry=_geometry(ws, code),
                                pages=pages, max_pages=MAX_PAGES, source=code)


# ---------------------------------------------------------------------------
# Mapping a rendered defect back to the source that produced it
# ---------------------------------------------------------------------------

def _line_span(code: str, first: int, last: int) -> Optional[Tuple[int, int]]:
    lines = code.splitlines(keepends=True)
    if first < 1 or first > len(lines):
        return None
    last = min(max(last, first), len(lines))
    start = sum(len(x) for x in lines[:first - 1])
    return start, start + sum(len(x) for x in lines[first - 1:last])


def _distinctive(text: str) -> str:
    """The longest run of a rendered line worth searching the source for."""
    t = re.sub(r"\s+", " ", (text or "")).strip()
    return t[:120]


def _match_plain_line(code: str, rendered: str) -> Optional[Tuple[int, int]]:
    """
    The source line whose *visible* text best matches a rendered line.

    The locator matches source against source. A line read back from the PDF
    is neither: TeX has already stripped the markup and re-broken the text, so
    "…its manifests (packag" exists nowhere in a source that reads
    "…its manifests (\\texttt{package.json}". Comparing what each source line
    would *print* against what the page actually printed closes that gap, and
    it is the one place in the pipeline where the two representations meet.
    """
    from latex_layout.metrics import latex_to_plain

    want = re.sub(r"\s+", "", rendered)[:60]
    if len(want) < 10:
        return None
    best: Optional[Tuple[int, int, int]] = None          # (overlap, start, end)
    offset = 0
    for line in code.splitlines(keepends=True):
        plain = re.sub(r"\s+", "", latex_to_plain(line))
        if len(plain) >= 10:
            # Longest prefix of the rendered line this source line prints.
            n = 0
            while n < len(want) and want[:n + 1] in plain:
                n += 1
            if n >= 10 and (best is None or n > best[0]):
                best = (n, offset, offset + len(line))
        offset += len(line)
    return (best[1], best[2]) if best else None


def _project_sources(ws: "ShadowWorkspace") -> List[Tuple[str, str]]:
    """
    Every LaTeX file the compiled PDF was built from, main first.

    A defect is rendered by whichever file holds the text, and in any real
    document that is rarely main.tex: a thesis is `\\input{chapters/…}`, and
    its main file holds nothing but a preamble and a list of includes. Looking
    for the offending line only in the main buffer found nothing, every issue
    came back "could not be located in the source", and the tool reported
    defects it then declined to repair.
    """
    files: List[Tuple[str, str]] = [(getattr(ws, "_file_path", "main.tex"), ws.get_buffer())]
    reference = set(getattr(ws, "_reference_files", {}) or {})
    for path, content in (getattr(ws, "_aux_files", {}) or {}).items():
        if path in reference or path == files[0][0]:
            continue
        if path.rsplit(".", 1)[-1].lower() in ("tex", "sty", "cls", "bbl"):
            files.append((path, content))
    return files


def map_issue_to_source(issue: LayoutIssue, code: str, ws: "ShadowWorkspace") -> Optional[Tuple[int, int]]:
    """
    The span of source that produced ``issue``, or None if it cannot be told.

    Three sources of truth, best first: TeX's own ``at lines a--b`` for an
    overfull box; the locator (exact → normalized → fuzzy, the same ladder
    every other edit in this codebase uses) on the rendered text; and, for a
    table, the enclosing environment of whatever anchor text was found.

    Returning None is a normal outcome. An issue nobody can place is reported
    to the user unrepaired, which is strictly better than editing a guess.
    """
    if issue.source:
        span = _line_span(code, issue.source[0], issue.source[1])
        if span:
            return span

    anchor: Optional[Tuple[int, int]] = None
    probe = _distinctive(issue.text)
    if len(probe) >= 8:
        from .locator import Target, resolve
        for needle in (probe, probe[:60], probe[:30]):
            if len(needle) < 8:
                break
            res = resolve(code, Target(text=needle), aliases=getattr(ws, "_node_aliases", None))
            if res.ok:
                anchor = (res.start, res.end)
                break
    if anchor is None:
        anchor = _match_plain_line(code, probe)
    if anchor is None:
        return None

    # A table defect is a property of the whole environment, not of the row
    # the anchor happened to land in: the column specification is what has to
    # change, and that lives up at \begin{tabular}.
    if issue.type in (TABLE_WIDTH, TABLE_CELL_OVERFLOW, VERTICAL_OVERFLOW):
        tab = _enclosing_tabular(code, anchor[0])
        if tab:
            return tab
    return anchor


def locate_issue(issue: LayoutIssue, ws: "ShadowWorkspace") -> Optional[Tuple[str, str, Tuple[int, int]]]:
    """
    ``(file_path, file_text, span)`` for the source behind ``issue``.

    The main file is tried first, because its line numbers are the ones TeX's
    overfull warnings refer to; an auxiliary file is matched on its text.
    """
    sources = _project_sources(ws)
    main_path = getattr(ws, "_file_path", "main.tex")
    # TeX's `at lines a--b` numbers the file it was *reading*, which in a
    # multi-file document is the included chapter, not main.tex. Applying
    # those numbers to the main buffer points at the preamble — so with more
    # than one source the line hint is dropped and the text has to place it.
    single_file = len(sources) == 1
    for path, text in sources:
        probe = issue if (single_file and path == main_path) else LayoutIssue(
            page=issue.page, type=issue.type, description=issue.description,
            text=issue.text, severity=issue.severity, region=issue.region,
            source=None, evidence=issue.evidence)
        span = map_issue_to_source(probe, text, ws)
        if span is not None:
            return path, text, _widen_to_paragraph(text, span)
    return None


def _widen_to_paragraph(text: str, span: Tuple[int, int]) -> Tuple[int, int]:
    """
    Grow a located span to the paragraph around it.

    The locator returns the run it matched, and a fuzzy match on a line read
    back from the PDF often covers only its first few words — "Sufficient
    local disk headroom" out of a sentence whose problem is the file path at
    the other end. Searching for the offending token inside that span finds
    nothing and the defect is reported unrepairable. The repairs themselves
    stay minimal regardless: they are chosen from the *rendered* defective
    line, so this only widens where they may look, never what they change.
    """
    start, end = span
    para_start = text.rfind("\n\n", 0, start)
    para_start = 0 if para_start < 0 else para_start + 2
    para_end = text.find("\n\n", end)
    para_end = len(text) if para_end < 0 else para_end
    for m in re.finditer(r"\\(?:begin|end)\s*\{document\}", text):
        if para_start <= m.start() < start:
            para_start = m.end()
        elif end < m.end() <= para_end:
            para_end = m.start()
    return (min(para_start, start), max(para_end, end))


def _enclosing_tabular(code: str, pos: int) -> Optional[Tuple[int, int]]:
    """The tabular-like environment containing ``pos``, outermost first."""
    best: Optional[Tuple[int, int]] = None
    search_from = 0
    while True:
        tab = find_tabular(code, search_from, len(code))
        if tab is None:
            break
        if tab.start <= pos < tab.end and (best is None or tab.start < best[0]):
            best = (tab.start, tab.end)
        if tab.start + 1 <= search_from:
            break
        search_from = tab.start + 1
    return best


# ---------------------------------------------------------------------------
# Applying one repair
# ---------------------------------------------------------------------------

def _inject_packages(ws: "ShadowWorkspace", packages: Sequence[str]) -> Optional[Dict[str, Any]]:
    """Adds any \\usepackage the repair needs. Returns a failure dict, or None."""
    for pkg in packages:
        buf = ws.get_buffer()
        if re.search(r"\\usepackage(?:\[[^\]]*\])?\{[^}]*\b" + re.escape(pkg) + r"\b", buf):
            continue
        m = re.search(r"\\begin\s*\{document\}", buf)
        if not m:
            return None
        added = ws._splice(m.start(), m.start(), f"\\usepackage{{{pkg}}}\n",
                           op="add_package", method="structural")
        if not added.get("success"):
            return added
    return None


def _apply_ops(ws: "ShadowWorkspace", ops: List[RepairOp], file_path: str,
               file_text: str) -> Optional[Dict[str, Any]]:
    """
    Applies a repair's operations to ``file_path``, last-first.

    Descending order keeps every offset valid: the operations were all planned
    against one snapshot of the file, so editing from the end means no earlier
    span has moved by the time it is written.

    Packages always go to the main buffer whatever file was repaired — the
    preamble lives there, and a `\\usepackage` inside an `\\input`-ed chapter
    is an error, not a fix.
    """
    main_path = getattr(ws, "_file_path", "main.tex")
    for op in sorted(ops, key=lambda o: -o.start):
        if file_path == main_path:
            res = ws._splice(op.start, op.end, op.new_text,
                             op="justify_content", method="layout_repair")
        else:
            res = ws.str_replace_file(file_path, file_text[op.start:op.end], op.new_text)
        if not res.get("success"):
            return res
    return _inject_packages(ws, sorted({p for o in ops for p in o.needs_packages}))


def _page_set(issues: Sequence[LayoutIssue]) -> List[int]:
    return sorted({i.page for i in issues})


# ---------------------------------------------------------------------------
# The tools
# ---------------------------------------------------------------------------

def detect_overflow_tool(ws: "ShadowWorkspace") -> Dict[str, Any]:
    run = _compile(ws)
    if run["infra"] or not run["pdf"]:
        return {"success": False, "skipped": True,
                "error": "No PDF to inspect (compiler unavailable or the document does not compile).",
                "new_errors": run.get("new_errors", [])[:3]}
    code = ws.get_buffer()
    report = detect_overflow(run["pdf"], "")
    lines = code.splitlines()
    overfull = []
    for o in run["overfull"]:
        item = dict(o)
        if o.get("lines"):
            a, b = o["lines"]
            item["source"] = "\n".join(f"{i}: {lines[i - 1]}" for i in range(a, min(b, a + 3) + 1)
                                       if 0 < i <= len(lines))
        overfull.append(item)
    report["overfull"] = overfull
    # Expressed over the same detector the repair path uses, so the tool that
    # reports a problem and the tool that fixes it cannot disagree about it.
    issues = _scan(ws, run, code)
    report["issues"] = [i.as_dict() for i in issues[:30]]
    report["issue_counts"] = issue_counts(issues)
    report["has_overflow"] = bool(issues or [o for o in overfull if o.get("severe")]
                                  or report["beyond_text_area"] or report["beyond_page"])
    report["success"] = True
    if report["has_overflow"]:
        report["hint"] = ("Call justify_content with scope='document' to repair these; it measures the "
                          "rendered pages and applies the smallest fix for each defect.")
    return report


def inspect_pdf_geometry_tool(ws: "ShadowWorkspace", page: int = 1) -> Dict[str, Any]:
    run = _compile(ws)
    if run["infra"] or not run["pdf"]:
        return {"success": False, "skipped": True, "error": "No PDF to inspect."}
    blocks, (pw, ph) = text_blocks_from_pdf(run["pdf"], max(0, page - 1))
    geom = _geometry(ws, ws.get_buffer())
    return {
        "success": True,
        "page": page,
        "page_size_pt": [round(pw, 1), round(ph, 1)],
        "text_right_edge_pt": (round(geom["right"], 1) if geom else text_right_edge(blocks)),
        "text_area_pt": ({k: round(v, 1) for k, v in geom.items()} if geom else None),
        "lines": [b.as_dict() for b in blocks[:80]],
        "truncated": max(0, len(blocks) - 80),
    }


_LR_BOX_RE = re.compile(r"\\(?:makebox|mbox|hbox|fbox|framebox|raisebox|resizebox\*?|scalebox|obhfit)"
                        r"\s*(?:\[[^\]]*\]|\{[^{}]*\})*\s*$")


def in_lr_box(code: str, start: int) -> bool:
    """
    True when ``start`` lies inside the argument of a box command that cannot
    break lines (\\makebox, \\mbox, …) or a tabular cell: content there is one
    line whatever its length, so it must be fitted, not wrapped.
    """
    depth = 0
    i = start - 1
    lo = max(0, start - 2000)
    while i >= lo:
        c = code[i]
        if c == "}" and code[i - 1:i] != "\\":
            depth += 1
        elif c == "{" and code[i - 1:i] != "\\":
            if depth == 0:
                if _LR_BOX_RE.search(code[max(0, i - 120):i]):
                    return True
            else:
                depth -= 1
        i -= 1
    # Inside a tabular row: the line holds an unescaped & before the target.
    line_start = code.rfind("\n", 0, start) + 1
    return bool(re.search(r"(?<!\\)&", code[line_start:start]))


def _fit_one_target(ws: "ShadowWorkspace", args: Dict[str, Any]) -> Dict[str, Any]:
    """
    The old single-target behaviour: measure one node or phrase against a width
    and apply the smallest fit. Still reachable with scope='node' / 'text',
    because an unbreakable one-line unit (a \\makebox label, a header) has no
    layout defect to detect — the caller simply knows it must fit a width.
    """
    from .locator import Target, resolve

    code = ws.get_buffer()
    node_ref = (args.get("node_id") or "").strip() or None
    text = args.get("text") or None
    alignment = (args.get("alignment") or "").strip().lower() or None
    try:
        width = float(args.get("width_pt") or 0)
    except (TypeError, ValueError):
        width = 0.0

    if node_ref and not text:
        node = ws.resolve_node(node_ref)
        if node is None:
            return ws._node_not_found("justify_content", node_ref)
        start, end = node.body_start, node.body_end
        if node.kind in ("section", "subsection", "subsubsection", "chapter", "part", "paragraph"):
            start, end = node.start, node.body_start
    else:
        res = resolve(code, Target(node_id=node_ref, text=text), aliases=ws._node_aliases)
        if not res.ok:
            return ws._failure("justify_content", {"text": (text or "")[:120], "node_id": node_ref}, res)
        start, end = res.start, res.end

    fragment = code[start:end]
    lead = fragment[:len(fragment) - len(fragment.lstrip())]
    trail = fragment[len(fragment.rstrip()):]
    core = fragment.strip()
    if not core:
        return {"success": False, "error": "The target is empty.", "document_unchanged": True}

    preamble = split_preamble(code)
    aux = dict(getattr(ws, "_aux_files", {}))
    if width <= 0:
        geom = _geometry(ws, code)
        width = (geom or {}).get("text_width") or 0.0
    if width <= 0:
        probe = tex_probe(preamble, [], aux)
        width = (probe or {}).get("LW") or (probe or {}).get("TW") or 0.0
    if width <= 0:
        return {"success": False, "error": "Could not determine the available width; pass width_pt.",
                "document_unchanged": True}

    single_line = True if in_lr_box(code, start + len(lead)) else None
    result = fit_fragment(core, width, document_font(code), alignment=alignment, single_line=single_line,
                          preamble=preamble, extra_files=aux)
    out: Dict[str, Any] = {"success": True, "justify": result.as_dict()}
    if not result.changed:
        out["message"] = "No change needed: the content fits the available width."
        return out

    tx = ws.begin_transaction()
    applied = ws._splice(start, end, lead + result.latex + trail, op="justify_content",
                         method="node" if node_ref else "text")
    if not applied.get("success"):
        ws.rollback_transaction(tx)
        return applied
    is_beamer = bool(re.search(r"\\documentclass(?:\[[^\]]*\])?\{beamer\}", preamble))
    pkgs = [p for p in result.needs_packages if not (p == "graphicx" and is_beamer)]
    failed = _inject_packages(ws, pkgs)
    if failed is not None:
        ws.rollback_transaction(tx)
        return failed
    out["lines_affected"] = applied.get("lines_affected")

    try:
        from .shadow_compiler import compile_workspace
        run = compile_workspace(ws)
        if not run["infra"]:
            if run["new_errors"]:
                ws.rollback_transaction(tx)
                return {"success": False, "failed_op": "justify_content", "document_unchanged": True,
                        "error": "The fix did not compile; it was rolled back.",
                        "new_errors": run["new_errors"][:3], "justify": result.as_dict()}
            lo, hi = applied["lines_affected"]
            still = [o for o in run["overfull"] if o.get("severe") and o.get("lines")
                     and o["lines"][0] <= hi and o["lines"][1] >= lo]
            out["verified"] = not still
            if still:
                out["remaining_overfull"] = still
    except Exception as e:  # verification is best-effort
        out["verify_error"] = str(e)[:200]
    return out


def justify_content_tool(ws: "ShadowWorkspace", args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Inspect the rendered document and repair its layout defects, smallest fix
    first, keeping only the repairs that measurably improve the page.
    """
    scope = (args.get("scope") or "").strip().lower()
    if not scope:
        # A caller naming one target means the old single-fit behaviour; a
        # caller naming nothing means "look at the document and fix it".
        scope = "node" if args.get("node_id") else ("text" if args.get("text") else "document")
    if scope in ("node", "text"):
        return _fit_one_target(ws, args)
    if scope not in ("document", "page"):
        return {"success": False, "error": f"Unknown scope '{scope}'. Use document, page, node or text.",
                "document_unchanged": True}

    try:
        max_fixes = max(1, min(int(args.get("max_fixes") or MAX_FIXES_DEFAULT), 40))
    except (TypeError, ValueError):
        max_fixes = MAX_FIXES_DEFAULT
    dry_run = bool(args.get("dry_run"))
    pages: Optional[List[int]] = None
    if scope == "page":
        try:
            pages = [int(args.get("page") or 1)]
        except (TypeError, ValueError):
            pages = [1]

    base_sha = ws.base_sha256
    base_ver = ws.base_version

    run = _compile(ws)
    if run["infra"] or not run["pdf"]:
        return {"success": False, "skipped": True, "document_unchanged": True,
                "error": ("The document could not be rendered, so its layout cannot be measured. "
                          "Fix the compile errors first." if not run["infra"]
                          else "No LaTeX compiler available; layout cannot be measured here."),
                "new_errors": run.get("new_errors", [])[:3]}

    code = ws.get_buffer()
    issues = _scan(ws, run, code, pages)
    # A second opinion, only on pages measurement found nothing wrong with,
    # and only when asked for: its findings are advisory and never repaired.
    advisory: List[Dict[str, Any]] = []
    if VISION_ENABLED:
        try:
            import pymupdf
            from latex_layout.vision import inspect_pages
            with pymupdf.open(stream=run["pdf"], filetype="pdf") as doc:
                all_pages = list(range(1, min(doc.page_count, MAX_PAGES) + 1))
            unexplained = [n for n in (pages or all_pages) if n not in {i.page for i in issues}]
            advisory = [i.as_dict() for i in inspect_pages(run["pdf"], unexplained)]
        except Exception as e:
            logger.debug(f"Vision pass skipped: {e}")
    before_score = layout_score(issues)
    found = [i.as_dict() for i in issues[:40]]
    if not issues:
        return {"success": True, "issues_found": 0, "repaired": 0, "document_unchanged": True,
                "message": "The rendered document has no measurable layout defects.",
                "observations": advisory}
    if dry_run:
        return {"success": True, "dry_run": True, "issues_found": len(issues), "repaired": 0,
                "document_unchanged": True, "by_type": issue_counts(issues),
                "issues": found, "layout_score": before_score, "observations": advisory}

    repaired: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    # Defects that have been tried and could not be improved. A defect that
    # *was* improved is deliberately left out, so the next rung of the ladder
    # gets a turn: giving a long path break opportunities often takes a 57pt
    # overflow down to 32pt without clearing it, and the paragraph fix that
    # finishes the job only applies once the token fix is in place. Retrying
    # cannot spin, because every kept repair must strictly lower the score and
    # `rounds` is bounded.
    attempted: set = set()
    progress_count: Dict[Any, int] = {}
    MAX_PASSES_PER_ISSUE = 3
    tx_all = ws.begin_transaction()

    for _round in range(max_fixes):
        progressed = False
        for issue in sort_issues(issues):
            key = issue.key()
            if key in attempted or progress_count.get(key, 0) >= MAX_PASSES_PER_ISSUE:
                continue
            attempted.add(key)
            located = locate_issue(issue, ws)
            if located is None:
                skipped.append({**issue.as_dict(), "reason": "could not be located in the source"})
                continue
            src_path, src_text, span = located
            ops = plan_repairs(issue, src_text, span)
            if not ops:
                skipped.append({**issue.as_dict(), "reason": "no safe minimal repair for this defect"})
                continue

            tx = ws.begin_transaction()
            failure = _apply_ops(ws, ops, src_path, src_text)
            if failure is not None:
                ws.rollback_transaction(tx)
                skipped.append({**issue.as_dict(),
                                "reason": f"edit rejected: {str(failure.get('error'))[:160]}"})
                continue

            after_run = _compile(ws)
            if after_run["infra"]:
                ws.rollback_transaction(tx)
                skipped.append({**issue.as_dict(), "reason": "compiler became unavailable"})
                continue
            if after_run["new_errors"] or not after_run["pdf"]:
                ws.rollback_transaction(tx)
                skipped.append({**issue.as_dict(), "reason": "the repair did not compile; rolled back",
                                "new_errors": [e.get("error") for e in after_run["new_errors"][:2]]})
                continue

            after = _scan(ws, after_run, ws.get_buffer(), pages)
            # Compiling is not evidence that a layout repair worked: the broken
            # version compiled too. The page has to measure better.
            if layout_score(after) >= layout_score(issues):
                ws.rollback_transaction(tx)
                skipped.append({**issue.as_dict(),
                                "reason": (f"no measured improvement "
                                           f"({layout_score(issues)} → {layout_score(after)}); rolled back")})
                continue

            # Improved: let this defect be looked at again with what is left
            # of the ladder, instead of being written off as handled.
            attempted.discard(key)
            progress_count[key] = progress_count.get(key, 0) + 1
            repaired.append({"page": issue.page, "type": issue.type,
                             "fix": ops[0].kind, "edits": len(ops), "file": src_path,
                             "description": ops[0].description,
                             "needs_packages": sorted({p for o in ops for p in o.needs_packages}),
                             "score": [layout_score(issues), layout_score(after)]})
            issues = after
            progressed = True
            break
        if not progressed or not issues:
            break

    # The document may have moved under us while this was running (a
    # collaborator typing, another tool). Committing a candidate built on a
    # dead base would overwrite their work.
    if (ws.base_sha256, ws.base_version) != (base_sha, base_ver):
        ws.rollback_transaction(tx_all)
        return {"success": False, "stale": True, "document_unchanged": True,
                "error": "The document changed while its layout was being analysed; nothing was applied. "
                         "Run justify_content again to work from the current version.",
                "issues_found": len(found)}

    out: Dict[str, Any] = {
        "success": True,
        "issues_found": len(found),
        "repaired": len(repaired),
        "skipped": len(skipped),
        "by_type": issue_counts(issues),
        "pages_verified": _page_set([i for i in sort_issues(issues)]) or _page_set(
            [LayoutIssue(page=r["page"], type=r["type"], description="") for r in repaired]),
        "layout_score": [before_score, layout_score(issues)],
        "fixes": repaired,
        "remaining": [s for s in skipped][:15],
        "document_unchanged": not repaired,
    }
    if advisory:
        out["observations"] = advisory
    if repaired:
        out["message"] = (f"Repaired {len(repaired)} layout defect(s) across "
                          f"{len({r['page'] for r in repaired})} page(s); "
                          f"{len(issues)} remain. Text content is unchanged.")
    else:
        out["message"] = (f"Found {len(found)} layout defect(s) but none could be repaired safely; "
                          f"the document was not modified.")
    return out
