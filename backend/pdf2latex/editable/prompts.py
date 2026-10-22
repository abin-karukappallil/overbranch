"""
prompts.py — Prompts for the editable-mode polish pass (text only: the gateway rejects images).

Exact mode's prompts (pdf2latex/prompts.py) are separate and untouched.
"""

PROMPT_VERSION = "math-2"

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
