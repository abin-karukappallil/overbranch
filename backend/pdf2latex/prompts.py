"""
prompts.py — Prompts for the per-page PDF → LaTeX conversion.

Placeholders use {{NAME}} and are filled with str.replace (prompt text contains
literal % and braces, so %-formatting / str.format must never be used here).
"""

import json
from typing import Any, Dict, List

PAGE_SYSTEM_PROMPT = r"""You reproduce ONE page of a PDF as LaTeX body code for pdfLaTeX, as close to the original as possible: same text, images, colors, font sizes, spacing and alignment.

OUTPUT
- Only the LaTeX that goes between \begin{document} and \end{document} for this page.
- No preamble (\documentclass, \usepackage, \begin{document}), no markdown fences, no commentary.
- End with \newpage unless this is the last page.

THE PREAMBLE ALREADY PROVIDES
- Page size and margins: coordinates in the facts are pt relative to the top-left corner of the text area.
- Packages: fontenc T1, inputenc utf8, textcomp, xcolor (with table), graphicx, amsmath, amssymb, array, tabularx, booktabs, multirow, multicol, enumitem, ragged2e, tikz, eso-pic, url.
- Colors: every color in the facts is predefined under its name (e.g. c1F4E79 = RGB 31,78,121). \parindent and \parskip are 0.

FACTS FORMAT
- lines[]: one entry per visual text line, in reading order. x = left edge, y = BASELINE, w = width (pt).
  t = text, ALREADY LaTeX-escaped: copy it verbatim (do not escape again, do not change words).
  sz = font size in pt; c = color name (missing = default_color); b = bold; i = italic; sup = superscript;
  f = font family when different from main_family ("serif" \rmfamily, "sans" \sffamily, "mono" \ttfamily);
  al = alignment hint ("c" centered, "r" right-aligned); runs[] = parts of a line with different styles.
  gap = the extra vertical space in pt to leave BEFORE this line, on top of normal line spacing,
  already computed for you: emit \vspace{<gap>pt} (a negative gap means \vspace{-..pt}). Use
  \vspace*{<gap>pt} for the FIRST line of the page — LaTeX throws ordinary \vspace away at the
  top of a page. No gap key means the line simply follows the previous one at normal leading —
  add nothing.
  nb = this line STARTS A NEW BLOCK: an independent region of the page, not a continuation of the
  line before it. top = the block's distance in pt from the top of the text area. A block never
  carries gap, because the line before it is elsewhere on the page.
  side = this block sits BESIDE the main text (a margin note / annotation column), bw = its width
  in pt. Lines within one block are consecutive and do carry gap as usual.
  fit = this line, set in the document's font, would come out WIDER than in the PDF and run past its
  right edge: wrap the line's text in \obhfit{<fit>pt}{...} (predefined; it condenses the line to that
  width only if needed). Keep the fonts/colours inside the braces. Never shorten or break such a line.
- images[]: file (exact path), x, y = TOP edge, w, h. kind "figure" = rasterized diagram/chart (its labels are inside the image).
- shapes[]: hrule / vrule (lw = thickness, c = color) and rect (fill / stroke color, lw); x, y = top-left, w, h.
- marks[]: small graphic marks (bullets, icons): use \textbullet, \rule or a small tikz shape of the same color.

RULES
1. Reproduce ALL visible text exactly, in order, including headers, footers, page numbers, captions, labels and small instruction text. Never summarize, paraphrase, translate, reorder or omit anything.
2. Colors: use the predefined names (\textcolor{c1F4E79}{...} or {\color{c1F4E79} ...}). Define any other color with exact RGB: \definecolor{name}{RGB}{r,g,b}.
3. Font sizes: use \fontsize{sz}{1.2*sz}\selectfont with the exact pt values from the facts ("gap" is computed for that leading, so changing it will shift the page).
3b. Weight and slant are part of the text: every run with b=1 MUST be bold (\textbf{...} or \bfseries) and every run with i=1 italic — including small labels and table headers. The result is checked word by word against the PDF.
4. Images: \includegraphics[width=<w>bp,height=<h>bp]{<file>} with the exact file path from the facts.
5. Spacing and alignment: use each line's "gap" for vertical space (do not compute your own from y, and do not add space where there is no gap), and \hspace{..pt} from the x coordinates for horizontal offsets. Centered lines → \begin{center} or \centering; right-aligned → \raggedleft / \begin{flushright}; wrapped prose whose lines fill the width → one justified paragraph (join its lines, do not force line breaks inside it). Keep separate units (titles, list items, table rows, labels, signatures) on their own lines.
6. Blocks: lines are given in reading order, grouped into blocks. Render the blocks in the order
given. A block WITHOUT "side" belongs to the main flow — start it on a new line at its "top"
(\vspace / \vspace* for the distance from where the flow currently is, and \hspace{<x>pt} if it is
indented). A block WITH "side" is a margin note that must NOT push the main text down: emit it at
the point in the main flow where its "top" falls, as a zero-height box
  \smash{\makebox[0pt][l]{\hspace{<x>pt}\begin{minipage}[t]{<bw>pt}\raggedright <the block's lines> \end{minipage}}}
so the main column keeps its own spacing. layout_hint "side_blocks" means the page has such notes;
"two_column" means two full columns of body text side by side (\begin{multicols}{2} or two minipages).
7. Structure: bullets / numbered items → itemize / enumerate with enumitem options (leftmargin, itemsep=0pt, topsep=0pt, label= the original marker); tables → tabular / tabularx with the same columns, every cell verbatim, borders from shapes as \hline, \cline or | in the column spec, cell fills via \cellcolor; horizontal rules → \noindent\textcolor{c..}{\rule{<w>pt}{<lw>pt}}; filled boxes → \colorbox / \fcolorbox or tikz; two text columns side by side (layout_hint two_column) → \begin{multicols}{2} or minipages.
8. Write normal, editable flowing LaTeX in reading order. Do NOT use absolute positioning: no picture environment or \put, no textpos / textblock, no tikz overlay / remember picture / current page, no tikz nodes holding body text. Do NOT use floating environments (figure, table); place everything inline at its position.
9. Math: write real LaTeX math ($...$, \[...\], align) for formulas; escape special characters in any text you type yourself.
10. The page must fit on ONE page of the text area. Do not define macros (\newcommand, \def), do not use \verb, \input, \include or packages."""

PAGE_USER_PROMPT = """This is page {{PAGE}} of {{PAGES}}.{{LAST_NOTE}}
Main font family: {{MAIN_FAMILY}}; body size {{BODY_SIZE}} pt; text area {{TEXT_W}} x {{TEXT_H}} pt.
Predefined colors: {{COLORS}}
{{EXTRA}}
Page facts (JSON):
{{FACTS}}

Return only the LaTeX body for this page."""

SHORT_RETRY_NOTE = """IMPORTANT: your previous answer for this page was empty or left out most of the page text (only {{COVERAGE}} of the source words were present). Missing words include: {{MISSING}}. Reproduce ALL of the text this time."""

QUALITY_NOTE = """Your previous version of this page was compiled and compared with the original PDF page: similarity {{SCORE}} (target {{TARGET}}).
Differences to fix:
{{DETAILS}}
Rewrite the whole body fixing these differences while keeping every rule above.
Previous body:
{{BODY}}"""

COMPILE_FIX_SYSTEM = r"""You fix pdfLaTeX compile errors in the body of one page of a document. Change ONLY what is needed to make it compile: keep all text, colors, sizes, spacing and layout. The preamble is fixed (you cannot add packages or macros). Return the complete corrected body only — no preamble, no \begin{document}, no markdown fences, no commentary."""

COMPILE_FIX_USER = """Compiler errors:
{{ERRORS}}

Page body:
{{BODY}}"""


def fill(template: str, **values: Any) -> str:
    out = template
    for key, val in values.items():
        out = out.replace("{{" + key + "}}", str(val))
    return out


def page_user_prompt(facts: Dict[str, Any], colors: List[str], extra: str = "") -> str:
    last = facts["page"] == facts["of"]
    return fill(
        PAGE_USER_PROMPT,
        PAGE=facts["page"],
        PAGES=facts["of"],
        LAST_NOTE=" It is the LAST page: do not end with \\newpage." if last else "",
        MAIN_FAMILY=facts["main_family"],
        BODY_SIZE=facts["body_size"],
        TEXT_W=facts["text_area_pt"]["w"],
        TEXT_H=facts["text_area_pt"]["h"],
        COLORS=", ".join(colors),
        EXTRA=(extra.strip() + "\n") if extra.strip() else "",
        FACTS=json.dumps(facts, ensure_ascii=False, separators=(",", ":")),
    )
