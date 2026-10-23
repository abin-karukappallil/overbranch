"""
prompts.py — Prompts for the editable-mode polish pass (text only: the gateway rejects images).

Exact mode's prompts (pdf2latex/prompts.py) are separate and untouched.
"""

PROMPT_VERSION = "math-2+vision-1"

MATH_SYSTEM = """You rebuild ONE displayed equation from a PDF as LaTeX maths.

You get the equation's glyphs as they sit on the page: each with its text, x position, baseline y
(larger y is lower), font size and font. Glyphs on the same baseline are one row; smaller glyphs
raised or lowered relative to their neighbours are superscripts or subscripts; a glyph much larger
than the rest is a big operator (sum, integral, product) or a delimiter; rows stacked around a
horizontal bar are a fraction.

Rules:
1. Output ONLY the maths, without $, \\[ \\], equation environments or \\tag. Nothing else: no
   prose, no explanation, no code fence.
2. Use every glyph exactly once and add no visible glyph of your own (spacing commands are fine).
3. Use standard amsmath/amssymb commands only (\\frac, \\sum, \\int, \\mathrm, \\left( \\right),
   \\alpha …). No \\newcommand, \\def, \\input, \\include, \\usepackage, \\write, \\text formatting
   tricks, colours or font-size commands.
4. Do not include the equation number; it is added separately."""

MATH_USER = """Equation glyphs (text, x, baseline_y, size, font), in reading order:
{{GLYPHS}}

The equation is {{WIDTH}}pt wide and {{HEIGHT}}pt tall.{{FEEDBACK}}"""

MATH_FEEDBACK = """

Your previous answer was rejected:
{{PREVIOUS}}
Problem: {{PROBLEM}}
Fix it and answer with the corrected maths only."""


# ---------------------------------------------------------------------------
# Vision layout: fix the size, alignment, placement and float choice of the
# figures and tables on one PDF page. Sent with the rendered page image.
# ---------------------------------------------------------------------------

VISION_LAYOUT_SYSTEM = """You correct the layout of the figures and tables on ONE PDF page so a
LaTeX reflow of the page matches the source without adding extra pages.

You get the page as an image and a JSON description of every figure/table on it: its id, bbox in
PDF points (x0, y0, x1, y1), the current width_frac (figures: fraction of \\linewidth; tables:
width_pt in points), the current alignment ("left"|"center"|"right"), a short caption excerpt,
and the ids of the two blocks before and after it in reading order.

For each figure and table, decide:
  width_frac   - fraction of \\linewidth the picture (or the whole table) should take, in [0.1, 1.0]
  align        - "left" | "center" | "right"
  float_spec   - null to keep it in flow, or "htbp" | "ht" | "H" | "!htbp" when the block is tall
                 enough that keeping it in flow would push body text onto a new page. Prefer "H"
                 (requires \\usepackage{float}; it is loaded) when the block must stay where it is,
                 "htbp" when LaTeX may choose a nearby position.
  anchor       - "unchanged" | "before" | "after": whether to move the block in reading order
  anchor_block_id - id of the neighbour it should sit before/after; only ids from "before_ids" or
                 "after_ids" are allowed, and only when ``anchor`` is "before" or "after".

Rules:
1. Output ONE JSON object only. No prose, no code fence, no markdown.
2. Schema:
   {"figures":[{"id":<int>,"width_frac":<float>,"align":<str>,"float_spec":<str|null>,
                "anchor":<str>,"anchor_block_id":<int|null>}, …],
    "tables":  [ ...same shape... ]}
3. Only include ids that appear in the input. Omit a block when nothing should change.
4. width_frac is bounded [0.1, 1.0]. align is lowercase. float_spec is one of the five values
   above, or null.
5. Do not invent extra fields. Do not include captions or image paths."""


VISION_LAYOUT_USER = """Page {{PAGE}} of {{TOTAL}}. Text area is {{TEXT_W}}pt wide by {{TEXT_H}}pt tall;
the page itself is {{PAGE_W}}x{{PAGE_H}}pt.{{BLOAT_HINT}}

Figures on this page:
{{FIGURES_JSON}}

Tables on this page:
{{TABLES_JSON}}

Return the JSON correction object described in the system prompt."""


VISION_BLOAT_HINT = """ The current LaTeX output renders this page's content across more pages
than the source; at least one block on this page is likely too tall for its position. Prefer
reducing width_frac, or promoting the heaviest block to float_spec="H" (or "htbp")."""

