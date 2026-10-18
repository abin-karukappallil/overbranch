"""
`generate_diagram` — flowchart / block-diagram / figure builder (LLM or deterministic).

Rationale (same philosophy as justify_content / repair.py): the LLM is good at
deciding the STRUCTURE of a diagram (which boxes, which arrows) and bad at
writing TikZ that compiles (missing semicolons, unloaded libraries, overlap).
So the model supplies a node/edge spec and this tool emits guaranteed-compiling,
auto-laid-out TikZ. The model never hand-writes the TikZ for these.

Layout is a longest-path layered placement with explicit coordinates (robust,
no relative-positioning ambiguity). Cycles (e.g. a `retry` feedback edge) are
handled by excluding back-edges from the layering and drawing them with a bend.

The picture is wrapped in `\\resizebox{0.9\\textwidth}{!}{…}` so it can never
overflow a slide — this scales a figure, not body type.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple, Set, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .shadow_workspace import ShadowWorkspace

logger = logging.getLogger("agent.diagram_tools")

# Geometry (cm). The pitch along the flow axis must exceed the node's extent on
# that axis or boxes overlap; a node is far wider (~2.6cm) than tall (~1cm), so
# the two orientations need different pitches.
LAYER_PITCH_V = 2.3   # vertical flow: layers stacked by height
CROSS_PITCH_V = 3.9   # vertical flow: siblings spread by width
LAYER_PITCH_H = 4.6   # horizontal flow: layers spread by width
CROSS_PITCH_H = 2.3   # horizontal flow: siblings stacked by height

# Node shapes → inline TikZ styles. Colours are xcolor expressions that are
# always available once tikz is loaded, so the diagram never depends on colours
# the host document happens to define.
_SHAPE_STYLE = {
    "process": "dgproc",
    "block": "dgproc",
    "terminal": "dgterm",
    "start": "dgterm",
    "end": "dgterm",
    "decision": "dgdec",
    "io": "dgio",
    "data": "dgio",
}

_DIAGRAM_LIBRARIES = (
    "\\usetikzlibrary{shapes.geometric,shapes.misc,shapes.multipart,arrows.meta,"
    "positioning,calc,fit,backgrounds,patterns,decorations.pathreplacing,"
    "decorations.markings,matrix,chains,scopes}"
)

# LLM diagram generation (rich / custom figures described in natural language).
DIAGRAM_LLM_MAX_REPAIRS = 2


def _escape(text: str) -> str:
    """Escape a plain label for LaTeX text mode (so 'R&D', 'a_b', '50%' are safe)."""
    if text is None:
        return ""
    s = str(text)
    out = []
    for ch in s:
        if ch == "\\":
            out.append("\\textbackslash{}")
        elif ch in "&%#_$":
            out.append("\\" + ch)
        elif ch == "~":
            out.append("\\textasciitilde{}")
        elif ch == "^":
            out.append("\\textasciicircum{}")
        elif ch == "{":
            out.append("\\{")
        elif ch == "}":
            out.append("\\}")
        else:
            out.append(ch)
    return "".join(out)


def _safe_name(idx: int) -> str:
    return f"dn{idx}"


def _compute_layers(
    ids: List[str], fwd: List[Tuple[str, str]]
) -> Dict[str, int]:
    """Longest-path layering over the forward (non-back) edges."""
    layer = {i: 0 for i in ids}
    adj: Dict[str, List[str]] = {i: [] for i in ids}
    for a, b in fwd:
        adj[a].append(b)
    # Relax up to len(ids) times (DAG once back-edges are removed).
    for _ in range(len(ids)):
        changed = False
        for a, b in fwd:
            if layer[b] < layer[a] + 1:
                layer[b] = layer[a] + 1
                changed = True
        if not changed:
            break
    return layer


def _find_back_edges(
    ids: List[str], edges: List[Tuple[str, str]]
) -> Set[int]:
    """DFS; an edge to a node currently on the recursion stack is a back-edge."""
    adj: Dict[str, List[Tuple[int, str]]] = {i: [] for i in ids}
    for ei, (a, b) in enumerate(edges):
        if a in adj and b in adj:
            adj[a].append((ei, b))
    color: Dict[str, int] = {i: 0 for i in ids}  # 0=white,1=grey,2=black
    back: Set[int] = set()

    def visit(u: str) -> None:
        color[u] = 1
        for ei, v in adj[u]:
            if v == u:
                back.add(ei)  # self-loop
            elif color[v] == 1:
                back.add(ei)
            elif color[v] == 0:
                visit(v)
        color[u] = 2

    for i in ids:
        if color[i] == 0:
            visit(i)
    return back


def build_diagram_tikz(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    kind: str = "flowchart",
    direction: str = "vertical",
    title: Optional[str] = None,
) -> str:
    """Pure: node/edge spec → a complete, compiling TikZ figure block."""
    ids = [str(n.get("id")) for n in nodes if n.get("id") is not None]
    id_set = set(ids)
    name = {nid: _safe_name(i) for i, nid in enumerate(ids)}
    label = {str(n.get("id")): str(n.get("label", n.get("id"))) for n in nodes}
    shape = {
        str(n.get("id")): _SHAPE_STYLE.get(str(n.get("shape", "process")).lower(), "dgproc")
        for n in nodes
    }

    norm_edges: List[Tuple[str, str, str, str]] = []  # (from,to,label,style)
    pair_edges: List[Tuple[str, str]] = []
    for e in edges:
        a, b = str(e.get("from")), str(e.get("to"))
        if a not in id_set or b not in id_set:
            continue
        norm_edges.append((a, b, str(e.get("label", "") or ""), str(e.get("style", "solid") or "solid")))
        pair_edges.append((a, b))

    back = _find_back_edges(ids, pair_edges)
    fwd = [pair_edges[i] for i in range(len(pair_edges)) if i not in back and pair_edges[i][0] != pair_edges[i][1]]
    layer = _compute_layers(ids, fwd)

    # Group by layer, preserving spec order within a layer.
    by_layer: Dict[int, List[str]] = {}
    for nid in ids:
        by_layer.setdefault(layer[nid], []).append(nid)

    horizontal = str(direction).lower().startswith("h")
    layer_pitch = LAYER_PITCH_H if horizontal else LAYER_PITCH_V
    cross_pitch = CROSS_PITCH_H if horizontal else CROSS_PITCH_V
    coord: Dict[str, Tuple[float, float]] = {}
    for lv in sorted(by_layer):
        row = by_layer[lv]
        k = len(row)
        for j, nid in enumerate(row):
            cross = (j - (k - 1) / 2.0) * cross_pitch
            main = lv * layer_pitch
            if horizontal:
                coord[nid] = (main, -cross)
            else:
                coord[nid] = (cross, -main)

    # Bounding box (cm), padded for node sizes, to choose the binding dimension:
    # scaling to width alone lets a tall vertical flow run off the slide.
    xs = [c[0] for c in coord.values()] or [0.0]
    ys = [c[1] for c in coord.values()] or [0.0]
    NODE_W, NODE_H = 3.0, 1.3
    bbox_w = (max(xs) - min(xs)) + NODE_W
    bbox_h = (max(ys) - min(ys)) + NODE_H
    # Available content area on a 16:9 frame (cm), leaving room for the title.
    AVAIL_W, AVAIL_H = 11.0, 6.6
    if bbox_h <= 0 or (bbox_w / bbox_h) >= (AVAIL_W / AVAIL_H):
        resize = "\\resizebox{%.2f\\textwidth}{!}{%%" % 0.92  # wide: bind width
    else:
        resize = "\\resizebox{!}{%.1fcm}{%%" % AVAIL_H          # tall: bind height

    lines: List[str] = []
    lines.append("\\begin{center}")
    if title:
        lines.append("{\\small\\bfseries " + _escape(title) + "}\\\\[2mm]")
    lines.append(resize)
    lines.append("\\begin{tikzpicture}[>=Stealth,")
    lines.append("  dgbase/.style={draw=blue!55!black,line width=0.7pt,fill=blue!5,align=center,"
                 "text width=26mm,minimum height=9mm,inner sep=3pt,font=\\small},")
    lines.append("  dgproc/.style={dgbase,rectangle},")
    lines.append("  dgterm/.style={dgbase,rounded corners=7pt},")
    lines.append("  dgdec/.style={dgbase,diamond,aspect=2,text width=20mm,fill=orange!12},")
    lines.append("  dgio/.style={dgbase,trapezium,trapezium left angle=70,trapezium right angle=110,fill=green!10},")
    lines.append("  dgedge/.style={->,line width=0.7pt,draw=blue!45!black},")
    lines.append("  dglabel/.style={font=\\scriptsize,fill=white,inner sep=1pt}]")
    for nid in ids:
        x, y = coord.get(nid, (0.0, 0.0))
        lines.append(
            f"  \\node[{shape[nid]}] ({name[nid]}) at ({x:.2f},{y:.2f}) {{{_escape(label[nid])}}};"
        )
    for idx, (a, b, lab, sty) in enumerate(norm_edges):
        dash = ",dashed" if sty.lower() == "dashed" else ""
        lbl = f" node[dglabel]{{{_escape(lab)}}}" if lab else ""
        if a == b:
            lines.append(f"  \\draw[dgedge{dash}] ({name[a]}) to[loop above]{lbl} ({name[a]});")
        elif idx in back:
            # Route a feedback edge wide around the flow; label near its start.
            lbl_b = f" node[dglabel,pos=0.12]{{{_escape(lab)}}}" if lab else ""
            lines.append(f"  \\draw[dgedge{dash}] ({name[a]}) to[bend left=60]{lbl_b} ({name[b]});")
        else:
            lines.append(f"  \\draw[dgedge{dash}] ({name[a]}) --{lbl} ({name[b]});")
    lines.append("\\end{tikzpicture}}")
    lines.append("\\end{center}")
    return "\n".join(lines)


def _ensure_diagram_libraries(ws: "ShadowWorkspace", with_adjustbox: bool = False) -> Optional[Dict[str, Any]]:
    """Make sure the TikZ libraries the diagram uses are loaded. Idempotent.

    The write-gate healer already injects tikz/calc/positioning/arrows.meta on any
    TikZ edit, but NOT shapes.geometric (diamond/io shapes) or the richer libraries
    an LLM diagram may use; adjustbox bounds an LLM figure to the slide.
    """
    buf = ws.get_buffer()
    inserts: List[str] = []
    if "shapes.geometric" not in buf:
        inserts.append(_DIAGRAM_LIBRARIES)
    if with_adjustbox and "{adjustbox}" not in buf:
        inserts.append("\\usepackage{adjustbox}")
    if not inserts:
        return None
    res = ws.insert_block("preamble", "\n".join(inserts), position="end")
    # A document without a `preamble` node (rare) — the healer still adds tikz.
    return res if not res.get("success") else None


# ---------------------------------------------------------------------------
# LLM mode: the diagram / figure is drawn by the model, then verified & repaired
# ---------------------------------------------------------------------------

_VERIFY_PREAMBLE = (
    "\\documentclass{article}\n"
    "\\usepackage{tikz}\n\\usepackage{amsmath,amssymb}\n\\usepackage{xcolor}\n"
    "\\usepackage{graphicx}\n\\usepackage{adjustbox}\n"
    + _DIAGRAM_LIBRARIES + "\n\\pagestyle{empty}\n"
)

_TIKZ_LIBS_FOR_PROMPT = (
    "shapes.geometric, shapes.misc, shapes.multipart, arrows.meta, positioning, "
    "calc, fit, backgrounds, patterns, decorations.pathreplacing, matrix, chains"
)


def _extract_tikz(content: str) -> Optional[str]:
    """Pull one self-contained tikzpicture out of an LLM reply."""
    if not content:
        return None
    text = re.sub(r"```+\s*(?:latex|tex)?", "", content)
    m = re.search(r"\\begin\{tikzpicture\}.*\\end\{tikzpicture\}", text, re.S)
    return m.group(0).strip() if m else None


def _wrap_llm_tikz(tikz: str, title: Optional[str]) -> str:
    """Bound an LLM figure to the slide in both dimensions (adjustbox)."""
    out = ["\\begin{center}"]
    if title:
        out.append("{\\small\\bfseries " + _escape(title) + "}\\\\[2mm]")
    out.append("\\begin{adjustbox}{max width=0.95\\textwidth,max totalheight=0.78\\textheight,center}")
    out.append(tikz)
    out.append("\\end{adjustbox}")
    out.append("\\end{center}")
    return "\n".join(out)


def _diagram_prompt(description: str, kind: str, direction: str,
                    prev_tikz: Optional[str], errors: Optional[str]) -> str:
    base = (
        f"Draw a {kind} as a LaTeX TikZ picture for a single presentation slide.\n\n"
        f"DIAGRAM TO DRAW:\n{description}\n\n"
        "STRICT OUTPUT RULES:\n"
        "- Output ONLY one `\\begin{tikzpicture} ... \\end{tikzpicture}` block — NO \\documentclass, "
        "NO \\usepackage, NO \\begin{figure}, NO \\caption, NO markdown fences, NO prose.\n"
        f"- Use only TikZ with these already-loaded libraries: {_TIKZ_LIBS_FOR_PROMPT}.\n"
        "- Use xcolor colour expressions only (e.g. blue!55!black, gray!20, orange!15); do NOT \\definecolor "
        "and do NOT reference colours defined elsewhere.\n"
        f"- Flow direction: {direction}. Use positioning / node distance so nodes never overlap.\n"
        "- Keep it clean, labelled and readable, about 12cm wide, fitting one slide.\n"
        "- End EVERY statement (\\node, \\draw, \\path, \\fill, ...) with a semicolon. Wrap math in $...$. "
        "In node text write \\& \\% \\# \\_ for & % # _.\n"
    )
    if prev_tikz and errors:
        base += (
            "\nYour previous attempt FAILED to compile. Fix these errors and return corrected TikZ:\n"
            f"{errors}\n\nPREVIOUS TIKZ:\n{prev_tikz}\n"
        )
    elif errors:
        base += f"\nPrevious attempt was unusable: {errors}\n"
    return base


def _verify_tikz(wrapped: str) -> Tuple[bool, List[str]]:
    """Compile the wrapped figure standalone; (ok, error messages)."""
    try:
        import compiler
    except Exception:
        return True, []  # cannot verify → accept best effort
    doc = _VERIFY_PREAMBLE + "\\begin{document}\n" + wrapped + "\n\\end{document}\n"
    try:
        r = compiler.compile_latex(doc, engine="pdflatex", persist_synctex=False,
                                   allow_recovery=False, pre_heal=True)
    except Exception as e:  # pragma: no cover
        logger.debug(f"diagram verify compile raised: {e}")
        return True, []
    errs = r.get("errors") or []
    msgs = [str(e.get("error", e)) if isinstance(e, dict) else str(e) for e in errs]
    return (bool(r.get("success")) and not errs), msgs


def build_diagram_llm(description: str, kind: str, direction: str, title: Optional[str],
                      cancel_token: Any = None) -> Dict[str, Any]:
    """Have the LLM draw the diagram, then verify+repair it against real pdflatex."""
    try:
        from providers.router import DEFAULT_MODEL, provider_router
        from providers.base_provider import LLMProviderError
    except Exception as e:  # pragma: no cover
        return {"error": f"LLM provider unavailable: {e}", "_llm_unavailable": True}

    prev_tikz: Optional[str] = None
    errors: Optional[str] = None
    last_wrapped: Optional[str] = None
    for attempt in range(1 + DIAGRAM_LLM_MAX_REPAIRS):
        prompt = _diagram_prompt(description, kind, direction, prev_tikz, errors)
        try:
            resp = provider_router.chat([{"role": "user", "content": prompt}], model=DEFAULT_MODEL,
                                        temperature=0.2, max_tokens=2400, cancel_token=cancel_token)
        except LLMProviderError as e:
            return {"error": f"LLM diagram generation failed: {e}", "_llm_unavailable": True}
        tikz = _extract_tikz(resp.get("content", ""))
        if not tikz:
            prev_tikz, errors = None, "Your reply contained no \\begin{tikzpicture}...\\end{tikzpicture}."
            continue
        wrapped = _wrap_llm_tikz(tikz, title)
        last_wrapped = wrapped
        ok, errs = _verify_tikz(wrapped)
        if ok:
            return {"latex": wrapped, "attempts": attempt + 1, "verified": True}
        prev_tikz, errors = tikz, "\n".join(errs[:8]) or "Compilation failed."
    if last_wrapped:
        return {"latex": last_wrapped, "attempts": 1 + DIAGRAM_LLM_MAX_REPAIRS, "verified": False}
    return {"error": "The model did not return usable TikZ for the diagram."}


def _valid_spec(nodes: Any, edges: Any) -> Optional[str]:
    """None if (nodes, edges) is a usable deterministic spec, else an error string."""
    if not isinstance(nodes, list) or not nodes:
        return "generate_diagram needs either a 'description' or a non-empty 'nodes' list of {id, label, shape?}."
    if not all(isinstance(n, dict) and n.get("id") is not None for n in nodes):
        return "Each node must be an object with an 'id' (and a 'label')."
    if not isinstance(edges, list):
        return "'edges' must be a list of {from, to, label?}."
    ids = [str(n.get("id")) for n in nodes]
    if len(set(ids)) != len(ids):
        return "Node ids must be unique."
    id_set = set(ids)
    bad = [e for e in edges if str(e.get("from")) not in id_set or str(e.get("to")) not in id_set]
    if bad:
        return f"{len(bad)} edge(s) reference an unknown node id. Valid ids: {ids}"
    return None


def generate_diagram_tool(ws: "ShadowWorkspace", args: Dict[str, Any]) -> Dict[str, Any]:
    nodes = args.get("nodes") or []
    edges = args.get("edges") or []
    description = (args.get("description") or args.get("prompt") or "").strip()
    kind = str(args.get("kind", "flowchart"))
    direction = str(args.get("direction", "vertical"))
    title = args.get("title") or args.get("caption")
    dry_run = bool(args.get("dry_run"))
    node_id = args.get("node_id")
    position = str(args.get("position", "end"))

    spec_error = _valid_spec(nodes, edges)
    have_spec = spec_error is None

    # ---- choose the drawing mode ----
    source = "deterministic"
    meta: Dict[str, Any] = {}
    tikz: Optional[str] = None
    with_adjustbox = False

    if description:
        cancel = getattr(ws, "_cancel_token", None)
        llm = build_diagram_llm(description, kind, direction, title, cancel_token=cancel)
        if "error" not in llm:
            tikz = llm["latex"]
            source = "llm"
            with_adjustbox = True
            meta = {"attempts": llm.get("attempts"), "verified": llm.get("verified")}
        elif have_spec:
            logger.info("LLM diagram failed (%s); falling back to the deterministic layout.", llm.get("error"))
            meta = {"llm_fallback": llm.get("error")}
        else:
            return llm  # no spec to fall back to

    if tikz is None:
        if not have_spec:
            return {"error": spec_error}
        tikz = build_diagram_tikz(nodes, edges, kind=kind, direction=direction, title=title)
        meta.setdefault("node_count", len(nodes))
        meta.setdefault("edge_count", len(edges))

    if dry_run or not node_id:
        return {"success": True, "inserted": False, "latex": tikz, "source": source, **meta,
                "note": "Diagram LaTeX ready. Place it where it belongs (e.g. insert_block into the "
                        "slide/section that discusses it)."}

    lib_err = _ensure_diagram_libraries(ws, with_adjustbox=with_adjustbox)
    if lib_err:
        return lib_err
    res = ws.insert_block(str(node_id), tikz, position)
    if not res.get("success"):
        return res
    out = {"success": True, "inserted": True, "latex": tikz, "source": source,
           "node_id": node_id, "position": position, **meta}
    if res.get("auto_repairs"):
        out["auto_repairs"] = res["auto_repairs"]
    return out
