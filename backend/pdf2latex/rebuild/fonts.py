"""
fonts.py — Source font families → INSTALLED XeLaTeX (fontspec) fonts, for the preamble call.

Each family the layout reports (`block["font"]["family"]`, e.g. "Calibri", "Helvetica", "Times") is
mapped to the closest font this machine really has: metric-compatible first (Calibri → Carlito,
Cambria → Caladea, Arial/Helvetica → Liberation Sans, Times → Liberation Serif, Courier → Liberation
Mono, Georgia → Gelasio), then the closest serif/sans/mono by `fontmap.editable_font` (read-only).

A font counts as installed when fontconfig lists the family (`fc-list`, loaded by name) or when
kpathsea finds its files in the TeX tree (`kpsewhich`, loaded by file name: XeTeX only finds TeX-tree
fonts by name when fontconfig was told about them, which a stock TeX Live is not). `FontChoice.fontspec`
is the exact argument string to use, so the model never guesses a font name. Both lookups run once per
process (cached). A font that is in neither list is never offered.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import PurePath
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from ..fontmap import editable_font
from .model import PageLayout

logger = logging.getLogger("pdf2latex.rebuild.fonts")

_TOOL_TIMEOUT_S = 30


@dataclass(frozen=True)
class _Face:
    """One installable family: its fontconfig name and its TeX-tree files (regular, bold, italic, bold italic)."""
    name: str
    generic: str                  # "serif" | "sans" | "mono"
    files: Tuple[str, str, str, str] = ("", "", "", "")


def _quad(stem: str, ext: str,
          styles: Sequence[str] = ("Regular", "Bold", "Italic", "BoldItalic")) -> Tuple[str, str, str, str]:
    return tuple(f"{stem}{s}.{ext}" for s in styles)  # type: ignore[return-value]


_GYRE = ("-regular", "-bold", "-italic", "-bolditalic")

FACES: Dict[str, _Face] = {f.name: f for f in (
    _Face("Carlito", "sans", _quad("Carlito-", "ttf")),
    _Face("Caladea", "serif", _quad("Caladea-", "ttf")),
    _Face("Liberation Sans", "sans", _quad("LiberationSans-", "ttf")),
    _Face("Liberation Serif", "serif", _quad("LiberationSerif-", "ttf")),
    _Face("Liberation Mono", "mono", _quad("LiberationMono-", "ttf")),
    _Face("Arimo", "sans", _quad("Arimo-", "ttf")),
    _Face("Tinos", "serif", _quad("Tinos-", "ttf")),
    _Face("Cousine", "mono", _quad("Cousine-", "ttf")),
    _Face("Nimbus Sans", "sans"),
    _Face("Nimbus Roman", "serif"),
    _Face("Nimbus Mono PS", "mono"),
    _Face("TeX Gyre Heros", "sans", _quad("texgyreheros", "otf", _GYRE)),
    _Face("TeX Gyre Termes", "serif", _quad("texgyretermes", "otf", _GYRE)),
    _Face("TeX Gyre Cursor", "mono", _quad("texgyrecursor", "otf", _GYRE)),
    _Face("TeX Gyre Pagella", "serif", _quad("texgyrepagella", "otf", _GYRE)),
    _Face("TeX Gyre Schola", "serif", _quad("texgyreschola", "otf", _GYRE)),
    _Face("TeX Gyre Bonum", "serif", _quad("texgyrebonum", "otf", _GYRE)),
    _Face("TeX Gyre Adventor", "sans", _quad("texgyreadventor", "otf", _GYRE)),
    _Face("Gelasio", "serif", _quad("Gelasio-", "otf")),
    _Face("EB Garamond", "serif", _quad("EBGaramond-", "otf")),
    _Face("Libertinus Serif", "serif", _quad("LibertinusSerif-", "otf")),
    _Face("Libertinus Sans", "sans", ("LibertinusSans-Regular.otf", "LibertinusSans-Bold.otf",
                                      "LibertinusSans-Italic.otf", "")),
    _Face("Roboto", "sans", _quad("Roboto-", "otf")),
    _Face("Open Sans", "sans", _quad("OpenSans-", "ttf")),
    _Face("Lato", "sans", _quad("Lato-", "ttf")),
    _Face("Source Sans Pro", "sans", _quad("SourceSansPro-", "otf", ("Regular", "Bold", "RegularIt", "BoldIt"))),
    _Face("Source Serif Pro", "serif", _quad("SourceSerifPro-", "otf", ("Regular", "Bold", "RegularIt", "BoldIt"))),
    _Face("Fira Sans", "sans", _quad("FiraSans-", "otf")),
    _Face("Noto Sans", "sans", _quad("NotoSans-", "ttf")),
    _Face("Noto Serif", "serif", _quad("NotoSerif-", "ttf")),
    _Face("DejaVu Sans", "sans", ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans-Oblique.ttf",
                                  "DejaVuSans-BoldOblique.ttf")),
    _Face("DejaVu Serif", "serif", ("DejaVuSerif.ttf", "DejaVuSerif-Bold.ttf", "DejaVuSerif-Italic.ttf",
                                    "DejaVuSerif-BoldItalic.ttf")),
    _Face("DejaVu Sans Mono", "mono", ("DejaVuSansMono.ttf", "DejaVuSansMono-Bold.ttf",
                                       "DejaVuSansMono-Oblique.ttf", "DejaVuSansMono-BoldOblique.ttf")),
    _Face("Inconsolata", "mono", ("Inconsolatazi4-Regular.otf", "Inconsolatazi4-Bold.otf", "", "")),
    _Face("Latin Modern Roman", "serif", _quad("lmroman10", "otf", _GYRE)),
    _Face("Latin Modern Sans", "sans", ("lmsans10-regular.otf", "lmsans10-bold.otf", "lmsans10-oblique.otf",
                                        "lmsans10-boldoblique.otf")),
    _Face("Latin Modern Mono", "mono", ("lmmono10-regular.otf", "lmmonolt10-bold.otf", "lmmono10-italic.otf",
                                        "lmmonolt10-boldoblique.otf")),
)}

_SERIF = ("Liberation Serif", "TeX Gyre Termes", "Tinos", "Nimbus Roman", "DejaVu Serif", "Latin Modern Roman")
_SANS = ("Liberation Sans", "TeX Gyre Heros", "Arimo", "Nimbus Sans", "DejaVu Sans", "Latin Modern Sans")
_MONO = ("Liberation Mono", "TeX Gyre Cursor", "Cousine", "Nimbus Mono PS", "DejaVu Sans Mono", "Latin Modern Mono")

# (name fragments of the source family, preferred faces in order). Checked in this order; mono and the
# more specific names come first ("dejavusansmono" before "dejavusans", "liberationsans" before "sans").
RULES: Tuple[Tuple[Tuple[str, ...], Tuple[str, ...]], ...] = (
    (("dejavusansmono",), ("DejaVu Sans Mono",) + _MONO),
    (("inconsolata", "consolas", "menlo", "monaco", "lucidaconsole", "sourcecode", "firamono", "firacode"),
     ("Inconsolata", "DejaVu Sans Mono") + _MONO),
    (("courier", "cousine", "liberationmono", "nimbusmono", "cursor"), _MONO),
    (("lmmono", "cmtt"), ("Latin Modern Mono",) + _MONO),
    (("calibri", "carlito"), ("Carlito",) + _SANS),
    (("cambria", "caladea"), ("Caladea",) + _SERIF),
    (("georgia", "gelasio"), ("Gelasio", "TeX Gyre Schola") + _SERIF),
    (("palatino", "bookantiqua", "pagella", "palladio", "pplr", "pplb"), ("TeX Gyre Pagella",) + _SERIF),
    (("garamond",), ("EB Garamond", "TeX Gyre Pagella") + _SERIF),
    (("schoolbook", "schola", "centuryschl", "newcentury"), ("TeX Gyre Schola",) + _SERIF),
    (("bookman", "bonum"), ("TeX Gyre Bonum",) + _SERIF),
    (("avantgarde", "centurygothic", "adventor"), ("TeX Gyre Adventor",) + _SANS),
    (("libertine", "libertinus"), ("Libertinus Serif",) + _SERIF),
    (("sourceserif",), ("Source Serif Pro",) + _SERIF),
    (("sourcesans",), ("Source Sans Pro",) + _SANS),
    (("notoserif",), ("Noto Serif",) + _SERIF),
    (("notosans",), ("Noto Sans",) + _SANS),
    (("dejavuserif",), ("DejaVu Serif",) + _SERIF),
    (("dejavusans", "verdana", "tahoma"), ("DejaVu Sans",) + _SANS),
    (("roboto",), ("Roboto",) + _SANS),
    (("opensans", "segoe"), ("Open Sans",) + _SANS),
    (("lato",), ("Lato",) + _SANS),
    (("firasans",), ("Fira Sans",) + _SANS),
    (("lmsans", "cmss"), ("Latin Modern Sans",) + _SANS),
    (("lmroman", "cmr", "cmbx", "cmti", "cmsl", "computermodern", "latinmodern"), ("Latin Modern Roman",) + _SERIF),
    (("arial", "helvetica", "helv", "arimo", "liberationsans", "nimbussans", "heros", "swiss"),
     ("Liberation Sans", "Arimo", "Nimbus Sans", "TeX Gyre Heros") + _SANS),
    (("times", "tinos", "liberationserif", "nimbusrom", "termes", "tiro", "roman"),
     ("Liberation Serif", "Tinos", "Nimbus Roman", "TeX Gyre Termes") + _SERIF),
)

# Symbol and math fonts: their glyphs are symbols or math, not text in a family to reproduce.
_SKIP = re.compile(r"^(cmmi|cmsy|cmex|msam|msbm|rsfs|eufm|eurm|stmary|wasy|lmmath|mtmi|mtsy|txsy|pxsy|"
                   r"symbol|zapf|dingbat|wingding|webding|marlett|mathematicalpi|universalmath)|math",
                   re.IGNORECASE)


@dataclass(frozen=True)
class FontChoice:
    source: str                   # the family as the layout spells it ("Helvetica")
    generic: str                  # "serif" | "sans" | "mono"
    family: str                   # the installed family chosen ("Liberation Sans")
    fontspec: str                 # exact \setmainfont / \newfontfamily argument: "{Liberation Sans}" or "{Carlito-Regular.ttf}[...]"
    bold: bool                    # a real bold face is installed
    italic: bool                  # a real italic face is installed
    metric_compatible: bool       # same glyph widths as the source family
    chars: int = 0                # source characters set in this family
    roles: Tuple[str, ...] = ()   # block roles that use it ("body", "heading", ...)
    sizes: Tuple[float, ...] = ()  # distinct sizes it is set in, pt
    alternatives: Tuple[str, ...] = field(default=())   # other installed faces that would also do

    def to_prompt(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"source_family": self.source, "generic": self.generic, "use": self.family,
                             "fontspec": self.fontspec, "bold": self.bold, "italic": self.italic,
                             "metric_compatible": self.metric_compatible, "chars": self.chars,
                             "roles": list(self.roles), "sizes_pt": list(self.sizes)}
        if self.alternatives:
            d["alternatives"] = list(self.alternatives)
        return d


# ---------------------------------------------------------------------------
# What is installed (cached per process)
# ---------------------------------------------------------------------------

def _run(argv: List[str]) -> str:
    try:
        cp = subprocess.run(argv, capture_output=True, text=True, timeout=_TOOL_TIMEOUT_S, check=False)
        return cp.stdout or ""
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning(f"{argv[0]} failed: {e}")
        return ""


@lru_cache(maxsize=1)
def fc_families() -> Dict[str, Set[str]]:
    """fontconfig families (lower-case) → their style names (lower-case). Empty without fc-list."""
    exe = shutil.which("fc-list")
    if not exe:
        return {}
    out: Dict[str, Set[str]] = defaultdict(set)
    for line in _run([exe, "--format", "%{family}\t%{style}\n"]).splitlines():
        fam, _, style = line.partition("\t")
        styles = {s.strip().lower() for s in style.split(",") if s.strip()}
        for name in fam.split(","):
            if name.strip():
                out[name.strip().lower()].update(styles)
    return dict(out)


@lru_cache(maxsize=1)
def tex_font_files() -> Set[str]:
    """The basenames of `FACES` files kpathsea can find (one `kpsewhich` call). Empty without kpsewhich."""
    from tex_runner.compile import build_env  # the sandbox's PATH: the TeX that will compile the pages

    exe = shutil.which("kpsewhich", path=build_env().get("PATH"))
    if not exe:
        return set()
    wanted = sorted({f for face in FACES.values() for f in face.files if f})
    found = {PurePath(p.strip()).name for p in _run([exe, *wanted]).splitlines() if p.strip()}
    return found & set(wanted)


def _fc_spec(face: _Face) -> Optional[Tuple[str, bool, bool]]:
    styles = fc_families().get(face.name.lower())
    if not styles:
        return None
    bold = any("bold" in s for s in styles)
    italic = any("italic" in s or "oblique" in s for s in styles)
    return "{" + face.name + "}", bold, italic


def _file_spec(face: _Face) -> Optional[Tuple[str, bool, bool]]:
    found = tex_font_files()
    regular, bold, italic, bolditalic = face.files
    if not regular or regular not in found:
        return None
    opts = []
    if bold in found:
        opts.append(f"BoldFont={bold}")
    if italic in found:
        opts.append(f"ItalicFont={italic}")
    if bolditalic in found:
        opts.append(f"BoldItalicFont={bolditalic}")
    return "{" + regular + "}" + (f"[{', '.join(opts)}]" if opts else ""), bold in found, italic in found


def installed_spec(name: str) -> Optional[Tuple[str, bool, bool]]:
    """(fontspec argument, has bold, has italic) for an installed face of `FACES`, else None."""
    face = FACES.get(name)
    if face is None:
        return None
    by_name = _fc_spec(face)
    # loading by name is the most readable for whoever edits the preamble, but only with real bold/italic
    if by_name and by_name[1] and by_name[2]:
        return by_name
    return _file_spec(face) or by_name


def installed_faces() -> List[str]:
    return [name for name in FACES if installed_spec(name)]


# ---------------------------------------------------------------------------
# Source family → choice
# ---------------------------------------------------------------------------

def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", re.sub(r"^[A-Z]{6}\+", "", name or "").lower())


def preferences(source: str) -> Tuple[str, Tuple[str, ...]]:
    """(generic family, faces in order of preference) for a source family name."""
    n = _norm(source)
    for keys, faces in RULES:
        if any(k in n for k in keys):
            return FACES[faces[0]].generic, faces
    _cls, generic = editable_font(source)
    return generic, {"sans": _SANS, "mono": _MONO}.get(generic, _SERIF)


def choose(source: str) -> Optional[FontChoice]:
    """The best installed face for one source family, or None when nothing suitable is installed."""
    if not source or _SKIP.search(_norm(source)):
        return None
    generic, prefs = preferences(source)
    # then the rest of the same generic class, so an odd install still gets something of the right kind
    pool = list(dict.fromkeys(prefs + {"sans": _SANS, "mono": _MONO}.get(generic, _SERIF)))
    picked: List[Tuple[str, Tuple[str, bool, bool]]] = []
    for name in pool:
        spec = installed_spec(name)
        if spec:
            picked.append((name, spec))
    if not picked:
        return None
    name, (spec, bold, italic) = picked[0]
    return FontChoice(source=source, generic=generic, family=name, fontspec=spec, bold=bold, italic=italic,
                      metric_compatible=_metric_match(source, name),
                      alternatives=tuple(n for n, _ in picked[1:4]))


def _metric_match(source: str, face: str) -> bool:
    """Whether `face` has the glyph widths of the source family (a drop-in replacement)."""
    n = _norm(source)
    groups = {
        "calibri": (("calibri", "carlito"), {"Carlito"}),
        "cambria": (("cambria", "caladea"), {"Caladea"}),
        "georgia": (("georgia", "gelasio"), {"Gelasio"}),
        # the TeX Gyre fonts are URW clones of the PostScript base fonts, same metrics
        "palatino": (("palatino", "pagella", "palladio", "pplr", "pplb"), {"TeX Gyre Pagella"}),
        "schoolbook": (("schoolbook", "schola", "centuryschl", "newcentury"), {"TeX Gyre Schola"}),
        "bookman": (("bookman", "bonum"), {"TeX Gyre Bonum"}),
        "avantgarde": (("avantgarde", "adventor"), {"TeX Gyre Adventor"}),
        "sans": (("arial", "helvetica", "helv", "arimo", "liberationsans", "nimbussans", "heros"),
                 {"Liberation Sans", "Arimo", "Nimbus Sans", "TeX Gyre Heros"}),
        "serif": (("times", "tinos", "liberationserif", "nimbusrom", "termes", "tiro"),
                  {"Liberation Serif", "Tinos", "Nimbus Roman", "TeX Gyre Termes"}),
        "mono": (("courier", "cousine", "liberationmono", "nimbusmono", "cursor"),
                 {"Liberation Mono", "Cousine", "Nimbus Mono PS", "TeX Gyre Cursor"}),
    }
    return any(face in faces and any(k in n for k in keys) for keys, faces in groups.values())


def _usage(layouts: Iterable[PageLayout]) -> Dict[str, Dict[str, Any]]:
    use: Dict[str, Dict[str, Any]] = {}
    for layout in layouts:
        for b in layout.blocks:
            font = b.get("font") or {}
            fam = str(font.get("family") or "").strip()
            if not fam:
                continue
            u = use.setdefault(fam, {"chars": 0, "roles": Counter(), "sizes": Counter()})
            n = len(str(b.get("text") or ""))
            u["chars"] += n
            u["roles"][str(b.get("role") or "body")] += n
            try:
                u["sizes"][round(float(font.get("size") or 0), 1)] += n
            except (TypeError, ValueError):
                pass
    return use


def font_candidates(layouts: Iterable[PageLayout]) -> List[FontChoice]:
    """
    One `FontChoice` per text family used in `layouts` (most characters first), each mapped to an
    installed face. Families with nothing suitable installed, and symbol/math fonts, are left out.
    """
    out: List[FontChoice] = []
    for fam, u in sorted(_usage(layouts).items(), key=lambda kv: -kv[1]["chars"]):
        choice = choose(fam)
        if choice is None:
            continue
        roles = tuple(r for r, _ in u["roles"].most_common())
        sizes = tuple(sorted(s for s in u["sizes"] if s > 0))[:12]
        out.append(FontChoice(**{**choice.__dict__, "chars": u["chars"], "roles": roles, "sizes": sizes}))
    return out
