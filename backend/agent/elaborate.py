r"""
`elaborate_content` — add to a block without replacing a word of it.

WHY THIS IS A TOOL AND NOT A PROMPT
-----------------------------------
"Elaborate this section" asked of a model editing the document produces a
*replacement* for the section: the same points, re-worded, perhaps a little
longer, and the user's own sentences gone. Measured on real runs, the cheapest
behaviour that satisfied every prompt rule was a reworded heading with a
sentence under it — which is why the growth gate in `edit_validator` exists at
all.

So the two properties the request is really about are made structural instead of
requested:

  **It cannot delete anything.** There is no code path here that overwrites a
  target's text. The tool only ever splices new material in — after the block's
  existing body, or (on a slide, which overflows if stuffed) as follow-up frames
  after it. Preservation is therefore a property of the operation, not a hope
  about the model's output, and it is asserted afterwards anyway.

  **It cannot be token.** The new material is measured in *visible* characters
  (markup does not count), must clear `EXPANSION_MIN_NEW_CHARS`, must not simply
  restate what the block already said, must not cite a key the bibliography does
  not have, must pass the ordinary write gate, and must compile — each checked,
  with the specific failure handed back for another attempt, and the insert
  rolled back if the document stops building.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It does not reword, re-order, condense or restructure existing text, and it does
not touch a heading: headings are how every block in this codebase is tracked
(the locator, the node IDs, the expansion worklist). A request to improve the
*wording* is `humanize_document`'s; a request to make the pages *look* right is
`justify_content`'s. This tool adds substance and nothing else.
"""
from __future__ import annotations

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Sequence, Tuple, TYPE_CHECKING

from document_index import get_expansion_units
from edit_validator import (
    EXPANSION_MIN_NEW_CHARS, EXPANSION_MIN_RETENTION, content_words,
    expansion_target_delta, measure_retention,
)

if TYPE_CHECKING:  # pragma: no cover
    from .shadow_workspace import ShadowWorkspace

logger = logging.getLogger("agent.elaborate")

# Attempts per block: the first try, plus retries that carry the measured
# reason it was refused ("you added 340 of 1000 characters").
ELABORATE_MAX_ATTEMPTS = max(1, int(os.getenv("ELABORATE_MAX_ATTEMPTS", "3") or 3))
# Blocks whose material is generated at once when the target is the document.
ELABORATE_CONCURRENCY = max(1, int(os.getenv("ELABORATE_CONCURRENCY", "4") or 4))
# Share of the new text's content words that may already appear in the block.
# Above this the "elaboration" is a restatement of what was there.
ELABORATE_MAX_ECHO = float(os.getenv("ELABORATE_MAX_ECHO", "0.75") or 0.75)
# Blocks elaborated in one `target="document"` call. The run can be asked again
# to continue, and an unbounded call is a twenty-minute request with no progress
# the user can see.
ELABORATE_MAX_UNITS = max(1, int(os.getenv("ELABORATE_MAX_UNITS", "40") or 40))

_SLIDE_KINDS = ("frame", "page")
_RE_CITE_KEY = re.compile(r"\\(?:cite|citep|citet|citeauthor|citeyear|citealp|citealt|"
                          r"fullcite|textcite|parencite)\s*(?:\[[^\]]*\])*\s*\{([^{}]*)\}")
_RE_REF_KEY = re.compile(r"\\(?:ref|eqref|autoref|nameref|cref|Cref|vref|pageref)\s*\{([^{}]*)\}")
_RE_BIBITEM = re.compile(r"\\bibitem\s*(?:\[[^\]]*\])?\s*\{([^{}]*)\}")
_RE_BIB_ENTRY = re.compile(r"@\w+\s*\{\s*([^,\s}]+)")
_RE_LABEL = re.compile(r"\\label\s*\{([^{}]*)\}")
_RE_FENCE = re.compile(r"^\s*```(?:latex|tex)?\s*|\s*```\s*$", re.IGNORECASE)
_RE_HEADING = re.compile(r"\\(?:part|chapter|section|subsection|subsubsection|paragraph)\s*\*?\s*\{")


# ---------------------------------------------------------------------------
# Recognising the request
# ---------------------------------------------------------------------------
_RE_ELABORATE_REQUEST = re.compile(
    r"\belaborat\w*\b"
    r"|\bexpand\b"
    r"|\bexpand(?:ed|ing)\b"
    r"|\badd\s+(?:more|further|additional)\s+(?:detail|depth|content|material|explanation)"
    r"|\bmore\s+(?:detail|depth|elaboration)\b"
    r"|\b(?:explain|describe|discuss)\s+(?:\w+\s+){0,3}(?:in\s+)?(?:more|greater|further)\s+(?:depth|detail)\b"
    r"|\bgo\s+(?:in)?to\s+(?:more|greater)\s+(?:depth|detail)\b"
    r"|\bmake\s+(?:it|this|the\s+\w+)\s+(?:more\s+)?(?:detailed|longer|comprehensive|thorough)\b"
    r"|\b(?:lengthen|deepen|flesh\s+out|build\s+out|beef\s+up)\b",
    re.IGNORECASE)


def is_elaborate_request(instruction: str) -> bool:
    """Whether the request is to ADD material rather than change what is there."""
    return bool(_RE_ELABORATE_REQUEST.search(instruction or ""))


# ---------------------------------------------------------------------------
# Measuring what an insert really added
# ---------------------------------------------------------------------------
def visible_length(latex_text: str) -> int:
    """
    Characters a reader will see, markup removed.

    The floor is counted on this and not on `len()`, because a thousand
    characters of `\\begin{itemize}` scaffolding and `\\textbf{}` wrappers is not
    a thousand characters of new material.
    """
    from .humanize import _plain  # one definition of "what a reader sees"
    return len(re.sub(r"\s+", " ", _plain(latex_text)).strip())


def echo_ratio(existing: str, addition: str) -> float:
    """
    Share of the addition's content words that the block already contained.

    1.0 means the "elaboration" says nothing the block did not already say.
    """
    new_words = content_words(addition)
    if not new_words:
        return 1.0
    old = set(content_words(existing))
    if not old:
        return 0.0
    return sum(1 for w in new_words if w in old) / len(new_words)


def known_keys(code: str, aux: Optional[Dict[str, str]] = None) -> Tuple[set, set]:
    """Citation keys and labels the project actually defines."""
    cites: set = set()
    labels: set = set()
    for text in [code] + list((aux or {}).values()):
        cites.update(_RE_BIBITEM.findall(text))
        cites.update(_RE_BIB_ENTRY.findall(text))
        labels.update(_RE_LABEL.findall(text))
    return cites, labels


def invented_references(addition: str, cites: set, labels: set) -> List[str]:
    """
    Citation keys and cross-references the addition uses and the document does
    not define.

    This is the one part of "do not hallucinate" that can be checked
    mechanically, and it is the part that bites: a fabricated `\\cite{smith2019}`
    renders as a bold **[?]** in the PDF and looks like a real reference in the
    source.
    """
    bad: List[str] = []
    for group in _RE_CITE_KEY.findall(addition):
        for key in (k.strip() for k in group.split(",")):
            if key and key not in cites:
                bad.append(f"\\cite{{{key}}}")
    own_labels = set(_RE_LABEL.findall(addition))
    for group in _RE_REF_KEY.findall(addition):
        for key in (k.strip() for k in group.split(",")):
            if key and key not in labels and key not in own_labels:
                bad.append(f"\\ref{{{key}}}")
    return bad


def check_addition(existing: str, addition: str, target: int,
                   cites: set, labels: set) -> List[str]:
    """
    Why this material is not an elaboration of this block, if it is not.

    Empty list means: enough new, substantive, grounded text to be worth
    inserting. Each string is a reason the model can act on.
    """
    problems: List[str] = []
    added = visible_length(addition)
    if added < target:
        problems.append(f"only {added} characters of visible new text — this block needs at least "
                        f"{target}. Write more substance: mechanisms, trade-offs, a worked example, "
                        "a derivation, concrete detail.")
    echo = echo_ratio(existing, addition)
    if echo > ELABORATE_MAX_ECHO:
        problems.append(f"{int(echo * 100)}% of the new text repeats words the block already uses — "
                        "this is a restatement, not an elaboration. Add something the block does "
                        "not already say.")
    bad = invented_references(addition, cites, labels)
    if bad:
        problems.append("these citations/references do not exist in this document: "
                        + ", ".join(sorted(set(bad))[:6])
                        + ". Never invent a key; explain the point without a citation instead.")
    if _RE_HEADING.search(addition):
        heads = _RE_HEADING.findall(addition)
        if len(heads) > 2:
            problems.append("the material adds several new headings — elaborate the block itself "
                            "rather than restructuring the document around it.")
    return problems


# ---------------------------------------------------------------------------
# Asking for the material
# ---------------------------------------------------------------------------
_PROMPT_HEAD = """You are adding new material to one block of an academic LaTeX document.

You are NOT rewriting the block. Everything already in it stays exactly where it
is; your text is placed after it. So write only the NEW material.

HARD REQUIREMENTS
- At least {target} characters of visible new prose (markup does not count).
  That is roughly {paras} substantial paragraphs.
- Substance, not restatement: mechanisms, why a design is the way it is,
  trade-offs, derivations, a worked example, concrete consequences. Text that
  repeats what the block already says is rejected and sent back.
- Do NOT invent facts. Build on what this document and established knowledge of
  the subject support. Never fabricate a measurement, a dataset, an author or a
  number, and never cite a key that is not already in this document's
  bibliography{bibnote}.
- Where a concrete figure would have to be invented, explain the mechanism
  instead.
- Do not repeat or re-word the block's heading, and do not add new section
  headings.
- Return RAW LaTeX only. No markdown fences, no commentary, no explanation of
  what you wrote.
"""

_PROMPT_SLIDE = """
THIS BLOCK IS A SLIDE. A frame overflows if you stuff it, so do NOT write a long
body. Instead return TWO OR THREE COMPLETE follow-up frames that continue the
topic:

\\begin{{frame}}{{<Topic>: Detailed Analysis}}
  \\begin{{itemize}}
    \\item ...
  \\end{{itemize}}
\\end{{frame}}

At most 6 bullets per frame, each a full clause. They are placed directly after
the slide, which keeps its own content.
"""

_PROMPT_PROSE = """
Write flowing paragraphs. Add a displayed equation, a `tabular` of values the
document already contains, an enumerated analysis or a worked example where the
topic admits one. Use \\subsection only if the material genuinely needs one.
"""


def _build_prompt(block_title: str, block_kind: str, block_text: str, target: int,
                  outline: str, instruction: str, has_bib: bool,
                  reasons: Optional[Sequence[str]] = None) -> str:
    paras = max(2, target // 450)
    parts = [_PROMPT_HEAD.format(
        target=target, paras=paras,
        bibnote="" if has_bib else " (this document has no bibliography, so use no \\cite at all)")]
    parts.append(_PROMPT_SLIDE.format() if block_kind in _SLIDE_KINDS else _PROMPT_PROSE)
    if reasons:
        parts.append("\nYour previous attempt was REJECTED. Fix exactly this:\n"
                     + "\n".join(f"  - {r}" for r in reasons[:4]))
    if instruction:
        parts.append(f"\nWHAT THE USER ASKED FOR: {instruction}")
    if outline:
        parts.append(f"\nDOCUMENT OUTLINE (for consistency; do not duplicate other blocks):\n{outline}")
    parts.append(f"\nBLOCK: {block_kind} — {block_title}\nITS CURRENT CONTENT:\n{block_text}\n")
    parts.append("\nNow write only the new material to add after it:")
    return "\n".join(parts)


def _strip_fences(text: str) -> str:
    out = (text or "").strip()
    if out.startswith("```"):
        out = re.sub(r"^```[a-zA-Z]*\s*", "", out)
        out = re.sub(r"\s*```\s*$", "", out)
    return out.strip("\r\n")


def _chat(prompt: str, cancel_token: Any = None, max_tokens: int = 4000) -> str:
    from providers.router import DEFAULT_MODEL, provider_router
    resp = provider_router.chat(
        messages=[{"role": "user", "content": prompt}],
        model=DEFAULT_MODEL,
        temperature=0.4,
        max_tokens=max_tokens,
        cancel_token=cancel_token,
    )
    return _strip_fences(str(resp.get("content") or ""))


def generate_addition(block_title: str, block_kind: str, block_text: str, target: int,
                      outline: str, instruction: str, cites: set, labels: set,
                      has_bib: bool, cancel_token: Any = None) -> Tuple[Optional[str], List[str]]:
    """
    New material for one block, written and then measured.

    Returns ``(addition, reasons)``: the text that cleared every check, or
    ``None`` with the reasons the last attempt did not. Nothing is written here
    — the caller owns the transaction.
    """
    reasons: List[str] = []
    for _ in range(ELABORATE_MAX_ATTEMPTS):
        prompt = _build_prompt(block_title, block_kind, block_text, target, outline,
                               instruction, has_bib, reasons)
        try:
            addition = _chat(prompt, cancel_token, max_tokens=max(2000, target * 3))
        except Exception as err:  # noqa: BLE001 — reported, not raised
            logger.warning(f"elaborate: generation failed for {block_title!r}: {err}")
            return None, [f"the model could not be reached: {err}"]
        if not addition.strip():
            reasons = ["the reply was empty"]
            continue
        problems = check_addition(block_text, addition, target, cites, labels)
        if not problems:
            return addition, []
        reasons = problems
    return None, reasons


# ---------------------------------------------------------------------------
# Inserting it
# ---------------------------------------------------------------------------
def _outline(ws: "ShadowWorkspace", limit: int = 60) -> str:
    try:
        nodes = ws.get_nodes()
    except Exception:  # noqa: BLE001
        return ""
    rows = [f"  {n.node_id}: {n.title or n.kind}" for n in nodes
            if n.kind in ("part", "chapter", "section", "subsection", "subsubsection",
                          "frame", "page")][:limit]
    return "\n".join(rows)


def _node_text(ws: "ShadowWorkspace", node: Any) -> str:
    buf = ws.get_buffer()
    b0 = getattr(node, "body_start", None) or node.start
    b1 = getattr(node, "body_end", None) or node.end
    return buf[b0:b1]


def _compile_ok(ws: "ShadowWorkspace") -> Tuple[bool, List[str]]:
    """``(the edits introduced no errors, the errors they introduced)``."""
    try:
        from .shadow_compiler import compile_workspace
        res = compile_workspace(ws)
        if res.get("infra") or res.get("infra_skip"):
            return True, []
        errs = res.get("new_errors") or []
        if not errs:
            return True, []
        return False, [str(e.get("error") if isinstance(e, dict) else e) for e in errs[:5]]
    except Exception as err:  # noqa: BLE001 — a verification that cannot run is not a verdict
        logger.warning(f"elaborate: compile check failed: {err}")
        return True, []


def _insert(ws: "ShadowWorkspace", node_id: str, kind: str, addition: str) -> Dict[str, Any]:
    r"""
    Splice the material in without replacing anything.

    A slide's material is whole follow-up frames, which go *after* the frame; a
    prose block's goes at the end of its own body, before whatever follows it.
    Both go through the ordinary write gate.
    """
    position = "after" if kind in _SLIDE_KINDS else "end"
    return ws.insert_block(node_id, addition, position=position)


def _elaborate_one(ws: "ShadowWorkspace", node_id: str, instruction: str,
                   content: Optional[str], outline: str, cites: set, labels: set,
                   has_bib: bool, dry_run: bool, skip_compile: bool = False) -> Dict[str, Any]:
    """
    One block, start to finish: generate (or take) the material, check it,
    insert it in its own transaction, compile, and roll the insert back if the
    document stopped building or the original text did not survive.
    """
    node = ws.resolve_node(node_id)
    if node is None:
        return {"unit_id": node_id, "ok": False,
                "reason": f"no block with id '{node_id}' — call inspect_document for the ids"}
    kind = node.kind
    title = node.title or node.node_id
    before_text = _node_text(ws, node)
    target = expansion_target_delta(len(before_text), kind)

    addition, reasons = content, []
    if addition is None:
        addition, reasons = generate_addition(title, kind, before_text, target, outline,
                                              instruction, cites, labels, has_bib,
                                              getattr(ws, "_cancel_token", None))
    else:
        addition = _strip_fences(addition)
        reasons = check_addition(before_text, addition, target, cites, labels)
        if reasons:
            addition = None
    if addition is None:
        return {"unit_id": node_id, "title": title, "kind": kind, "ok": False,
                "before": len(before_text), "target": target,
                "reason": "; ".join(reasons) or "no material could be produced for this block"}

    added_visible = visible_length(addition)
    if dry_run:
        return {"unit_id": node_id, "title": title, "kind": kind, "ok": True,
                "before": len(before_text), "target": target, "added_chars": added_visible,
                "dry_run": True, "latex": addition}

    tx = ws.begin_transaction()
    res = _insert(ws, node_id, kind, addition)
    if not res.get("success"):
        ws.rollback_transaction(tx)
        return {"unit_id": node_id, "title": title, "kind": kind, "ok": False,
                "before": len(before_text), "target": target,
                "reason": f"the write gate refused the insert: {str(res.get('error'))[:200]}"}

    # Insert-only makes this true by construction; measuring it anyway is what
    # turns "cannot delete" from a claim into a check.
    after_node = ws.resolve_node(node_id)
    after_text = _node_text(ws, after_node) if after_node is not None else ws.get_buffer()
    if kind in _SLIDE_KINDS:
        after_text = after_text + "\n" + addition   # its follow-up frames are its own
    retention = measure_retention(before_text, after_text)
    if retention is not None and retention < EXPANSION_MIN_RETENTION:
        ws.rollback_transaction(tx)
        return {"unit_id": node_id, "title": title, "kind": kind, "ok": False,
                "before": len(before_text), "target": target, "retention": round(retention, 3),
                "reason": f"only {int(retention * 100)}% of the block's original wording survived "
                          "the insert, so it was rolled back"}

    # One block pays for its own compile. A forty-block call compiles once at
    # the end instead and takes back only the inserts the errors point at.
    if not skip_compile:
        ok, errs = _compile_ok(ws)
        if not ok:
            ws.rollback_transaction(tx)
            return {"unit_id": node_id, "title": title, "kind": kind, "ok": False,
                    "before": len(before_text), "target": target,
                    "reason": "the material does not compile, so it was rolled back: "
                              + "; ".join(errs[:3])}

    return {"unit_id": node_id, "title": title, "kind": kind, "ok": True,
            "before": len(before_text), "target": target, "added_chars": added_visible,
            "retention": None if retention is None else round(retention, 3),
            "lines_affected": res.get("lines_affected"),
            "auto_repairs": res.get("auto_repairs") or []}


def _selection_node(ws: "ShadowWorkspace") -> Optional[str]:
    """The block holding what the user highlighted in the editor, if anything."""
    sel = getattr(ws, "user_selection", None) or {}
    text = (sel.get("text") or "").strip()
    start_line = sel.get("start_line") or sel.get("startLine")
    if not text and not start_line:
        return None
    try:
        nodes = ws.get_nodes()
    except Exception:  # noqa: BLE001
        return None
    if start_line:
        # The innermost block containing the first selected line.
        inner = [n for n in nodes if n.start_line <= int(start_line) <= n.end_line]
        if inner:
            return min(inner, key=lambda n: n.end_line - n.start_line).node_id
    buf = ws.get_buffer()
    pos = buf.find(text[:120])
    if pos >= 0:
        inner = [n for n in nodes if n.start <= pos < n.end]
        if inner:
            return min(inner, key=lambda n: n.end - n.start).node_id
    return None


# ---------------------------------------------------------------------------
# The tool
# ---------------------------------------------------------------------------
def _unit_plan(ws: "ShadowWorkspace", args: Dict[str, Any]) -> Tuple[str, List[str], Optional[str]]:
    """``(target, node ids to elaborate, error)`` for this call."""
    node_id = (args.get("node_id") or "").strip() or None
    target = str(args.get("target") or ("section" if node_id else "")).strip().lower()

    if not target:
        if node_id:
            target = "section"
        elif _selection_node(ws):
            target = "selection"
        else:
            target = "document"

    if target in ("section", "block", "node"):
        if not node_id:
            return target, [], ("target='section' needs a node_id. Call inspect_document for the "
                                "ids, or use target='document' to elaborate every block.")
        return "section", [node_id], None

    if target == "selection":
        picked = node_id or _selection_node(ws)
        if not picked:
            return target, [], ("nothing is selected in the editor. Pass node_id, or use "
                                "target='document'.")
        return "selection", [picked], None

    units = get_expansion_units(ws.get_buffer())
    if not units:
        return "document", [], "this document has no blocks to elaborate."
    return "document", [u.unit_id for u in units][:ELABORATE_MAX_UNITS], None


def elaborate_content_tool(ws: "ShadowWorkspace", args: Dict[str, Any]) -> Dict[str, Any]:
    r"""
    Add substantive new material to one block, to the user's selection, or to
    every block of the document — without replacing any of what is there.

    The material is written for you unless ``content`` is given, and in either
    case it is measured before it is inserted (enough visible new text, not a
    restatement, no invented citation), inserted through the ordinary write
    gate, and rolled back if the document stops compiling.
    """
    target, unit_ids, err = _unit_plan(ws, args)
    if err:
        return {"error": err}

    instruction = str(args.get("instruction") or "").strip()
    content = args.get("content")
    dry_run = bool(args.get("dry_run"))
    code = ws.get_buffer()
    cites, labels = known_keys(code, getattr(ws, "_aux_files", None))
    has_bib = bool(cites)
    outline = _outline(ws)

    if content is not None and len(unit_ids) != 1:
        return {"error": "content is for one block at a time; pass a node_id with it, or omit it "
                         "and the material will be written for each block."}

    # Document order, processed last-first: an insert then shifts only the lines
    # after it, so every earlier block's reported line range stays true and a
    # faulty insert can still be found and removed.
    nodes_in_order = {n.node_id: n.start for n in ws.get_nodes()}
    unit_ids = sorted(set(unit_ids), key=lambda nid: nodes_in_order.get(nid, 0), reverse=True)

    # One block (or a dry run) is cheap enough to verify on its own.
    if len(unit_ids) == 1 or dry_run:
        rows = [_elaborate_one(ws, nid, instruction, content, outline, cites, labels,
                               has_bib, dry_run) for nid in unit_ids]
        return _report(ws, target, rows, dry_run)

    # Many blocks: write the material in parallel, insert sequentially, compile
    # once. Compiling after each of forty inserts is forty compiles for a
    # verdict the write gate has already mostly given.
    plans: List[Tuple[str, str, str, str, int]] = []
    for nid in unit_ids:
        node = ws.resolve_node(nid)
        if node is None:
            continue
        text = _node_text(ws, node)
        plans.append((nid, node.kind, node.title or nid, text,
                      expansion_target_delta(len(text), node.kind)))

    generated: Dict[str, Tuple[Optional[str], List[str]]] = {}

    def work(plan: Tuple[str, str, str, str, int]) -> None:
        nid, kind, title, text, tgt = plan
        generated[nid] = generate_addition(title, kind, text, tgt, outline, instruction,
                                           cites, labels, has_bib,
                                           getattr(ws, "_cancel_token", None))

    if plans:
        with ThreadPoolExecutor(max_workers=min(ELABORATE_CONCURRENCY, len(plans)),
                                thread_name_prefix="elaborate") as pool:
            list(pool.map(work, plans))

    rows: List[Dict[str, Any]] = []
    written: List[Tuple[str, str]] = []        # (node_id, inserted text)
    for nid, kind, title, text, tgt in plans:
        addition, reasons = generated.get(nid, (None, ["nothing was generated"]))
        if addition is None:
            rows.append({"unit_id": nid, "title": title, "kind": kind, "ok": False,
                         "before": len(text), "target": tgt,
                         "reason": "; ".join(reasons) or "no material could be produced"})
            continue
        row = _elaborate_one(ws, nid, instruction, addition, outline, cites, labels,
                             has_bib, dry_run=False, skip_compile=True)
        rows.append(row)
        if row.get("ok"):
            written.append((nid, addition))

    if written:
        ok, errs = _compile_ok(ws)
        if not ok:
            # Take back the inserts the failing compile points at, newest
            # first, and keep everything that still builds.
            removed = _drop_failing_inserts(ws, written, errs)
            for row in rows:
                if row.get("unit_id") in removed:
                    row["ok"] = False
                    row["reason"] = ("the material did not compile, so it was removed: "
                                     + "; ".join(errs[:2]))
            if removed:
                ok, errs = _compile_ok(ws)
    return _report(ws, target, rows, dry_run=False)


def _drop_failing_inserts(ws: "ShadowWorkspace", written: Sequence[Tuple[str, str]],
                          errors: Sequence[str]) -> set:
    r"""
    Remove the inserts a failing compile points at, newest first.

    Returns the node ids whose material was taken back out. An insert whose text
    the locator can no longer find (the model's own later edit changed it) is
    left alone rather than guessed at.
    """
    removed: set = set()
    for nid, text in written:
        res = ws.str_replace(old_str=text.strip("\r\n"), new_str="")
        if res.get("success"):
            removed.add(nid)
            ok, _ = _compile_ok(ws)
            if ok:
                break
        else:
            logger.info("elaborate: could not take back the insert in %s (%s)",
                        nid, str(res.get("error"))[:120])
    return removed


def _report(ws: "ShadowWorkspace", target: str, rows: List[Dict[str, Any]],
            dry_run: bool) -> Dict[str, Any]:
    done = [r for r in rows if r.get("ok")]
    failed = [r for r in rows if not r.get("ok")]
    added = sum(int(r.get("added_chars") or 0) for r in done)
    repairs: List[str] = []
    for r in done:
        for fix in (r.get("auto_repairs") or []):
            if fix not in repairs:
                repairs.append(fix)

    out: Dict[str, Any] = {
        "success": bool(done) or not rows,
        "target": target,
        "units_total": len(rows),
        "elaborated": len(done),
        "added_chars": added,
        "minimum_per_block": EXPANSION_MIN_NEW_CHARS,
        "per_unit": rows,
        "failed": [{"unit_id": r.get("unit_id"), "title": r.get("title"),
                    "reason": r.get("reason")} for r in failed],
        "document_unchanged": not done,
        "auto_repairs": repairs,
    }
    if dry_run:
        out["dry_run"] = True
        out["would_elaborate"] = len(done)
        out["message"] = (f"{len(done)} block(s) would gain at least {EXPANSION_MIN_NEW_CHARS} "
                          "characters of new material each; nothing was written.")
        return out
    if done:
        out["compile_result"] = "ok" if _compile_ok(ws)[0] else "errors"
    out["message"] = elaborate_summary(out)
    return out


def elaborate_summary(report: Dict[str, Any]) -> str:
    total = report.get("units_total") or 0
    done = report.get("elaborated") or 0
    added = report.get("added_chars") or 0
    if not total:
        return "Nothing to elaborate."
    head = (f"Elaborated {done} of {total} block(s), adding {added} characters of new text "
            f"(at least {report.get('minimum_per_block')} per block). The text that was already "
            "there is untouched.")
    failed = report.get("failed") or []
    if failed:
        named = ", ".join(f"{f.get('unit_id')} ({f.get('reason', '')[:80]})" for f in failed[:4])
        head += f" Not elaborated: {named}."
    return head


def elaborate_status_note(report: Dict[str, Any]) -> str:
    """The line that ends the run's explanation."""
    if not report or not report.get("success"):
        return ""
    total = report.get("units_total") or 0
    if not total:
        return ""
    done = report.get("elaborated") or 0
    note = (f"✓ Added {report.get('added_chars')} characters of new material to {done} of "
            f"{total} block(s); every existing sentence was kept in place.")
    failed = report.get("failed") or []
    if failed:
        note += (f" {len(failed)} block(s) were left as they were — "
                 + "; ".join(str(f.get("reason"))[:90] for f in failed[:2]) + ".")
    if report.get("compile_result") == "errors":
        note += " The document reports LaTeX errors after the additions — see the compile output."
    return note


def run_elaborate(ws: "ShadowWorkspace", instruction: str,
                  node_id: Optional[str] = None) -> Dict[str, Any]:
    """
    What an elaboration request runs, before the model's first turn.

    The request is "add substance", which is measurable; a model asked to do it
    by hand replaces the block with a reworded version of itself. The merged
    report is what the model and the user are then shown.
    """
    args: Dict[str, Any] = {"instruction": instruction}
    if node_id:
        args.update({"target": "section", "node_id": node_id})
    else:
        args["target"] = "selection" if _selection_node(ws) else "document"
    return elaborate_content_tool(ws, args)
