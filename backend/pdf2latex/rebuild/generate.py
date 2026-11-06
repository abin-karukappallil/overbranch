"""
generate.py — Stage 6 of the AI rebuild ("generating"): the preamble call and the per-page body calls.

`make_preamble(ctx)` asks the model once for a XeLaTeX preamble built from the measured document facts
(page size, margins, heading ladder, colours, fonts, furniture) and the installed font candidates of
`fonts.py`, plus the page-1 image when the gateway really sees images. `write_page(ctx, n)` asks for
the body of page n from its layout JSON, its assets and tables, the validated preamble and the page
image. Compiling, repairing and scoring bodies is `refine.py`'s job; this module only smoke-compiles
the preamble.

Everything the model writes passes a deterministic guard before it is used, because the model reads
untrusted PDF text and a PDF can try to inject TeX:
  guard_preamble  strips fences/prose and anything from \\begin{document} on, removes every command
                  that reads or writes files, runs code, or rebuilds control sequences (\\input,
                  \\include*, \\write*, \\immediate, \\openout, \\openin, \\read, \\catcode, \\csname,
                  \\scantokens, \\directlua, \\special, \\font, ^^-escapes, file-writing environments,
                  shell/file packages, fontspec paths, ...), forces an article-type class, deletes any
                  geometry and page-dimension setting and re-imposes OUR geometry line (built from the
                  measured margins, bp units), and appends the page contract block (\\obpagestart and
                  fallbacks for \\obhead, \\obfoot, \\obcaption, \\obfootnote, \\obbackground).
  guard_body      the same removals, plus: no preamble commands, no \\obpagestart, no trailing page
                  break, and the ONLY file references allowed are \\includegraphics / \\obbackground of a
                  file listed for that page (anything else is dropped and reported; never replaced
                  by a placeholder).
A removed command is replaced by an empty group "{}", so the text on either side can never join into a
new control sequence. Both guards are pure and idempotent.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import shutil
import statistics
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from ..config import get_settings
from ..llm import LLMCallFailed, complete_ex
from ..prompts import fill
from . import prompts as P
from .document import standalone_page
from .fonts import FontChoice, font_candidates
from .model import PageLayout, RebuildCtx, SandboxResult
from .sandbox import compile_dir

logger = logging.getLogger("pdf2latex.rebuild.generate")

PREAMBLE_MAX_REPAIRS = 2
PREAMBLE_MAX_TOKENS = 8192
PAGE_MAX_TOKENS = 16384
SMOKE_BODY = "Test."
PAGE_SIZE_TOL_BP = 1.0          # the smoke PDF's page must be the geometry's paper size within this
LOG_EXCERPT_CHARS = 3000

CONTRACT_BEGIN = "% --- overbranch page contract (added by the pipeline; edits here are replaced) ---"
CONTRACT_END = "% --- end of overbranch page contract ---"


class PreambleFailed(Exception):
    pass


class PageGenerationFailed(Exception):
    pass


@dataclass
class PreambleResult:
    text: str
    warnings: List[str] = field(default_factory=list)
    repairs: int = 0
    vision_used: bool = False


@dataclass
class PageDraft:
    body: str
    warnings: List[str] = field(default_factory=list)
    vision_used: bool = False


# ---------------------------------------------------------------------------
# Low-level TeX scanning
# ---------------------------------------------------------------------------

_TOKEN = re.compile(r"\\(?:([A-Za-z@]+)|(.))", re.DOTALL)
# TeX's ^^ notation rewrites characters before tokenizing (\^^69nput is \input): the escape goes with
# any control word it sits in and the code after it
_CARETS = re.compile(r"(?:\\+[A-Za-z@]*)?\^\^(?:\^\^)?(?:[0-9a-f]{2}){0,2}[^\s{}\\]?")
_WORD_REST = re.compile(r"[A-Za-z@]*")
_BARE = re.compile(r"[ \t]*[^\s{}\[\\%]+")

# Control words removed wherever they appear (exact names).
_FORBIDDEN_NAMES = {
    "immediate", "openout", "closeout", "openin", "closein", "read", "readline", "ifeof", "newread",
    "catcode", "csname", "endcsname", "scantokens", "everyeof", "special", "font", "ExplSyntaxOn",
    "ExplSyntaxOff", "graphicspath", "DeclareGraphicsRule", "DeclareGraphicsExtensions", "import",
    "subimport", "bibliography", "bibliographystyle", "addbibresource", "tikzexternalize", "pdfximage",
    "pdfrefximage", "pdfmdfivesum", "mdfivesum", "DTLloaddb", "DTLloadrawdb", "csvreader", "csvautotabular",
    "csvautobooktabular", "csvautolongtable", "pgfplotstableread", "pgfimage", "pgfdeclareimage", "epsfig",
    "epsfbox", "psfig", "animategraphics", "ShellEscape", "jobname", "obpagestart",
}
# Control words removed when their name contains one of these (case-insensitive): \input, \@@input,
# \InputIfFileExists, \verbatiminput, \lstinputlisting, \include, \includeonly, \includepdf, \write,
# \protected@write, \newwrite, \IfFileExists, \XeTeXpicfile, \attachfile, \write18 (=\write), \directlua...
_FORBIDDEN_PART = re.compile(r"input|include|write|file|shell|lua|catcode|openout|openin", re.IGNORECASE)
# ... except these, which are checked separately (file name must be a listed asset).
_FILE_REFS = {"includegraphics", "obbackground"}

_FORBIDDEN_ENVS = ("filecontents", "filecontents*", "VerbatimOut", "verbatimwrite", "minted", "pycode",
                   "pyblock", "pyconsole", "luacode", "luacode*", "sagesilent", "sageblock", "sagecommandline",
                   "shellcommand", "tcbwritetemp", "tcboutputlisting")
_FORBIDDEN_PACKAGES = {"shellesc", "bashful", "pythontex", "minted", "luacode", "luapackageloader", "catchfile",
                       "filecontents", "newfile", "external", "tikzexternal", "embedfile", "attachfile",
                       "attachfile2", "navigator", "insdljs", "eforms", "media9", "movie15", "animate",
                       "import", "subfiles", "docmute", "askinclude", "verbatimbox", "write18", "ifplatform",
                       "pdftexcmds", "datatool", "csvsimple", "pgfplotstable"}
_PACKAGE_CMDS = {"usepackage", "RequirePackage", "documentclass", "LoadClass", "usetikzlibrary",
                 "usepgfplotslibrary", "usepgflibrary", "tcbuselibrary", "RequirePackageWithOptions"}
_FONT_CMDS = {"setmainfont", "setsansfont", "setmonofont", "setmathfont", "setmathrm", "setboldmathrm",
              "setmathsf", "setmathtt", "newfontfamily", "renewfontfamily", "providefontfamily", "setfontfamily",
              "newfontface", "renewfontface", "providefontface", "setfontface", "fontspec", "defaultfontfeatures",
              "addfontfeatures", "addfontfeature", "newfontlanguage", "newfontscript"}
_NAME_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-]*$")
_UNSAFE_PATH = re.compile(r"(^|[\s{\[=,\"'])(/|~|[A-Za-z]:[\\/])|\.\.|\bPath\s*=|\|", re.IGNORECASE)

_ALLOWED_CLASSES = {"article", "extarticle", "scrartcl"}
_DROP_CLASS_OPTIONS = {"landscape", "portrait"}

_PAGE_LENGTHS = ("textwidth", "textheight", "topmargin", "oddsidemargin", "evensidemargin", "headheight",
                 "headsep", "footskip", "paperwidth", "paperheight", "hoffset", "voffset", "pdfpagewidth",
                 "pdfpageheight", "pagewidth", "pageheight")
_GEOMETRY_CMDS = ("geometry", "newgeometry", "restoregeometry", "savegeometry", "loadgeometry")

_DEFINERS = (r"(?:(?:renew|new|provide)command\*?|DeclareRobustCommand\*?|(?:New|Renew|Provide|Declare)"
             r"(?:Expandable)?DocumentCommand|[gex]?def|let)")

_CONTRACT_MACROS = ("obpagestart", "obhead", "obfoot", "obcaption", "obfootnote", "obbackground")


def _skip_group(text: str, i: int, open_ch: str, close_ch: str) -> int:
    """Index just past the group that starts at text[i] == open_ch (braces nest; `\\{` does not count)."""
    depth = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def _skip_ws(text: str, i: int) -> int:
    """Skip spaces and at most one line break (a blank line ends an argument list in TeX)."""
    newlines = 0
    while i < len(text) and text[i] in " \t\r\n":
        if text[i] == "\n":
            newlines += 1
            if newlines > 1:
                break
        i += 1
    return i


def _args_end(text: str, i: int, max_groups: int = 4, bare: bool = True, cs_arg: bool = False) -> int:
    """
    End of the arguments that follow a command ending at `i`: an optional star, an optional control
    sequence (`cs_arg`, e.g. \\newfontfamily\\x), a TeX-style bare argument on the same line (`bare`:
    \\input /etc/passwd, \\write18, \\openout3=x), then up to `max_groups` `[..]` / `{..}` groups.
    """
    end = i
    j = _skip_ws(text, i)
    if j < len(text) and text[j] == "*":
        end = j + 1
        j = _skip_ws(text, end)
    if cs_arg:
        m = _TOKEN.match(text, j)
        if m and m.group(1):
            end = m.end()
            j = _skip_ws(text, end)
    if bare:
        m = _BARE.match(text, end)
        if m:
            end = m.end()
            j = _skip_ws(text, end)
    groups = 0
    while j < len(text) and groups < max_groups and text[j] in "[{":
        j = _skip_group(text, j, text[j], "]" if text[j] == "[" else "}")
        groups += 1
        end = j
        j = _skip_ws(text, j)
    return end


def _braced(text: str, i: int) -> Tuple[Optional[str], int]:
    """(content, end) of the `{..}` group at/after `i` (spaces skipped), or (None, i)."""
    j = _skip_ws(text, i)
    if j < len(text) and text[j] == "{":
        e = _skip_group(text, j, "{", "}")
        return text[j + 1:e - 1], e
    return None, i


def _options(text: str, i: int) -> Tuple[List[str], int]:
    """The `[..]` groups at/after `i` (contents) and the index after them."""
    opts: List[str] = []
    j = _skip_ws(text, i)
    while j < len(text) and text[j] == "[":
        e = _skip_group(text, j, "[", "]")
        opts.append(text[j + 1:e - 1])
        i = e
        j = _skip_ws(text, e)
    return opts, i


def _splice(text: str, start: int, end: int, repl: str = "{}") -> str:
    return text[:start] + repl + text[end:]


# ---------------------------------------------------------------------------
# Wrapping (fences, chatter)
# ---------------------------------------------------------------------------

_FENCE = re.compile(r"```[ \t]*[A-Za-z0-9_+-]*[ \t]*\n(.*?)(?:(?<=\n)[ \t]*```|\Z)", re.DOTALL)
_CHATTER = re.compile(r"^\s*(?:sure|certainly|okay|ok|here(?:'s| is| are)|below is|the following|this is)\b[^\\]*"
                      r"(?:latex|code|body|preamble|page|output)[^\\]*:\s*$", re.IGNORECASE)


def strip_wrapping(text: str) -> str:
    """The LaTeX inside Markdown fences (the longest block) without leading chatter lines."""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    if "```" in text:
        blocks = [m.group(1) for m in _FENCE.finditer(text)]
        if blocks:
            text = max(blocks, key=len)
        else:
            text = text.replace("```", "")
    lines = text.split("\n")
    while lines and (not lines[0].strip() or _CHATTER.match(lines[0])):
        lines.pop(0)
    return "\n".join(lines).strip("\n")


# ---------------------------------------------------------------------------
# The shared sanitizer
# ---------------------------------------------------------------------------

def _drop_envs(text: str, warns: List[str]) -> str:
    for env in _FORBIDDEN_ENVS:
        pat = re.compile(r"\\begin\s*\{" + re.escape(env) + r"\}(.*?)(\\end\s*\{" + re.escape(env) + r"\}|\Z)",
                         re.DOTALL)
        text, k = pat.subn("{}", text)
        if k:
            warns.append(f"removed environment {env} (writes files or runs code)")
    return text


# Each check below looks at one command starting at `start` and returns (text, keep): keep=True leaves
# it in place (possibly rewritten, same command name) and scanning continues INSIDE its arguments, so
# nothing hides in an option or a group; keep=False means it was replaced by "{}".

def _package_check(text: str, start: int, name: str, warns: List[str], in_body: bool) -> Tuple[str, bool]:
    cmd_end = start + 1 + len(name)
    if in_body:
        warns.append(f"removed \\{name} from the body (preamble only)")
        return _splice(text, start, _args_end(text, cmd_end, max_groups=3, bare=False)), False
    opts, after_opts = _options(text, cmd_end)
    arg, end = _braced(text, after_opts)
    if arg is None:
        warns.append(f"removed malformed \\{name}")
        return _splice(text, start, after_opts), False
    _, end = _options(text, end)    # \documentclass{x}[date]
    if any(_UNSAFE_PATH.search(o) for o in opts):
        warns.append(f"removed \\{name} with a path in its options")
        return _splice(text, start, end), False
    items = [x.strip() for x in arg.split(",") if x.strip()]
    keep = []
    for it in items:
        if not _NAME_OK.match(it):
            warns.append(f"removed \\{name}{{{it}}}: not a plain package name")
        elif it.lower() in _FORBIDDEN_PACKAGES:
            warns.append(f"removed \\{name}{{{it}}} (files, shell or scripting)")
        else:
            keep.append(it)
    if not keep:
        return _splice(text, start, end), False
    if keep != items:
        new = f"\\{name}" + "".join(f"[{o}]" for o in opts) + "{" + ",".join(keep) + "}"
        return _splice(text, start, end, new), True
    return text, True


def _resolve_file(fname: str, allowed: Dict[str, str]) -> Optional[str]:
    """The exact allowed filename `fname` names (exact, "./"-prefixed, or without its extension)."""
    f = fname.strip()
    if f.startswith("./"):
        f = f[2:]
    return allowed.get(f)


def _file_ref_check(text: str, start: int, name: str, allowed: Optional[Dict[str, str]], warns: List[str],
                    page: Optional[int]) -> Tuple[str, bool]:
    cmd_end = start + 1 + len(name)
    j = _skip_ws(text, cmd_end)
    if j < len(text) and text[j] == "*":
        j += 1
    opts, after_opts = _options(text, j)
    arg, end = _braced(text, after_opts)
    where = f"page {page}: " if page is not None else ""
    if arg is None:
        warns.append(f"{where}removed \\{name} without a file argument")
        return _splice(text, start, after_opts), False
    fname = arg.strip()
    if allowed is None:
        warns.append(f"removed \\{name}{{{fname}}} from the preamble (files belong in page bodies)")
        return _splice(text, start, end), False
    resolved = _resolve_file(fname, allowed)
    if resolved is None or any(_UNSAFE_PATH.search(o) for o in opts):
        warns.append(f"{where}dropped \\{name}{{{fname}}}: not a file of this page")
        return _splice(text, start, end), False
    if resolved != arg:
        return text[:after_opts] + "{" + resolved + "}" + text[end:], True
    return text, True


def _font_check(text: str, start: int, name: str, warns: List[str]) -> Tuple[str, bool]:
    """fontspec commands load font FILES: no paths, no Path= option, no macro as the font name."""
    end = _args_end(text, start + 1 + len(name), max_groups=4, bare=False, cs_arg=True)
    span = text[start + 1 + len(name):end]
    names = [g for g in re.findall(r"\{([^{}]*)\}", span)]
    if _UNSAFE_PATH.search(span) or any("\\" in g for g in names):
        warns.append(f"removed \\{name}: a font given by path or macro")
        return _splice(text, start, end), False
    return text, True


def _strip_carets(text: str, warns: List[str]) -> str:
    """
    Remove ^^ escapes. One inside a control word takes the whole command with it, so the rest of the
    disguised name and its argument (`put{../../x}` of `\\^^69nput{../../x}`) do not stay as page text.
    """
    found = False
    i = 0
    while True:
        m = _CARETS.search(text, i)
        if not m:
            break
        found = True
        end = m.end()
        if text[m.start()] == "\\":
            end = _args_end(text, _WORD_REST.match(text, end).end(), max_groups=2)
        text = _splice(text, m.start(), end)
        i = m.start() + 2
    if found:
        warns.append("removed ^^ character escapes")
    return text


def _sanitize(text: str, warns: List[str], *, allowed: Optional[Dict[str, str]], page: Optional[int],
              in_body: bool) -> str:
    """Remove every dangerous construct (see the module docstring). `allowed` None = preamble."""
    text = _strip_carets(text, warns)
    text = _drop_envs(text, warns)
    i = 0
    while True:
        m = _TOKEN.search(text, i)
        if not m:
            return text
        name = m.group(1)
        if name is None:            # a control symbol (\\, \%, \{ ...): skip both characters
            i = m.end()
            continue
        start = m.start()
        if name in _FILE_REFS:
            text, keep = _file_ref_check(text, start, name, allowed, warns, page)
        elif name in _PACKAGE_CMDS:
            text, keep = _package_check(text, start, name, warns, in_body)
        elif name in _FONT_CMDS:
            text, keep = _font_check(text, start, name, warns)
        elif name in _FORBIDDEN_NAMES or _FORBIDDEN_PART.search(name):
            if name == "obpagestart":
                end = _args_end(text, m.end(), max_groups=1, bare=False)
                warns.append("removed \\obpagestart (the pipeline inserts it)")
            else:
                end = _args_end(text, m.end(), max_groups=2)
                warns.append(f"removed \\{name} (reads/writes files, runs code or builds commands)")
            text, keep = _splice(text, start, end), False
        else:
            keep = True
        i = start + 1 + len(name) if keep else start + 2


def _defines(text: str, name: str) -> bool:
    return re.search(r"\\" + _DEFINERS + r"\s*\{?\s*\\" + name + r"(?![A-Za-z@])", text) is not None


def _drop_definitions(text: str, name: str) -> str:
    """Remove definitions of \\name (\\newcommand{\\name}[n]{..}, \\def\\name#1{..}, \\let\\name\\x, ...)."""
    pat = re.compile(r"\\(" + _DEFINERS + r")\s*(\{\s*\\" + name + r"\s*\}|\\" + name + r"(?![A-Za-z@]))")
    while True:
        m = pat.search(text)
        if not m:
            return text
        definer = m.group(1)
        j = m.end()
        if definer == "let":
            j = _skip_ws(text, j)
            if j < len(text) and text[j] == "=":
                j = _skip_ws(text, j + 1)
            t = _TOKEN.match(text, j)
            end = t.end() if t else j
        elif definer.endswith("def"):
            pm = re.compile(r"[^{]*").match(text, j)       # parameter text up to the body
            k = pm.end() if pm else j
            end = _skip_group(text, k, "{", "}") if k < len(text) else k
        else:
            groups = 2 if "DocumentCommand" in definer else 1
            end = j
            k = _skip_ws(text, j)
            seen = 0
            while k < len(text) and seen < groups:
                if text[k] == "[":
                    k = _skip_group(text, k, "[", "]")
                elif text[k] == "{":
                    k = _skip_group(text, k, "{", "}")
                    seen += 1
                else:
                    break
                end = k
                k = _skip_ws(text, k)
        text = _splice(text, m.start(), end, "")


# ---------------------------------------------------------------------------
# Preamble guard
# ---------------------------------------------------------------------------

def _strip_contract(text: str) -> str:
    """Remove a contract block (ours from an earlier guard, or a forged one): it is re-appended fresh."""
    pat = re.compile(re.escape(CONTRACT_BEGIN) + r".*?(?:" + re.escape(CONTRACT_END) + r"|\Z)", re.DOTALL)
    return pat.sub("", text)


def _fix_class(text: str, warns: List[str]) -> Tuple[str, int]:
    """Keep exactly one article-type \\documentclass (first in the text); returns (text, index after it)."""
    m = re.search(r"\\documentclass(?![A-Za-z@])", text)
    if not m:
        warns.append("the preamble had no \\documentclass; using article")
        text = "\\documentclass{article}\n" + text
        m = re.search(r"\\documentclass(?![A-Za-z@])", text)
    opts, after = _options(text, m.end())
    arg, end = _braced(text, after)
    _, end = _options(text, end)
    cls = (arg or "").strip()
    keep_opts = [o.strip() for raw in opts for o in raw.split(",")
                 if o.strip() and o.strip().lower() not in _DROP_CLASS_OPTIONS]
    if cls not in _ALLOWED_CLASSES:
        warns.append(f"document class {cls or '?'} replaced by article")
        cls = "article"
    new = "\\documentclass" + (f"[{','.join(keep_opts)}]" if keep_opts else "") + "{" + cls + "}"
    text = text[:m.start()] + new + text[end:]
    first_end = m.start() + len(new)
    # any further \documentclass goes
    rest = text[first_end:]
    while True:
        m2 = re.search(r"\\documentclass(?![A-Za-z@])", rest)
        if not m2:
            break
        e = _args_end(rest, m2.end(), max_groups=3, bare=False)
        rest = rest[:m2.start()] + rest[e:]
        warns.append("removed a second \\documentclass")
    return text[:first_end] + rest, first_end


def _strip_geometry(text: str, warns: List[str]) -> str:
    found = False
    # \usepackage[..]{geometry} (alone or in a list)
    pat = re.compile(r"\\usepackage(?![A-Za-z@])")
    i = 0
    while True:
        m = pat.search(text, i)
        if not m:
            break
        opts, after = _options(text, m.end())
        arg, end = _braced(text, after)
        if arg is None:
            i = m.end()
            continue
        items = [x.strip() for x in arg.split(",") if x.strip()]
        if "geometry" in items:
            found = True
            rest = [x for x in items if x != "geometry"]
            new = ("\\usepackage{" + ",".join(rest) + "}") if rest else ""
            text = text[:m.start()] + new + text[end:]
            i = m.start() + len(new)
        else:
            i = end
    for cmd in _GEOMETRY_CMDS:
        pat = re.compile(r"\\" + cmd + r"(?![A-Za-z@])")
        while True:
            m = pat.search(text)
            if not m:
                break
            found = True
            text = text[:m.start()] + text[_args_end(text, m.end(), max_groups=2, bare=False):]
    lengths = "|".join(_PAGE_LENGTHS)
    pats = (
        re.compile(r"\\(?:setlength|addtolength)\s*\{?\s*\\(?:" + lengths + r")(?![A-Za-z@])\s*\}?\s*\{[^{}]*\}"),
        re.compile(r"\\(?:" + lengths + r")(?![A-Za-z@])\s*=?\s*[-+]?\s*(?:\d+(?:\.\d*)?|\.\d+)\s*"
                   r"(?:pt|bp|mm|cm|in|em|ex|pc|dd|cc|sp)\b"),
    )
    for p in pats:
        text, k = p.subn("", text)
        found = found or bool(k)
    if found:
        warns.append("replaced the model's page geometry with the measured one")
    return text


def _contract_block(text: str) -> str:
    """The pipeline's page contract, appended after the model's preamble (trusted code, never guarded)."""
    lines = [CONTRACT_BEGIN, "\\usepackage{graphicx}", "\\usepackage{eso-pic}"]
    fancy_loaded = re.search(r"\\usepackage\s*(?:\[[^\]]*\])?\s*\{[^}]*\bfancyhdr\b", text) is not None
    if not _defines(text, "obhead") or not _defines(text, "obfoot"):
        if not fancy_loaded:
            lines += ["\\usepackage{fancyhdr}",
                      "\\pagestyle{fancy}\\fancyhf{}\\renewcommand{\\headrulewidth}{0pt}"
                      "\\renewcommand{\\footrulewidth}{0pt}"]
        lines += ["\\providecommand{\\obhead}[3]{\\fancyhead[L]{#1}\\fancyhead[C]{#2}\\fancyhead[R]{#3}}",
                  "\\providecommand{\\obfoot}[3]{\\fancyfoot[L]{#1}\\fancyfoot[C]{#2}\\fancyfoot[R]{#3}}"]
    lines += [
        "\\providecommand{\\obcaption}[1]{\\par{\\small #1}\\par}",
        "\\providecommand{\\obfootnote}[2]{\\par{\\footnotesize\\textsuperscript{#1}\\,#2}\\par}",
        "\\providecommand{\\obbackground}[1]{\\AddToShipoutPictureBG*{\\AtPageLowerLeft{"
        "\\includegraphics[width=\\paperwidth,height=\\paperheight]{#1}}}}",
        # \label's page field is \thepage, which \setcounter has just set to the SOURCE page, so it can
        # never show drift. ob-out-n records the physical page (\the is expanded by \write, at shipout).
        "\\makeatletter",
        "\\def\\ob@outpage#1{\\protected@write\\@auxout{}{\\string\\newlabel{ob-out-#1}"
        "{{}{\\noexpand\\the\\ReadonlyShipoutCounter}{}{}{}}}}",
        "\\def\\obpagestart#1{\\setcounter{page}{#1}\\obhead{}{}{}\\obfoot{}{}{}\\label{ob-src-#1}\\ob@outpage{#1}}",
        "\\makeatother",
        CONTRACT_END,
    ]
    return "\n".join(lines)


def guard_preamble(text: str, geometry_line: str) -> Tuple[str, List[str]]:
    """
    The model's preamble made safe and conformant (see the module docstring): returns (preamble,
    warnings). Pure and idempotent; `geometry_line` is the full `\\usepackage[...]{geometry}` line.
    """
    warns: List[str] = []
    text = _strip_contract(strip_wrapping(text))
    m = re.search(r"\\begin\s*\{document\}", text)
    if m:
        if text[m.end():].strip() and not re.fullmatch(r"\s*\\end\s*\{document\}\s*", text[m.end():]):
            warns.append("dropped everything from \\begin{document} on")
        text = text[:m.start()]
    text, k = re.subn(r"\\end\s*\{document\}", "", text)
    if k:
        warns.append("removed \\end{document}")
    if _defines(text, "obpagestart"):
        text = _drop_definitions(text, "obpagestart")     # the pipeline's own definition is appended
    text = _sanitize(text, warns, allowed=None, page=None, in_body=False)
    text = _strip_geometry(text, warns)
    text, cls_end = _fix_class(text, warns)
    head, tail = text[:cls_end], text[cls_end:]
    insert = [geometry_line]
    if not re.search(r"\\usepackage\s*(?:\[[^\]]*\])?\s*\{[^}]*\bfontspec\b", tail):
        insert.append("\\usepackage{fontspec}")
    tail = re.sub(r"\n{3,}", "\n\n", tail.strip("\n"))
    out = head + "\n" + "\n".join(insert) + ("\n" + tail if tail.strip() else "") + "\n" + _contract_block(tail)
    return out.strip() + "\n", _dedupe(warns)


def _dedupe(warns: List[str]) -> List[str]:
    return list(dict.fromkeys(warns))


# ---------------------------------------------------------------------------
# Body guard
# ---------------------------------------------------------------------------

_TRAILING_BREAK = re.compile(r"(?:\s*\\(?:newpage|clearpage|cleardoublepage|pagebreak)(?![A-Za-z@])(?:\s*\[\d\])?)+\s*\Z")


def _allowed_map(allowed_files: Iterable[str]) -> Dict[str, str]:
    """Allowed names, keyed by themselves and by their name without extension (if unambiguous)."""
    files = [f.strip() for f in allowed_files if f and f.strip()]
    out: Dict[str, str] = {f: f for f in files}
    stems = Counter(re.sub(r"\.[A-Za-z0-9]+$", "", f) for f in files)
    for f in files:
        stem = re.sub(r"\.[A-Za-z0-9]+$", "", f)
        if stem != f and stems[stem] == 1 and stem not in out:
            out[stem] = f
    return out


def guard_body(body: str, allowed_files: Iterable[str], page: int) -> Tuple[str, List[str]]:
    """
    One page body made safe (see the module docstring): returns (body, warnings). The only file
    references kept are \\includegraphics / \\obbackground of `allowed_files`. Pure and idempotent.
    """
    warns: List[str] = []
    text = strip_wrapping(body)
    m = re.search(r"\\begin\s*\{document\}", text)
    if m:
        text = text[m.end():]
        warns.append(f"page {page}: the reply was a whole document; kept only its body")
    m = re.search(r"\\end\s*\{document\}", text)
    if m:
        if text[m.end():].strip():
            warns.append(f"page {page}: dropped text after \\end{{document}}")
        text = text[:m.start()]
    for name in _CONTRACT_MACROS:
        if _defines(text, name):
            text = _drop_definitions(text, name)
            warns.append(f"page {page}: removed a redefinition of \\{name}")
    text = _sanitize(text, warns, allowed=_allowed_map(allowed_files), page=page, in_body=True)
    # a macro defined in one page body would be defined twice in the merged document
    text, k = re.subn(r"\\(?:new|renew)command(?![A-Za-z@])", r"\\DeclareRobustCommand", text)
    if k:
        warns.append(f"page {page}: \\newcommand in the body turned into \\DeclareRobustCommand")
    text = re.sub(r"(?<!\\else)\\(newlength|newsavebox)\s*\{?\s*(\\[A-Za-z@]+)\s*\}?",
                  r"\\ifdefined\2\\else\\\1{\2}\\fi", text)
    text = _TRAILING_BREAK.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    # only the placeholders of removed commands left: the model did not write a page
    if not text.replace("{}", "").strip():
        text = ""
    return (text + "\n" if text else ""), _dedupe(warns)


# ---------------------------------------------------------------------------
# Measured document facts
# ---------------------------------------------------------------------------

def _lower_quartile(values: Sequence[float]) -> float:
    vals = sorted(values)
    return vals[int((len(vals) - 1) * 0.25)]


def _median(values: Sequence[float]) -> float:
    return float(statistics.median(values)) if values else 0.0


def _page_size(layouts: Sequence[PageLayout], ctx_inspection=None) -> Tuple[float, float]:
    sizes = Counter((round(l.width_pt, 2), round(l.height_pt, 2)) for l in layouts if l.width_pt and l.height_pt)
    if not sizes and ctx_inspection is not None:
        sizes = Counter((round(p.width_pt, 2), round(p.height_pt, 2)) for p in ctx_inspection.pages)
    return sizes.most_common(1)[0][0] if sizes else (595.28, 841.89)


def _furniture_blocks(layouts: Sequence[PageLayout], roles: Tuple[str, ...]) -> List[Dict[str, Any]]:
    return [b for l in layouts for b in l.blocks if b.get("role") in roles and b.get("bbox")]


def _font_size(b: Dict[str, Any], default: float = 10.0) -> float:
    try:
        return float((b.get("font") or {}).get("size") or default)
    except (TypeError, ValueError):
        return default


def geometry_line(layouts: Sequence[PageLayout], inspection=None) -> str:
    """
    The `\\usepackage[...]{geometry}` line, from measurement: exact paper size, the lower quartile of
    each page margin over the pages that have text (short pages do not inflate the bottom margin), and,
    when the document has running headers/footers, headheight/headsep/footskip that put them where
    the source has them. Units are bp (= PDF points).
    """
    w, h = _page_size(layouts, inspection)
    same = [l for l in layouts if abs(l.width_pt - w) < 1 and abs(l.height_pt - h) < 1 and l.margins]
    texty = [l for l in same if l.blocks] or same
    m: Dict[str, float] = {}
    for side, default in (("left", 72.0), ("right", 72.0), ("top", 72.0), ("bottom", 72.0)):
        vals = [float(l.margins.get(side, default)) for l in texty]
        m[side] = _lower_quartile(vals) if vals else default
    for a, b, dim in (("left", "right", w), ("top", "bottom", h)):
        m[a] = min(max(m[a], 0.0), 0.45 * dim)
        m[b] = min(max(m[b], 0.0), 0.45 * dim)
    opts = [f"paperwidth={w:.2f}bp", f"paperheight={h:.2f}bp", f"left={m['left']:.2f}bp",
            f"right={m['right']:.2f}bp", f"top={m['top']:.2f}bp", f"bottom={m['bottom']:.2f}bp"]
    heads = [b for b in _furniture_blocks(same, ("header",)) if b["bbox"][3] <= m["top"] + 2]
    if heads:
        size = _median([_font_size(b) for b in heads])
        base = _median([b["bbox"][3] for b in heads]) - 0.22 * size     # header baseline
        headheight = max(1.25 * size, _median([b["bbox"][3] - b["bbox"][1] for b in heads]))
        headheight = min(headheight, max(base, 1.0))
        headsep = max(0.0, m["top"] - base)
        opts += [f"headheight={headheight:.2f}bp", f"headsep={headsep:.2f}bp"]
    feet = [b for b in _furniture_blocks(same, ("footer", "page_number")) if b["bbox"][1] >= h - m["bottom"] - 2]
    if feet:
        size = _median([_font_size(b) for b in feet])
        base = _median([b["bbox"][3] for b in feet]) - 0.22 * size      # footer baseline
        footskip = base - (h - m["bottom"])
        if footskip < size:
            footskip = max(size, 0.5 * m["bottom"])
        opts.append(f"footskip={footskip:.2f}bp")
    return "\\usepackage[" + ",".join(opts) + "]{geometry}"


def _geometry_values(line: str) -> Dict[str, float]:
    return {k: float(v) for k, v in re.findall(r"(\w+)=([\d.]+)bp", line)}


def _style(blocks: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The dominant font (by characters) of some blocks: family, size, bold, italic, color."""
    if not blocks:
        return None
    votes: Counter = Counter()
    for b in blocks:
        f = b.get("font") or {}
        key = (str(f.get("family") or ""), round(_font_size(b), 1), bool(f.get("bold")), bool(f.get("italic")),
               str(f.get("color") or "#000000"))
        votes[key] += max(1, len(str(b.get("text") or "")))
    fam, size, bold, italic, color = votes.most_common(1)[0][0]
    d: Dict[str, Any] = {"family": fam, "size": size, "bold": bold, "italic": italic, "color": color,
                         "blocks": len(blocks)}
    aligns = Counter(str(b.get("align") or "left") for b in blocks)
    d["align"] = aligns.most_common(1)[0][0]
    return d


def color_name(hex_color: str) -> str:
    return "c" + hex_color.lstrip("#").upper()


def document_facts(ctx: RebuildCtx, geometry: str) -> Dict[str, Any]:
    """What the preamble call needs to know about the whole document (measured, compact)."""
    layouts = ctx.layouts
    blocks = [b for l in layouts for b in l.blocks]
    by_role: Dict[str, List[Dict[str, Any]]] = {}
    for b in blocks:
        by_role.setdefault(str(b.get("role") or "body"), []).append(b)
    w, h = _page_size(layouts, ctx.inspection)
    g = _geometry_values(geometry)
    facts: Dict[str, Any] = {
        "pages": ctx.inspection.page_count if ctx.inspection else len(layouts),
        "doc_type": ctx.inspection.doc_type if ctx.inspection else "report",
        "paper_bp": [w, h],
        "orientation": "landscape" if w > h else "portrait",
        "margins_bp": {k: g.get(k) for k in ("left", "right", "top", "bottom")},
        "text_area_bp": [round(w - g.get("left", 0) - g.get("right", 0), 1),
                         round(h - g.get("top", 0) - g.get("bottom", 0), 1)],
        "columns": max((l.columns for l in layouts), default=1),
    }
    body = _style(by_role.get("body", []) + by_role.get("list_item", []))
    if body:
        facts["body_text"] = body
    gaps = [float(b["gap_before"]) for l in layouts for prev, b in zip(l.blocks, l.blocks[1:])
            if b.get("role") == "body" and prev.get("role") == "body" and b.get("gap_before")]
    if gaps:
        facts["paragraph_gap_pt"] = round(_median(gaps), 1)
    ladder = {}
    for lvl in (1, 2, 3):
        st = _style([b for b in by_role.get("heading", []) if int(b.get("level") or 1) == lvl])
        if st:
            gb = [float(b["gap_before"]) for b in by_role.get("heading", [])
                  if int(b.get("level") or 1) == lvl and b.get("gap_before")]
            if gb:
                st["space_before_pt"] = round(_median(gb), 1)
            ladder[str(lvl)] = st
    if ladder:
        facts["heading_levels"] = ladder
    for role in ("title", "caption", "footnote", "header", "footer", "page_number"):
        st = _style(by_role.get(role, []))
        if st:
            facts[f"{role}_style"] = st
    furniture = {}
    for role in ("header", "footer", "page_number"):
        pages = sorted({l.number for l in layouts for b in l.blocks if b.get("role") == role})
        if pages:
            samples = list(dict.fromkeys(str(b.get("text") or "") for b in by_role.get(role, [])))[:3]
            furniture[role] = {"pages": len(pages), "examples": samples}
    facts["furniture"] = furniture or "none"
    markers = Counter(str(b.get("marker")) for b in by_role.get("list_item", []) if b.get("marker"))
    if markers:
        facts["list_markers"] = [mk for mk, _ in markers.most_common(8)]
        facts["list_depth_max"] = max(int(b.get("level") or 1) for b in by_role.get("list_item", []))
    colors: Counter = Counter()
    for b in blocks:
        c = (b.get("font") or {}).get("color")
        if c:
            colors[str(c)] += len(str(b.get("text") or ""))
        for r in b.get("runs") or []:
            if r.get("color"):
                colors[str(r["color"])] += len(str(r.get("text") or ""))
    if colors:
        facts["colors"] = {color_name(c): c for c, _ in colors.most_common(16)
                           if re.fullmatch(r"#[0-9a-fA-F]{6}", c)}
    tables = [t for l in layouts for t in l.tables]
    if tables:
        facts["tables"] = {"count": len(tables), "styles": sorted({str(t.get("style")) for t in tables})}
    kinds = Counter(a.kind for a in ctx.manifest.assets)
    if kinds:
        facts["assets"] = dict(kinds)
    if by_role.get("math") or kinds.get("math"):
        facts["math"] = True
    return facts


# ---------------------------------------------------------------------------
# LLM plumbing
# ---------------------------------------------------------------------------

def _nonce(*parts: str) -> str:
    return hashlib.sha1("\x00".join(parts).encode("utf-8", "replace")).hexdigest()[:10]


def _llm_kwargs(max_tokens: int, label: str) -> Dict[str, Any]:
    s = get_settings()
    return {"timeout": s.page_timeout, "retries": s.page_retries, "concurrency": s.concurrency,
            "max_tokens": max_tokens, "label": label}


async def _png(ctx: RebuildCtx, n: int) -> List[bytes]:
    """The page image to send: one when the gateway passed the vision probe, else none."""
    if not ctx.vision:
        return []
    path = ctx.page_pngs.get(n)
    if path is None or not Path(path).is_file():
        return []
    return [await asyncio.to_thread(Path(path).read_bytes)]


def _vision_used(reply) -> bool:
    return reply.images_sent > 0 and not reply.images_dropped


def _fonts_prompt(choices: List[FontChoice]) -> str:
    if not choices:
        return "(no suitable installed font found: keep the default font)"
    return json.dumps([c.to_prompt() for c in choices], ensure_ascii=False, indent=1)


# ---------------------------------------------------------------------------
# Preamble
# ---------------------------------------------------------------------------

async def _smoke(ctx: RebuildCtx, preamble: str, geometry: str) -> Tuple[bool, List[str], str]:
    """Compile the preamble with a one-line body; (ok, problems, log excerpt)."""
    wd = ctx.work_dir / "preamble"
    await asyncio.to_thread(_reset_dir, wd)
    (wd / "main.tex").write_text(standalone_page(preamble, SMOKE_BODY, 1), encoding="utf-8")
    res: SandboxResult = await compile_dir(wd)
    problems: List[str] = []
    if res.detail and not res.errors and not res.log:
        raise PreambleFailed(f"sandbox unavailable: {res.detail}")
    if res.timed_out:
        problems.append("the compile timed out")
    lines = preamble.split("\n")
    for e in res.errors[:12]:
        mm = re.match(r"[^:]*:(\d+):", e)
        if mm and 0 < int(mm.group(1)) <= len(lines):
            problems.append(f"{e}  [line {mm.group(1)}: {lines[int(mm.group(1)) - 1].strip()[:200]}]")
        else:
            problems.append(e)
    if res.ok and res.pdf_path and res.pdf_path.is_file():
        pages, size = await asyncio.to_thread(_pdf_shape, res.pdf_path)
        g = _geometry_values(geometry)
        if pages != 1:
            problems.append(f"the one-line test document produced {pages} pages; it must produce exactly 1 "
                            "(nothing in the preamble may print or break pages)")
        if size and (abs(size[0] - g.get("paperwidth", size[0])) > PAGE_SIZE_TOL_BP
                     or abs(size[1] - g.get("paperheight", size[1])) > PAGE_SIZE_TOL_BP):
            problems.append(f"the page size came out {size[0]:.1f} x {size[1]:.1f} bp instead of "
                            f"{g.get('paperwidth')} x {g.get('paperheight')} bp: something overrides the geometry")
    elif not problems:
        problems.append(res.detail or "no PDF was produced")
    ok = not problems
    excerpt = "" if ok else res.log[-LOG_EXCERPT_CHARS:]
    if ok:
        await asyncio.to_thread(shutil.rmtree, wd, True)
    return ok, problems, excerpt


def _reset_dir(wd: Path) -> None:
    shutil.rmtree(wd, ignore_errors=True)
    wd.mkdir(parents=True, exist_ok=True)


def _pdf_shape(pdf: Path) -> Tuple[int, Optional[Tuple[float, float]]]:
    import pymupdf

    with pymupdf.open(pdf) as doc:
        if doc.page_count == 0:
            return 0, None
        r = doc[0].rect
        return doc.page_count, (r.width, r.height)


async def make_preamble(ctx: RebuildCtx) -> PreambleResult:
    """
    The validated preamble (also stored in `ctx.preamble` and `ctx.rebuild_dir/preamble.tex`). One
    LLM call, plus at most PREAMBLE_MAX_REPAIRS repair calls when the smoke compile fails. A saved
    preamble that still compiles is reused without any call. Raises PreambleFailed.
    """
    geometry = geometry_line(ctx.layouts, ctx.inspection)
    saved = ctx.rebuild_dir / "preamble.tex"
    if saved.is_file():
        text, warns = guard_preamble(saved.read_text(encoding="utf-8"), geometry)
        ok, problems, _ = await _smoke(ctx, text, geometry)
        if ok:
            ctx.preamble = text
            return PreambleResult(text=text, warnings=warns, repairs=0, vision_used=False)
        logger.warning(f"saved preamble no longer compiles ({problems[:2]}); generating a new one")

    choices = await asyncio.to_thread(font_candidates, ctx.layouts)
    facts = json.dumps(document_facts(ctx, geometry), ensure_ascii=False, indent=1)
    images = await _png(ctx, 1)
    user = fill(P.PREAMBLE_USER, GEOMETRY=geometry, FONTS=_fonts_prompt(choices),
                VISION_NOTE=P.VISION_ON_PREAMBLE if images else P.VISION_OFF, NONCE=_nonce(facts), FACTS=facts)
    try:
        reply = await complete_ex(P.PREAMBLE_SYSTEM, user, images, **_llm_kwargs(PREAMBLE_MAX_TOKENS, "rebuild-preamble"))
    except LLMCallFailed as e:
        raise PreambleFailed(f"preamble call failed: {e}") from e
    vision_used = _vision_used(reply)
    if not strip_wrapping(reply.text).strip():
        raise PreambleFailed("the model returned an empty preamble")
    text, warns = guard_preamble(reply.text, geometry)

    repairs = 0
    ok, problems, excerpt = await _smoke(ctx, text, geometry)
    while not ok:
        if repairs >= PREAMBLE_MAX_REPAIRS:
            raise PreambleFailed("the preamble does not compile: " + "; ".join(problems[:3]))
        repairs += 1
        user = fill(P.PREAMBLE_REPAIR_USER, PROBLEMS="\n".join(f"- {p}" for p in problems[:12]),
                    LOG=excerpt or "(none)", PREAMBLE=text)
        try:
            fix = await complete_ex(P.PREAMBLE_SYSTEM, user, (),
                                    **_llm_kwargs(PREAMBLE_MAX_TOKENS, f"rebuild-preamble-fix{repairs}"))
        except LLMCallFailed as e:
            logger.warning(f"preamble repair {repairs} failed: {e}")
            continue
        # an empty reply or a failed call leaves the text as it was, so its smoke result still stands
        if strip_wrapping(fix.text).strip():
            text, w2 = guard_preamble(fix.text, geometry)
            warns = _dedupe(warns + w2)
            ok, problems, excerpt = await _smoke(ctx, text, geometry)

    await asyncio.to_thread(_save, saved, text)
    ctx.preamble = text
    return PreambleResult(text=text, warnings=warns, repairs=repairs, vision_used=vision_used)


def _save(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

def _layout(ctx: RebuildCtx, n: int) -> PageLayout:
    for l in ctx.layouts:
        if l.number == n:
            return l
    raise PageGenerationFailed(f"page {n}: no layout")


def page_files(ctx: RebuildCtx, n: int, layout: Optional[PageLayout] = None) -> List[str]:
    """The asset filenames page `n` may reference (manifest plus the layout's own asset list)."""
    files = list(ctx.manifest.filenames(n))
    for a in (layout.assets if layout is not None else []):
        f = a.get("file")
        if isinstance(f, str) and f not in files:
            files.append(f)
    return files


def _assets_prompt(ctx: RebuildCtx, n: int, layout: PageLayout) -> str:
    rows = []
    seen = set()
    for a in ctx.manifest.for_page(n):
        seen.add(a.filename)
        use = (f"\\obbackground{{{a.filename}}}" if a.kind == "background"
               else f"\\includegraphics[width={a.width_pt:.1f}bp]{{{a.filename}}}")
        rows.append(f"- {a.filename}  kind={a.kind}  {a.width_pt:.1f} x {a.height_pt:.1f} bp  → {use}")
    for a in layout.assets:
        f = a.get("file")
        if isinstance(f, str) and f not in seen:
            w = float(a.get("width_pt") or 0)
            rows.append(f"- {f}  kind={a.get('kind')}  → \\includegraphics[width={w:.1f}bp]{{{f}}}")
    return "\n".join(rows) if rows else "(none: this page has no images; include no file)"


def _furniture_prompt(layout: PageLayout) -> str:
    rows = [f"- {b.get('role')} ({b.get('align') or 'left'}): {json.dumps(str(b.get('text') or ''), ensure_ascii=False)}"
            for b in layout.blocks if b.get("role") in ("header", "footer", "page_number")]
    if not rows:
        return "This page has no running header or footer: do not call \\obhead or \\obfoot.\n"
    return "Running header/footer blocks of this page (pass them to \\obhead / \\obfoot):\n" + "\n".join(rows) + "\n"


def _blank(layout: PageLayout) -> bool:
    return not layout.blocks and not layout.assets and not layout.tables


async def write_page(ctx: RebuildCtx, n: int) -> PageDraft:
    """The guarded body of page `n` from one LLM call. Raises PageGenerationFailed."""
    layout = _layout(ctx, n)
    preamble = ctx.preamble
    if not preamble and (ctx.rebuild_dir / "preamble.tex").is_file():
        preamble = (ctx.rebuild_dir / "preamble.tex").read_text(encoding="utf-8")
    if not preamble:
        raise PageGenerationFailed(f"page {n}: no validated preamble")
    if _blank(layout):
        return PageDraft(body="\\mbox{}\n", warnings=[f"page {n}: blank page"], vision_used=False)

    files = page_files(ctx, n, layout)
    geometry = _geometry_values(geometry_line(ctx.layouts, ctx.inspection))
    page_json = json.dumps(layout.to_prompt_dict(), ensure_ascii=False, separators=(",", ":"))
    images = await _png(ctx, n)
    warnings = "".join(f"Note: {w}\n" for w in layout.warnings)
    user = fill(
        P.PAGE_USER,
        PAGE=n,
        PAGES=ctx.inspection.page_count if ctx.inspection else len(ctx.layouts),
        DOC_TYPE=ctx.inspection.doc_type if ctx.inspection else "report",
        TEXT_W=f"{layout.width_pt - geometry.get('left', 0) - geometry.get('right', 0):.1f}",
        TEXT_H=f"{layout.height_pt - geometry.get('top', 0) - geometry.get('bottom', 0):.1f}",
        LEFT=f"{geometry.get('left', 0):.1f}",
        TOP=f"{geometry.get('top', 0):.1f}",
        VISION_NOTE=P.VISION_ON_PAGE if images else P.VISION_OFF,
        ASSETS=_assets_prompt(ctx, n, layout),
        FURNITURE=_furniture_prompt(layout),
        WARNINGS=warnings,
        PREAMBLE=preamble.strip(),
        NONCE=_nonce(page_json, str(n)),
        PAGE_JSON=page_json,
    )
    try:
        reply = await complete_ex(P.PAGE_SYSTEM, user, images, **_llm_kwargs(PAGE_MAX_TOKENS, f"rebuild-page-{n}"))
    except LLMCallFailed as e:
        raise PageGenerationFailed(f"page {n}: LLM call failed: {e}") from e
    body, warns = guard_body(reply.text, files, n)
    if not body.strip():
        raise PageGenerationFailed(f"page {n}: the model returned an empty body")
    return PageDraft(body=body, warnings=warns, vision_used=_vision_used(reply))
