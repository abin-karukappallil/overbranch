"""
document.py — how a preamble and page bodies become a compilable document.

One source page is one output page. Every body starts after `\\obpagestart{n}` (the preamble defines
it: sets the page counter to n, drops `\\label{ob-src-n}`, and writes `ob-out-n` holding the physical
page, which is what lets the packager read back where each source page landed) and ends with `\\clearpage`, so a short page cannot pull the next one up.
The preamble ends before `\\begin{document}` and contains no body text.
"""

from typing import Iterable, Tuple

ASSET_ROOT = "assets"


def standalone_page(preamble: str, body: str, n: int) -> str:
    """A one-page document: the preamble plus source page `n`'s body (compiled to measure that page alone)."""
    return f"{preamble.rstrip()}\n\\begin{{document}}\n\\obpagestart{{{n}}}\n{body.strip()}\n\\clearpage\n\\end{{document}}\n"


def merged_document(preamble: str, bodies: Iterable[Tuple[int, str]]) -> str:
    """The whole document: bodies in page order, each followed by \\clearpage."""
    parts = [preamble.rstrip(), "\\begin{document}"]
    for n, body in sorted(bodies, key=lambda nb: nb[0]):
        parts += [f"\\obpagestart{{{n}}}", body.strip(), "\\clearpage"]
    parts.append("\\end{document}")
    return "\n".join(parts) + "\n"
