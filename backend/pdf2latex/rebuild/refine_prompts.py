"""
refine_prompts.py — Prompts of the compile-repair and measure-and-correct calls (`rebuild/refine.py`).

Both calls return ONE thing: the full page body (no preamble, no \\begin{document}). Placeholders are
filled with `str.replace` (`fill`), never `str.format`, because LaTeX is full of braces.
"""

COMPILE_FIX_SYSTEM = r"""You fix LaTeX compile errors in ONE page body of a XeLaTeX document.

The preamble is fixed and already compiles; you only ever see and return the page BODY: the text
that sits between \begin{document} and \end{document}.

Rules:
- Return the full corrected body and nothing else: no explanations, no Markdown fences, no
  \documentclass, \usepackage, \begin{document} or \end{document}.
- Fix ONLY what the errors point at. Change nothing else: same structure, same spacing commands,
  same order.
- Keep every word of the text exactly as it is. Escape special characters (& % $ # _ { } ~ ^ \)
  when they are meant as text instead of deleting them.
- Keep every \includegraphics and its file name exactly as written.
- Do not use packages the preamble does not load; prefer plain LaTeX constructs.
"""

COMPILE_FIX_USER = r"""The page body below does not compile. Errors (line numbers are BODY lines; ">>" marks the line
the error points at):

{{ERRORS}}

Packages the preamble loads: {{PACKAGES}}

Page body:
{{BODY}}

Return the full corrected body only."""


CORRECT_SYSTEM = r"""You improve ONE page body of a XeLaTeX document so that, compiled, it looks like the original
PDF page as closely as possible.

You get the current body, and a measured mismatch report comparing its compiled output with the
original page (positions in pt from the page's top-left corner).

Rules:
- Return the full corrected body and nothing else: no explanations, no Markdown fences, no
  \documentclass, \usepackage, \begin{document} or \end{document}.
- Keep every word of the source verbatim; add back missing words exactly where they belong and
  remove words that are not in the source. Do not invent content.
- The body must fill exactly ONE page: if the report says it overflows, tighten vertical space,
  font sizes of large elements or figure sizes until it fits.
- Use only these image files, spelled exactly: {{FILES}}. Never reference any other file.
- Fix what the report lists, and keep everything that already matches as it is.
- Do not use packages the preamble does not load.
"""

CORRECT_USER = r"""Mismatch report (compiled output vs the original page {{PAGE}}, {{WIDTH}}x{{HEIGHT}} pt):

{{REPORT}}

Packages the preamble loads: {{PACKAGES}}
{{IMAGES_NOTE}}
Current page body:
{{BODY}}

Return the full corrected body only."""

IMAGES_NOTE = ("Two images are attached: first the ORIGINAL page, then the CURRENT compiled output of the body "
               "below. Compare them alongside the report.\n")


def fill(template: str, **values: str) -> str:
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", str(value))
    return template
