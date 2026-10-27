import tempfile
import subprocess
import base64
import os
import re
import io
import time
import shutil
import sys
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

logger = logging.getLogger("compiler")


def _run_tex(cmd, *, cwd, timeout, env, capture_output=True):
    """
    Run a TeX engine subprocess and return its output as decoded strings.

    Uses bytes mode instead of ``text=True`` because pdflatex/xelatex/lualatex
    can emit non-UTF-8 bytes in their log output (Latin-1 font metric names,
    Windows-1252 file paths, raw binary from corrupted aux files).  Python's
    ``text=True`` defaults to strict UTF-8 decoding, which raises
    ``UnicodeDecodeError`` — surfaced as ``[INFRASTRUCTURE ERROR] Command
    'pdflatex' failed: 'utf-8' codec can't decode byte 0xed …``.  That
    exception was caught by the generic handler and treated as a compile
    failure, even when pdflatex had already produced a valid PDF.

    By reading raw bytes and decoding with ``errors='replace'``, invalid bytes
    become U+FFFD (�) instead of crashing, and the PDF is still picked up.

    The process runs in its own session (tex_sandbox.run_tex_process): on a
    timeout the whole process group — latexmk AND the pdflatex/biber it spawned —
    is killed, not just the direct child.
    """
    from tex_sandbox import run_tex_process
    return run_tex_process(cmd, cwd=cwd, timeout=timeout, env=env, capture_output=capture_output)


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, "") or default))
    except ValueError:
        return default


#: Wall-clock budget of one engine candidate (latexmk runs all its passes inside it).
TEX_COMPILE_TIMEOUT = _env_int("TEX_COMPILE_TIMEOUT", 120)
#: Budget for heavy documents (long, TikZ/pgfplots-heavy) — judged on every source on disk.
TEX_COMPILE_TIMEOUT_HEAVY = _env_int("TEX_COMPILE_TIMEOUT_HEAVY", 240)


_MAGIC_PROGRAM_RE = re.compile(
    r"^\s*%\s*!\s*TEX\s+(?:TS-)?program\s*=\s*(pdflatex|xelatex|lualatex)\b",
    re.IGNORECASE | re.MULTILINE,
)
_DEFAULT_ENGINES = {"", "latexmk", "pdflatex", "pdf", "latex"}


def detect_magic_engine(latex_code: str) -> Optional[str]:
    """Returns the engine named by a `% !TEX program = ...` magic comment in the file header, if any."""
    head = "\n".join((latex_code or "").splitlines()[:20])
    m = _MAGIC_PROGRAM_RE.search(head)
    return m.group(1).lower() if m else None


_TEX_ERROR_RE = re.compile(r"^(?:\S+\.tex:\d+: .*|! .*)$", re.MULTILINE)

# What a direct engine run is given instead of the bare file name. TeX reports an
# error at the line its reader had reached — the `\end{frame}` of a Beamer frame,
# the `\end{tabularx}` of a table — and says where the mistake really is only in
# the token context it prints underneath. By default that context is one level
# deep, which for `Missing $ inserted` is just `<inserted text> $`: no position
# at all. Raising \errorcontextlines here, on the command line, shows the levels
# that carry the user's text without adding a line to the document, so every
# reported line number still refers to the source as written.
_TEX_ENTRY = r"\errorcontextlines=20 \input{main.tex}"
# TeX truncates each context line to `half_error_line` (50 by default) and wraps
# its output at `max_print_line` (79). Both are kpathsea settings an environment
# variable overrides; widened, a context line holds enough of a frame to be found
# in the source, and no file name or error is ever split across lines.
_TEX_LOG_ENV = {"max_print_line": "10000", "error_line": "254", "half_error_line": "238"}


def _engine_command(engine_bin: str, *extra: str, jobname: str = "main", entry: str = "main.tex") -> List[str]:
    tex_entry = _TEX_ENTRY if entry == "main.tex" else r"\errorcontextlines=20 \input{" + entry + "}"
    return [engine_bin, *extra, "-interaction=nonstopmode", "-file-line-error", f"-jobname={jobname}", tex_entry]


# --- latexmk (the primary engine candidate: what Overleaf runs) ----------------------
_LATEXMK_ENGINE_FLAG = {"pdflatex": "-pdf", "xelatex": "-pdfxe", "lualatex": "-pdflua"}

# Server-side latexmkrc. Project rc files (.latexmkrc / latexmkrc) are Perl and are
# NEVER executed: latexmk runs with -norc and only this file via -r. It registers the
# custom dependencies Overleaf's own rc registers (makeindex is built into latexmk).
_SERVER_LATEXMKRC = r"""# OverBranch server latexmkrc - project rc files are never read (-norc).
use File::Basename;
sub ob_makeglossaries {
    my ($base_name, $path) = fileparse($_[0]);
    my @args = ("-q", "-d", $path, $base_name);
    return system("makeglossaries", @args);
}
add_cus_dep('glo', 'gls', 0, 'ob_makeglossaries');
add_cus_dep('acn', 'acr', 0, 'ob_makeglossaries');
add_cus_dep('slo', 'sls', 0, 'ob_makeglossaries');
add_cus_dep('nlo', 'nls', 0, 'ob_makenomenclature');
sub ob_makenomenclature {
    return system("makeindex", "$_[0].nlo", "-s", "nomencl.ist", "-o", "$_[0].nls");
}
push @generated_exts, 'glo', 'gls', 'glg', 'acn', 'acr', 'alg', 'slo', 'sls', 'slg', 'nlo', 'nls', 'nlg', 'ist';
$max_repeat = 6;
"""
_LATEXMKRC_PATH: Optional[Path] = None


def _server_latexmkrc() -> Path:
    """Writes the server rc once per process (outside every job directory) and returns it."""
    global _LATEXMKRC_PATH
    if _LATEXMKRC_PATH is not None and _LATEXMKRC_PATH.is_file():
        return _LATEXMKRC_PATH
    import hashlib
    digest = hashlib.sha1(_SERVER_LATEXMKRC.encode()).hexdigest()[:12]
    path = Path(tempfile.gettempdir()) / f"overbranch-latexmkrc-{os.getuid() if hasattr(os, 'getuid') else 0}-{digest}"
    if not path.is_file():
        tmp = path.with_suffix(".tmp%d" % os.getpid())
        tmp.write_text(_SERVER_LATEXMKRC, encoding="utf-8")
        os.replace(tmp, path)
    _LATEXMKRC_PATH = path
    return path


def _latexmk_command(engine_bin: str, main_rel: str, *, jobname: str, synctex: bool) -> List[str]:
    r"""
    ``latexmk -cd -f -interaction=nonstopmode -file-line-error -synctex=1 -pdf|-pdfxe|-pdflua``
    on the main document, run from the project root: ``-cd`` makes latexmk change to the
    main file's directory, so relative \input / \include / \graphicspath /
    \bibliography resolve exactly as on Overleaf. TeX Live's default restricted
    shell-escape is kept (no -shell-escape). ``-usepretex`` raises \errorcontextlines
    without adding a line to the document, as the direct engine path does.
    """
    cmd = ["latexmk", "-norc", "-r", str(_server_latexmkrc()), "-cd", "-f",
           "-interaction=nonstopmode", "-file-line-error"]
    if synctex:
        cmd.append("-synctex=1")
    cmd += [_LATEXMK_ENGINE_FLAG.get(engine_bin, "-pdf"), f"-jobname={jobname}",
            r"-usepretex=\errorcontextlines=20 ", main_rel]
    return cmd


def _attach_diagnostics(result: dict, output: str, tmpdir: Path, main_file: str = "main.tex",
                        project_root: Optional[Path] = None) -> None:
    """
    Adds ``diagnostics`` — every error of the run, located on the line its token
    is really on (latex_diagnostics) — and rewrites ``errors`` to carry those
    lines. ``output`` is one complete pass; ``result["errors"]`` already holds
    the error lines of all passes, and none of those is dropped.

    ``tmpdir`` is the directory TeX ran in (the main file's directory). When that
    is a sub-folder of ``project_root``, each diagnostic's ``file`` is rewritten
    to its project-relative path, so the editor opens the right file.
    """
    try:
        from latex_diagnostics import diagnose, error_lines
        root = (project_root or tmpdir).resolve()

        def read_source(name: str) -> Optional[str]:
            target = (tmpdir / name).resolve()
            if root not in target.parents or not target.is_file():
                return None
            return target.read_text(encoding="utf-8", errors="replace")

        diagnostics = diagnose(output, read_source, main_file)
        if project_root is not None and tmpdir.resolve() != root:
            for d in diagnostics:
                f = d.get("file")
                if isinstance(f, str) and f and not os.path.isabs(f):
                    try:
                        d["file"] = (tmpdir / f).resolve().relative_to(root).as_posix()
                    except (ValueError, OSError):
                        pass
    except Exception as e:
        logger.debug(f"error localisation skipped: {e}")
        return
    if not diagnostics:
        return
    result["diagnostics"] = diagnostics
    seen = {str(d.get("raw") or "") for d in diagnostics}
    others = [e for e in (result.get("errors") or []) if e not in seen]
    result["errors"] = list(dict.fromkeys(error_lines(diagnostics) + others))[:20]


def tex_errors(output: str) -> List[str]:
    """Error lines from a nonstopmode / -file-line-error TeX run (a PDF can still be produced)."""
    return list(dict.fromkeys(m.group(0).strip() for m in _TEX_ERROR_RE.finditer(output or "")))[:20]


def _overfull_boxes(output: str) -> List[Dict[str, Any]]:
    try:
        from latex_layout.overflow import parse_overfull
        return parse_overfull(output)
    except Exception:
        return []


def _pdf_extractable_chars(pdf_path: Path, max_pages: int = 40) -> int:
    """
    Number of non-whitespace characters the PDF's text layer yields (first ``max_pages``).
    Returns -1 when no extractor is available, so callers fail OPEN — an unknown count must
    never turn a real compile into a failure.
    """
    try:
        try:
            import pymupdf  # type: ignore
        except ImportError:
            import fitz as pymupdf  # type: ignore
        doc = pymupdf.open(str(pdf_path))
        try:
            total = 0
            for i, page in enumerate(doc):
                if i >= max_pages:
                    break
                total += len("".join(page.get_text().split()))
            return total
        finally:
            doc.close()
    except Exception:
        pass
    try:
        out = subprocess.run(["pdftotext", "-q", "-l", str(max_pages), str(pdf_path), "-"],
                             capture_output=True, timeout=30)
        if out.returncode == 0:
            return len("".join((out.stdout or b"").decode("utf-8", "replace").split()))
    except Exception:
        pass
    return -1


def _looks_blank(pdf_path: Path, source_text: str) -> bool:
    """
    A PDF that compiled but carries essentially no text, although its source clearly has a lot
    of it — the signature of a missing font under XeLaTeX (``\\setmainfont`` to a font the server
    does not have): the engine emits a valid, correctly-paginated PDF with no glyphs. Thresholds
    are deliberately wide (a real text page yields thousands of chars, a blank one a handful) and
    the check fails open, so image-only or genuinely sparse documents are never flagged.
    """
    src_alpha = sum(c.isalpha() for c in _strip_tex_comments(source_text or ""))
    if src_alpha <= 800:
        return False
    got = _pdf_extractable_chars(pdf_path)
    if got < 0:
        return False
    return got < 0.08 * src_alpha and got < 150 * max(1, _pdf_page_count(pdf_path))


_BLANK_FAILURE_MSG = (
    "The document compiled but produced no visible text — a font it selects "
    "(e.g. via \\setmainfont) is not installed on the server. Compile with pdfLaTeX, "
    "or guard the system-font setup behind \\ifPDFTeX so pdfLaTeX uses an installed font."
)


def _mark_blank_failure(failed: dict, blank_seen: bool) -> None:
    """Make a blank-output failure actionable instead of a wall of font-not-found noise."""
    if not blank_seen or not isinstance(failed, dict):
        return
    existing = failed.get("error_log") or ""
    if _BLANK_FAILURE_MSG not in existing:
        failed["error_log"] = f"{_BLANK_FAILURE_MSG}\n\n{existing}".strip()


def _pdf_page_count(pdf_path: Path) -> int:
    try:
        try:
            import pymupdf  # type: ignore
        except ImportError:
            import fitz as pymupdf  # type: ignore
        doc = pymupdf.open(str(pdf_path))
        try:
            return doc.page_count
        finally:
            doc.close()
    except Exception:
        return 1


_UNICODE_ENGINE_MARKERS = (
    "{fontspec}", "{unicode-math}", "{polyglossia}",
    r"\setmainfont", r"\setsansfont", r"\setmonofont",
    r"\setmathfont", r"\newfontface", r"\newfontfamily",
    r"\setmainlanguage", r"\directlua", r"\luadirect",
)


# Fontspec setup to neutralize when a blank-output pass tells us the system fonts
# are missing: comment out the package loads AND the font-selection commands so a
# retry under pdfLaTeX falls back to Computer Modern instead of selecting an
# installed font the server does not have.
_FONTSPEC_PKG_RE = re.compile(
    r'\\usepackage(?:\[[^\]]*\])?\{(?:fontspec|unicode-math|polyglossia)\}'
)
_FONTSPEC_CMD_RE = re.compile(
    r'\\(?:setmainfont|setsansfont|setmonofont|setromanfont|setmathfont|'
    r'newfontface|newfontfamily|setmainlanguage|setotherlanguage|setdefaultlanguage)'
    r'(?:\s*\[[^\]]*\])?\s*\{[^{}]*\}'
)


def _strip_fontspec_setup(code: str) -> str:
    """
    Comment out fontspec package loads and font-selection commands so a retry under
    pdfLaTeX renders in CM. Each stripped line is replaced by a comment that marks
    what was removed, so line numbers are preserved for diagnostics.
    """
    def _pkg(m: re.Match) -> str:
        return "% [AUTO-DISABLED: Unicode font package: " + m.group(0) + "]"

    def _cmd(m: re.Match) -> str:
        return "% [AUTO-DISABLED: system font selector: " + m.group(0).replace("\n", " ") + "]"

    out = _FONTSPEC_PKG_RE.sub(_pkg, code)
    out = _FONTSPEC_CMD_RE.sub(_cmd, out)
    return out


# Beamer-only commands appearing in a non-beamer class is the classic case where the
# source was authored (by the model or a user) for slides but the documentclass line
# never got switched. The resulting log is a wall of "Environment columns undefined"
# / "\end{frame} undefined" errors; swapping the class makes it compile.
_BEAMER_BODY_RE = re.compile(
    r'\\begin\s*\{(?:frame|columns|column|block|alertblock|exampleblock)\}'
    r'|\\column\s*\{'
    r'|\\frametitle\s*\{'
    r'|\\usetheme\s*\{'
    r'|\\usecolortheme\s*\{'
)
_DOCCLASS_SWAP_RE = re.compile(
    r'\\documentclass\s*(\[[^\]]*\])?\s*\{([^{}]+)\}'
)


def _looks_like_beamer_body(code: str) -> bool:
    return _BEAMER_BODY_RE.search(_strip_tex_comments(code)) is not None


def _promote_to_beamer(code: str) -> Tuple[str, Optional[str]]:
    """
    Rewrites the first `\\documentclass{...}` to `\\documentclass{beamer}`, keeping
    the option list intact. Returns (new_code, prior_class) or (code, None) if the
    class is already beamer-derived or there is no documentclass line.
    """
    m = _DOCCLASS_SWAP_RE.search(code)
    if not m:
        return code, None
    prior = m.group(2).strip()
    low = prior.lower()
    # Already a beamer or beamer-flavoured class.
    if low == "beamer" or low.endswith("beamerposter"):
        return code, None
    opts = m.group(1) or ""
    new = f"\\documentclass{opts}{{beamer}}"
    return code[:m.start()] + new + code[m.end():], prior


# Engine-detection conditionals (iftex / ifpdf / ifxetex / ifluatex) and the branch
# pdfLaTeX actually executes. A dual-engine template guards its fontspec setup behind
# `\ifPDFTeX ... \else ... \fi` (newtx under pdfLaTeX, system fonts under Xe/Lua); only
# the branch pdfLaTeX runs should decide whether it really needs a Unicode engine.
_ENGINE_IF = {
    "ifpdftex": "then", "ifpdf": "then",
    "ifxetex": "else", "ifluatex": "else", "ifvtex": "else",
}
_CTRLWORD_RE = re.compile(r"\\([A-Za-z@]+)")


def _pdflatex_active_source(latex_code: str) -> str:
    """
    The part of the source pdfLaTeX would actually compile, with the inactive branch of each
    engine conditional removed. Comments are stripped first (a commented-out `\\setmainfont`
    must not force a switch). Non-engine conditionals (`\\ifnum`, `\\ifx`, custom `\\if...`) are
    tracked only for `\\fi` balancing so nested `\\else`/`\\fi` pair with the right conditional,
    but their branches are left untouched.
    """
    code = _strip_tex_comments(latex_code or "")
    stack: List[Dict[str, Any]] = []
    drops: List[Tuple[int, int]] = []
    for m in _CTRLWORD_RE.finditer(code):
        name = m.group(1)
        low = name.lower()
        if name == "fi":
            if not stack:
                continue
            top = stack.pop()
            if not top["engine"]:
                continue
            els = top["else"]
            if top["keep"] == "then":
                if els is not None:          # drop the else-branch (… \else → … \fi)
                    drops.append((els[0], m.end()))
            else:                             # keep the else-branch
                if els is not None:          # drop the then-branch (\if… → \else)
                    drops.append((top["start"], els[1]))
                else:                         # no else-branch: the whole then-branch goes
                    drops.append((top["start"], m.end()))
        elif name == "else":
            if stack and stack[-1]["engine"] and stack[-1]["else"] is None:
                stack[-1]["else"] = (m.start(), m.end())
        elif name == "or":
            continue
        elif low.startswith("if"):
            if low in _ENGINE_IF:
                stack.append({"engine": True, "keep": _ENGINE_IF[low],
                              "start": m.start(), "else": None})
            else:
                stack.append({"engine": False})
    if not drops:
        return code
    drops.sort()
    out: List[str] = []
    pos = 0
    for a, b in drops:
        if a < pos:            # nested inside an already-removed branch
            pos = max(pos, b)
            continue
        out.append(code[pos:a])
        pos = b
    out.append(code[pos:])
    return "".join(out)


def needs_unicode_engine(latex_code: str) -> bool:
    """
    True when the document can only be compiled with XeLaTeX / LuaLaTeX.

    LLM-generated documents that compile on Overleaf (where the project's
    compiler is set to XeLaTeX) routinely load `fontspec`, `unicode-math`,
    `polyglossia`, or select a system font. Under pdfLaTeX those fail with a
    fatal "requires XeTeX or LuaTeX" error, so when the caller left the engine
    at its default we switch to XeLaTeX automatically.

    Markers that sit inside the non-pdfTeX branch of an `\\ifPDFTeX`/`\\ifxetex` guard do
    NOT count: a dual-engine document that falls back to newtx/`\\usepackage[T1]{fontenc}`
    under pdfLaTeX must stay on pdfLaTeX (switching it to XeLaTeX picks the system-font
    branch, whose fonts may not be installed, and renders a text-less PDF).
    """
    code = _pdflatex_active_source(latex_code or "")
    return any(m in code for m in _UNICODE_ENGINE_MARKERS)


def is_heavy_document(latex_code: str, extra_sources: Optional[Iterable[str]] = None) -> bool:
    """
    Documents with lots of TikZ/pgfplots or great length need a longer budget.

    ``extra_sources`` are the project's other ``.tex`` files. They matter more
    than the main file does: a real thesis has a main.tex of thirty lines that
    does nothing but ``\\input`` its chapters, so judged on that file alone the
    heaviest document in the project looks like the lightest one there is, gets
    the short budget, and times out.
    """
    code = latex_code or ""
    if extra_sources:
        code = code + "\n" + "\n".join(src or "" for src in extra_sources)
    if len(code) > 60000:
        return True
    if "pgfplots" in code or r"\addplot" in code:
        return True
    if (code.count(r"\begin{tikzpicture}") + code.count(r"\tikz")) >= 6:
        return True
    return False


def _bibliography_backend(latex_code: str) -> Optional[str]:
    """
    Which bibliography tool a direct (non-latexmk) compile must run, or None.

    `biblatex` defaults to biber unless `backend=bibtex` is set; a classic
    `\\bibliography{...}` + `\\bibliographystyle{...}` uses bibtex.
    """
    code = latex_code or ""
    has_biblatex = "biblatex" in code and r"\usepackage" in code
    if has_biblatex or r"\addbibresource" in code or r"\printbibliography" in code:
        return "bibtex" if "backend=bibtex" in code else "biber"
    if r"\bibliography{" in code or r"\bibliographystyle{" in code:
        return "bibtex"
    return None


# --- Bibliography pipeline helpers -----------------------------------------------------
_COMMENT_RE = re.compile(r"(?<!\\)%.*")
_CITE_RE = re.compile(r"\\(?:[A-Za-z]*cite[A-Za-z]*|nocite)\*?\s*(?:\[[^\]]*\]\s*)*\{([^{}]*)\}")
_BIB_TARGET_RE = re.compile(r"\\bibliography\s*\{([^{}]*)\}")
_ADD_BIB_RE = re.compile(r"\\addbibresource\s*(?:\[[^\]]*\])?\s*\{([^{}]*)\}")
_HYPERREF_LOADED_RE = re.compile(
    r"\\(?:usepackage|RequirePackage)\s*(?:\[[^\]]*\])?\s*\{[^{}]*\bhyperref\b[^{}]*\}|\\hypersetup\b")
_DOCCLASS_RE = re.compile(r"\\documentclass\s*(?:\[[^\]]*\])?\s*\{([^{}]*)\}")
_BEGIN_DOC_RE = re.compile(r"\\begin\s*\{document\}")
# Classes that load hyperref themselves, and packages that must be loaded AFTER it
# (so appending hyperref at the end of the preamble would break them).
_HYPERREF_CLASSES = {"beamer", "acmart"}
_AFTER_HYPERREF_PKGS = ("cleveref", "bookmark", "hypcap", "glossaries", "glossaries-extra", "hyperxmp", "pdfx")
_BIB_NOTE_MAX = 600


def _strip_tex_comments(text: str) -> str:
    return _COMMENT_RE.sub("", text or "")


def _project_tex_text(main_code: str, tmpdir: Path, extra_suffixes=(".tex",),
                      main_path: Optional[Path] = None) -> str:
    """
    main.tex plus every other source file the compile can read (\\input/\\include chapters).
    ``main_path`` is the main document on disk (excluded, since ``main_code`` is its
    compile copy); by default every file named main.tex is taken to be it.
    """
    parts = [main_code or ""]
    main_resolved = main_path.resolve() if main_path is not None else None
    try:
        for item in sorted(tmpdir.rglob("*")):
            is_main = (item.resolve() == main_resolved) if main_resolved is not None else item.name == "main.tex"
            if (item.is_file() and item.suffix.lower() in extra_suffixes
                    and not is_main and item.stat().st_size < 4_000_000):
                parts.append(item.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        pass
    return "\n".join(parts)


_INPUT_CMD_RE = re.compile(
    r"\\(?:input|include|subfile|InputIfFileExists|includefrom|inputfrom|subincludefrom|subinputfrom|"
    r"import|subimport)\*?\s*(?:\{([^{}]*)\}\s*)?\{([^{}]*)\}|\\input\s+([^\s{}\\%]+)")


def _reachable_tex_text(main_code: str, workdir: Path, tmpdir: Path, max_files: int = 400) -> Tuple[str, bool]:
    """
    The main document plus every file it reaches through \\input / \\include /
    \\subfile / \\import (transitively), resolved like TeX would (the main file's
    directory, the including file's directory for \\import, then the project tree).
    Returns (text, complete) — ``complete`` is False when a target could not be
    resolved statically (a macro in the path), so callers can fall back to the
    whole project.
    """
    root = tmpdir.resolve()
    index: Dict[str, List[Path]] = {}
    for f in root.rglob("*.tex"):
        if f.is_file():
            index.setdefault(f.name.lower(), []).append(f)
    parts = [main_code or ""]
    seen: set = set()
    complete = True
    queue: List[Tuple[str, Path]] = [(main_code or "", workdir)]
    while queue and len(seen) < max_files:
        text, here = queue.pop(0)
        for m in _INPUT_CMD_RE.finditer(_strip_tex_comments(text)):
            sub_dir, target = (m.group(1) or "").strip(), (m.group(2) or m.group(3) or "").strip()
            if not target:
                continue
            if "\\" in target or "#" in target or "\\" in sub_dir:
                complete = False
                continue
            names = [target] if target.lower().endswith(".tex") else [target + ".tex", target]
            found = None
            for base in ([here / sub_dir] if sub_dir else []) + [workdir, here]:
                for n in names:
                    cand = base / n
                    if cand.is_file():
                        found = cand
                        break
                if found:
                    break
            if found is None:
                for n in names:
                    tail = [p for p in Path(n).parts if p not in (".", "..")]
                    for f in index.get(tail[-1].lower(), []) if tail else []:
                        if [x.lower() for x in f.relative_to(root).parts[-len(tail):]] == [x.lower() for x in tail]:
                            found = f
                            break
                    if found:
                        break
            if found is None:
                continue
            try:
                key = found.resolve()
            except OSError:
                continue
            if key in seen:
                continue
            seen.add(key)
            try:
                if key.stat().st_size > 4_000_000:
                    continue
                sub_text = key.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            parts.append(sub_text)
            queue.append((sub_text, key.parent if sub_dir else here))
    return "\n".join(parts), complete


def _cite_keys(code: str) -> List[str]:
    keys: List[str] = []
    for m in _CITE_RE.finditer(_strip_tex_comments(code)):
        for k in m.group(1).split(","):
            k = k.strip()
            if k and k != "*" and k not in keys:
                keys.append(k)
    return keys


def _bib_targets(code: str) -> List[str]:
    """Relative .bib paths named by \\bibliography{a,b} and \\addbibresource{x.bib}."""
    code = _strip_tex_comments(code)
    out: List[str] = []
    for m in _BIB_TARGET_RE.finditer(code):
        for name in m.group(1).split(","):
            name = name.strip()
            if name:
                out.append(name if name.lower().endswith(".bib") else name + ".bib")
    for m in _ADD_BIB_RE.finditer(code):
        name = m.group(1).strip()
        if name and not re.match(r"[a-z]+://", name, re.I):
            out.append(name)
    return list(dict.fromkeys(out))


def _generate_stub_bibs(tmpdir: Path, project_text: str, base_dir: Optional[Path] = None) -> List[str]:
    """
    Writes a placeholder .bib for every bibliography target that has no file, with one
    @misc entry per citation key, so a document whose references have not been added yet
    still compiles and its citations resolve. Returns the generated paths.
    Inline thebibliography/\\bibitem documents name no target, so nothing is generated.
    """
    keys = _cite_keys(project_text)
    root = tmpdir.resolve()
    base = base_dir or tmpdir
    generated: List[str] = []
    for target in _bib_targets(project_text):
        dest = (base / target).resolve()
        if root not in dest.parents or dest.exists():
            continue
        # BIBINPUTS searches the project tree recursively: a refs.bib anywhere under
        # the project is what bibtex/biber will read, and a stub must not shadow it.
        tail = [p for p in Path(target).parts if p not in (".", "..")]
        if tail and any(
                [x.lower() for x in f.relative_to(root).parts[-len(tail):]] == [x.lower() for x in tail]
                for f in root.rglob(tail[-1]) if f.is_file()):
            continue
        entries = [f"@misc{{{k},\n  title = {{{k}}},\n  note = {{Reference not yet added}}\n}}\n" for k in keys]
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text("% Placeholder generated by the compiler: no bibliography file was provided.\n"
                            + "\n".join(entries), encoding="utf-8")
            generated.append(dest.relative_to(root).as_posix() if base_dir is not None else target)
        except OSError:
            continue
    return generated


def _has_citations(code: str) -> bool:
    code = _strip_tex_comments(code)
    return bool(_CITE_RE.search(code) or r"\printbibliography" in code or r"\begin{thebibliography}" in code)


def _inject_hyperref(main_code: str, project_text: str, tmpdir: Optional[Path] = None) -> str:
    """
    Returns main_code with `\\usepackage[hidelinks]{hyperref}` added, or main_code unchanged.

    Without hyperref a citation is plain text and the downloaded PDF has no links. This is
    applied to the COMPILE COPY only (never the user's source). It goes on the same line as
    \\begin{document} (end of the preamble, so it follows every package it must wrap) and adds
    no line, so TeX's reported line numbers still match the user's source.

    The load is wrapped in ``\\@ifpackageloaded{hyperref}``: a class or package the source
    scan cannot see (a TeX Live class such as elsarticle, a package that loads it
    internally) may already have loaded hyperref with other options, and a second
    ``\\usepackage[hidelinks]{hyperref}`` would then be an option clash.
    """
    visible = _strip_tex_comments(project_text)
    if not _has_citations(visible):
        return main_code
    cls = _DOCCLASS_RE.search(_strip_tex_comments(main_code))
    if cls and cls.group(1).strip().lower() in _HYPERREF_CLASSES:
        return main_code
    sources = visible
    if tmpdir is not None:  # a template .cls/.sty may already load it
        sources += "\n" + _project_tex_text("", tmpdir, (".cls", ".sty"))
    if _HYPERREF_LOADED_RE.search(sources) or re.search(r"\bhyperref\b", _strip_tex_comments(sources)):
        return main_code
    if any(re.search(r"\{[^{}]*\b" + re.escape(p) + r"\b[^{}]*\}", visible) for p in _AFTER_HYPERREF_PKGS):
        return main_code
    for m in _BEGIN_DOC_RE.finditer(main_code):
        line_start = main_code.rfind("\n", 0, m.start()) + 1
        if _COMMENT_RE.search(main_code[line_start:m.start()]):
            continue  # commented out
        return main_code[:m.start()] + _HYPERREF_INJECTION + main_code[m.start():]
    return main_code


_HYPERREF_INJECTION = (r"\makeatletter\@ifpackageloaded{hyperref}{}{\usepackage[hidelinks]{hyperref}}"
                       r"\makeatother")


def _run_bibliography(backend: str, tmpdir: Path, timeout: int, env: dict, notes: List[str],
                      jobname: str = "main") -> None:
    """Runs bibtex/biber; anything it complains about goes to ``notes`` (never to errors)."""
    try:
        rb = _run_tex([backend, jobname], cwd=tmpdir, timeout=timeout, env=env)
    except FileNotFoundError:
        notes.append(f"{backend} is not installed; the bibliography could not be built.")
        return
    except subprocess.TimeoutExpired:
        notes.append(f"{backend} timed out after {timeout}s; the bibliography may be incomplete.")
        return
    except Exception as exc:
        notes.append(f"{backend} failed to run: {exc}")
        return
    out = ((rb.stdout or "") + "\n" + (rb.stderr or "")).strip()
    if rb.returncode:
        lines = [ln.strip() for ln in out.splitlines()
                 if re.search(r"warning|error|couldn't|fatal|---line", ln, re.I)] or out.splitlines()[-6:]
        text = " | ".join(lines)
        if len(text) > _BIB_NOTE_MAX:
            text = text[:_BIB_NOTE_MAX] + "..."
        notes.append(f"{backend} reported problems (exit {rb.returncode}): {text}")


def _bib_note_diagnostic(message: str) -> Dict[str, Any]:
    return {"file": None, "line": None, "reported_line": None, "col": None, "token": None,
            "message": message, "located_by": None, "span": None, "context": "",
            "type": "BIBLIOGRAPHY", "severity": "warning", "suggested_action": "", "raw": message}


def augment_path_for_latex():
    """Augments system PATH with common MiKTeX and TeX Live installation locations on Windows."""
    if sys.platform == "win32":
        home = os.path.expanduser("~")
        common_win_paths = [
            r"C:\Program Files\MiKTeX\miktex\bin\x64",
            r"C:\Program Files (x86)\MiKTeX\miktex\bin\x64",
            r"C:\Program Files\MiKTeX\miktex\bin",
            os.path.join(home, r"AppData\Local\Programs\MiKTeX\miktex\bin\x64"),
            r"C:\texlive\2026\bin\windows",
            r"C:\texlive\2025\bin\windows",
            r"C:\texlive\2024\bin\windows",
            r"C:\texlive\2023\bin\windows",
        ]

        current_path = os.environ.get("PATH", "")
        found_paths = [p for p in common_win_paths if os.path.exists(p)]

        if found_paths:
            extra_path = os.path.pathsep.join(found_paths)
            if extra_path not in current_path:
                os.environ["PATH"] = f"{extra_path}{os.path.pathsep}{current_path}"


def clean_tex_syntax(text: str) -> str:
    """Strips TeX formatting commands, dimensions, font sizes, and environment syntax while preserving readable content."""
    if not text:
        return ""
    
    s = text.strip()
    
    # Ignore comments
    if s.startswith('%'):
        return ""
    s = re.sub(r'%.*$', '', s)

    # Ignore markdown code blocks or code fences if present in TeX source
    if s.startswith('```') or s.endswith('```'):
        return ""

    # Ignore TeX setup commands, macro definitions, Beamer color settings, and TikZ
    preamble_patterns = [
        r'^\s*\\documentclass',
        r'^\s*\\usepackage',
        r'^\s*\\renewcommand',
        r'^\s*\\newcommand',
        r'^\s*\\setlength',
        r'^\s*\\addtolength',
        r'^\s*\\cft',
        r'^\s*\\usetikzlibrary',
        r'^\s*\\definecolor',
        r'^\s*\\setbeamercolor',
        r'^\s*\\setbeamertemplate',
        r'^\s*\\setbeamerfont',
        r'^\s*\\titlegraphic',
        r'^\s*\\lstdefinestyle',
        r'^\s*\\lstset',
        r'^\s*\\geometry',
        r'^\s*\\fancy',
        r'^\s*\\captionsetup',
        r'^\s*\\pagestyle',
        r'^\s*\\thispagestyle',
        r'^\s*\\pagenumbering',
        r'^\s*\\setcounter',
        r'^\s*\\hypersetup',
        r'^\s*\\bibliographystyle',
        r'^\s*\\bibliography',
        r'^\s*\\usetheme',
        r'^\s*\\usecolortheme',
        r'^\s*\\usefonttheme',
        r'^\s*\\useoutertheme',
        r'^\s*\\useinnertheme',
        r'^\s*\\onehalfspacing',
        r'^\s*\\doublespacing',
        r'^\s*\\singlespacing',
        r'^\s*\\sloppy',
        r'^\s*\\headrulewidth',
        r'^\s*\\footrulewidth',
        r'^\s*\\node',
        r'^\s*\\draw',
        r'^\s*\\path',
        r'^\s*\\fill',
        r'^\s*\\clip',
        r'^\s*\\pgf',
        r'^\s*\\tikz',
        r'^\s*\\hrule',
        r'^\s*\\vrule',
        r'^\s*\\vspace',
        r'^\s*\\hspace',
        r'^\s*\\rule',
        r'^\s*\\centering',
        r'^\s*\\raggedright',
        r'^\s*\\raggedleft',
        r'^\s*\\vfill',
        r'^\s*\\hfill',
        r'^\s*\\pagebreak',
        r'^\s*\\clearpage',
        r'^\s*\\newpage',
    ]
    for pat in preamble_patterns:
        if re.search(pat, s, re.IGNORECASE):
            return ""

    # Ignore key=value style settings (e.g. backgroundcolor=..., commentstyle=..., tabsize=2, fg=white, bg=primary)
    if (re.match(r'^[a-zA-Z0-9_-]+\s*=\s*.*$', s) or re.match(r'^[a-zA-Z0-9_-]+,?\s*$', s)) and not s.startswith('•') and not s.startswith('\\item') and len(s.split()) < 4:
        return ""

    # Ignore standalone option brackets or raw dimensions like "[display]", "0pt", "40pt", "1822"
    if re.match(r'^\s*\[[^\]]*\]\s*$', s) or re.match(r'^\s*(?:\d+(?:\.\d+)?(?:cm|mm|in|pt|em|ex)?|\d+)\s*$', s):
        return ""

    # Replace inline formatting tags with temporary tokens before HTML escaping
    s = re.sub(r'\\textbf\{([^}]+)\}', r'___BOLD___\1___ENDBOLD___', s)
    s = re.sub(r'\\textit\{([^}]+)\}', r'___ITALIC___\1___ENDITALIC___', s)
    s = re.sub(r'\\cite\{([^}]+)\}', r'[\1]', s)
    s = re.sub(r'\\ref\{([^}]+)\}', r'(\1)', s)
    s = re.sub(r'\\item\s*', '• ', s)

    # Remove font size / spacing / style commands
    s = re.sub(r'\\fontsize\{[^}]*\}\{[^}]*\}', '', s)
    s = re.sub(r'\\selectfont', '', s)
    s = re.sub(r'\\vspace\*?\{[^}]*\}', '', s)
    s = re.sub(r'\\hspace\*?\{[^}]*\}', '', s)
    s = re.sub(r'\\setlength\{[^}]*\}\{[^}]*\}', '', s)
    s = re.sub(r'\\addtolength\{[^}]*\}\{[^}]*\}', '', s)
    s = re.sub(r'\\geometry\{[^}]*\}', '', s)
    s = re.sub(r'\\addcontentsline\{[^}]*\}\{[^}]*\}\{[^}]*\}', '', s)
    s = re.sub(r'\\captionsetup\[[^\]]*\]\{[^}]*\}', '', s)
    s = re.sub(r'\\captionsetup\{[^}]*\}', '', s)
    s = re.sub(r'\\color\{[^}]*\}', '', s)
    s = re.sub(r'\\textcolor\{[^}]*\}\{([^}]*)\}', r'\1', s)

    # Remove structural & environment commands
    s = re.sub(r'\\begin\{[^}]*\}(?:\[[^\]]*\])?(?:\{[^}]*\})*', '', s)
    s = re.sub(r'\\end\{[^}]*\}', '', s)
    s = re.sub(r'\\thispagestyle\{[^}]*\}', '', s)
    s = re.sub(r'\\pagestyle\{[^}]*\}', '', s)
    s = re.sub(r'\\pagenumbering\{[^}]*\}', '', s)

    # Remove image options like [width=4cm]
    s = re.sub(r'\[width=[^\]]+\]', '', s)
    s = re.sub(r'\[height=[^\]]+\]', '', s)

    # Remove remaining \command{arg} -> arg
    s = re.sub(r'\\[a-zA-Z]+\*?\{([^}]*)\}', r'\1', s)
    # Remove remaining standalone \command
    s = re.sub(r'\\[a-zA-Z]+\*?', '', s)
    
    # Remove leftover braces and TeX symbols
    s = re.sub(r'[{}\\]', '', s)
    
    # HTML escape ampersands and angle brackets to prevent ReportLab paraparser syntax errors
    s = s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    # Re-inject ReportLab supported HTML tags
    s = s.replace('___BOLD___', '<b>').replace('___ENDBOLD___', '</b>')
    s = s.replace('___ITALIC___', '<i>').replace('___ENDITALIC___', '</i>')

    return s.strip()


def generate_beamer_pdf(latex_code: str) -> str:
    """Renders LaTeX Beamer / Presentation documents into sleek multi-slide PDFs."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    slide_title_style = ParagraphStyle(
        'SlideTitle',
        parent=styles['Heading1'],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#1e1b4b'),
        fontName='Helvetica-Bold',
        spaceAfter=12
    )

    bullet_style = ParagraphStyle(
        'SlideBullet',
        parent=styles['BodyText'],
        fontSize=13,
        leading=18,
        textColor=colors.HexColor('#334155'),
        spaceAfter=8,
        leftIndent=15
    )

    slide_body_style = ParagraphStyle(
        'SlideBody',
        parent=styles['BodyText'],
        fontSize=13,
        leading=18,
        textColor=colors.HexColor('#1e293b'),
        spaceAfter=10
    )

    title_slide_title = ParagraphStyle(
        'PresTitle',
        parent=styles['Heading1'],
        fontSize=26,
        leading=32,
        alignment=1,
        textColor=colors.HexColor('#0f172a'),
        fontName='Helvetica-Bold',
        spaceAfter=14
    )

    title_slide_sub = ParagraphStyle(
        'PresSub',
        parent=styles['Normal'],
        fontSize=14,
        leading=18,
        alignment=1,
        textColor=colors.HexColor('#475569'),
        spaceAfter=20
    )

    story = []

    # Title Slide (Only add if explicit title or author metadata exists)
    title_m = re.search(r'\\title\{([^}]+)\}', latex_code)
    author_m = re.search(r'\\author\{([^}]+)\}', latex_code, re.DOTALL)
    institute_m = re.search(r'\\institute\{([^}]+)\}', latex_code, re.DOTALL)

    if title_m or author_m:
        title_text = clean_tex_syntax(title_m.group(1)) if title_m else ""
        author_text = clean_tex_syntax(author_m.group(1)) if author_m else ""
        inst_text = clean_tex_syntax(institute_m.group(1)) if institute_m else ""

        if title_text or author_text:
            story.append(Spacer(1, 40))
            if title_text:
                story.append(Paragraph(title_text, title_slide_title))
            if author_text or inst_text:
                sub_content = f"{author_text}<br/>{inst_text}" if inst_text else author_text
                story.append(Paragraph(sub_content, title_slide_sub))
            story.append(HRFlowable(width="80%", thickness=2, color=colors.HexColor("#6366f1"), spaceAfter=20))
            story.append(PageBreak())

    # Extract body section inside \begin{document}
    doc_match = re.search(r'\\begin\{document\}(.*?)\\end\{document\}', latex_code, re.DOTALL)
    body_code = doc_match.group(1) if doc_match else latex_code

    # Extract frames
    frames = re.findall(r'\\begin\{frame\}(.*?)\\end\{frame\}', body_code, re.DOTALL)

    if not frames:
        # If no explicit \begin{frame}, split by \chapter or \section
        sec_splits = re.split(r'\\(?:chapter|section)\{([^}]+)\}', body_code)
        if len(sec_splits) > 1:
            frames = []
            for i in range(1, len(sec_splits), 2):
                sec_title = sec_splits[i]
                sec_body = sec_splits[i+1] if i+1 < len(sec_splits) else ""
                frames.append(f"\\frametitle{{{sec_title}}}\n{sec_body}")
        else:
            frames = [body_code]

    active_slides = 0
    for idx, frame_content in enumerate(frames):
        lines = frame_content.split('\n')
        body_paras = []
        for line in lines:
            line_str = line.strip()
            if not line_str or 'frametitle' in line_str or '\\begin{document}' in line_str or '\\end{document}' in line_str or line_str.startswith('\\maketitle') or line_str.startswith('\\tableofcontents'):
                continue

            cleaned = clean_tex_syntax(line_str)
            if cleaned:
                if line_str.startswith('\\item') or line_str.startswith('•'):
                    body_paras.append(Paragraph(f"• {cleaned.lstrip('• ')}", bullet_style))
                else:
                    body_paras.append(Paragraph(cleaned, slide_body_style))

        frametitle_m = re.search(r'\\frametitle\{([^}]+)\}', frame_content)
        if not frametitle_m:
            frametitle_m = re.search(r'\\(?:chapter|section)\{([^}]+)\}', frame_content)

        frame_title = clean_tex_syntax(frametitle_m.group(1)) if frametitle_m else ""

        # Skip empty frames that have no title and no body text
        if not frame_title and not body_paras:
            continue

        if not frame_title:
            frame_title = f"Slide {active_slides + 1}"

        if story and not isinstance(story[-1], PageBreak):
            story.append(PageBreak())

        story.append(Paragraph(frame_title, slide_title_style))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0"), spaceAfter=14))
        story.extend(body_paras)
        story.append(Spacer(1, 15))
        active_slides += 1

    doc.build(story)
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode("utf-8")


def generate_fallback_pdf(latex_code: str, tmpdir: Optional[Path] = None) -> str:
    """
    Parses LaTeX code structure and generates a crisp PDF document using ReportLab
    when local TeX binary (pdflatex/tectonic) is missing or times out.
    """
    code_lower = latex_code.lower()
    if 'beamer' in code_lower or 'presentation' in code_lower or '\\begin{frame}' in latex_code or '\\frametitle' in latex_code:
        return generate_beamer_pdf(latex_code)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=18,
        leading=22,
        alignment=1,
        textColor=colors.HexColor('#0f172a'),
        fontName='Helvetica-Bold',
        spaceAfter=8
    )

    author_style = ParagraphStyle(
        'DocAuthor',
        parent=styles['Normal'],
        fontSize=10,
        leading=14,
        alignment=1,
        textColor=colors.HexColor('#475569'),
        fontName='Helvetica-Oblique',
        spaceAfter=14
    )

    section_style = ParagraphStyle(
        'DocSection',
        parent=styles['Heading2'],
        fontSize=13,
        leading=16,
        textColor=colors.HexColor('#1e1b4b'),
        fontName='Helvetica-Bold',
        spaceBefore=12,
        spaceAfter=6
    )

    body_style = ParagraphStyle(
        'DocBody',
        parent=styles['BodyText'],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#1e293b'),
        spaceAfter=8
    )

    abstract_style = ParagraphStyle(
        'DocAbstract',
        parent=styles['Normal'],
        fontSize=9.5,
        leading=13.5,
        textColor=colors.HexColor('#334155'),
        backColor=colors.HexColor('#f1f5f9'),
        borderColor=colors.HexColor('#cbd5e1'),
        borderWidth=0.5,
        borderPadding=8,
        spaceAfter=12
    )

    math_style = ParagraphStyle(
        'DocMath',
        parent=styles['Normal'],
        fontSize=10,
        leading=14,
        fontName='Courier-Oblique',
        alignment=1,
        textColor=colors.HexColor('#4338ca'),
        backColor=colors.HexColor('#eef2ff'),
        borderPadding=6,
        spaceAfter=8
    )

    story = []

    # Extract Title
    title_match = re.search(r'\\title\{([^}]+)\}', latex_code)
    title_text = clean_tex_syntax(title_match.group(1)) if title_match else "LaTeX Document"
    story.append(Paragraph(title_text, title_style))

    # Extract Author
    author_match = re.search(r'\\author\{([^}]+)\}', latex_code, re.DOTALL)
    if author_match:
        clean_author = clean_tex_syntax(author_match.group(1))
        if clean_author:
            story.append(Paragraph(clean_author, author_style))

    story.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#e2e8f0"), spaceAfter=10))

    # Extract Abstract
    abstract_match = re.search(r'\\begin\{abstract\}(.*?)\\end\{abstract\}', latex_code, re.DOTALL)
    if abstract_match:
        abstract_text = clean_tex_syntax(abstract_match.group(1))
        if abstract_text:
            story.append(Paragraph(f"<b>ABSTRACT — </b> {abstract_text}", abstract_style))

    # Parse body lines inside \begin{document}
    doc_match = re.search(r'\\begin\{document\}(.*?)\\end\{document\}', latex_code, re.DOTALL)
    body_code = doc_match.group(1) if doc_match else latex_code

    lines = body_code.split('\n')
    in_math_block = False
    math_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith('%'):
            continue

        if stripped.startswith('\\documentclass') or stripped.startswith('\\usepackage') or stripped.startswith('\\begin{document}') or stripped.startswith('\\end{document}') or stripped.startswith('\\maketitle') or stripped.startswith('\\bibliographystyle') or stripped.startswith('\\bibliography') or stripped.startswith('\\usetheme'):
            continue

        if stripped.startswith('\\begin{equation}') or stripped.startswith('\\begin{align}') or stripped.startswith('\\[') or stripped.startswith('$$'):
            in_math_block = True
            math_lines = []
            continue

        if stripped.startswith('\\end{equation}') or stripped.startswith('\\end{align}') or stripped.startswith('\\]') or stripped.startswith('$$'):
            in_math_block = False
            math_content = " ".join(math_lines)
            cleaned_math = clean_tex_syntax(math_content)
            if cleaned_math:
                story.append(Paragraph(f"[ Equation: {cleaned_math} ]", math_style))
            continue

        if in_math_block:
            math_lines.append(stripped)
            continue

        # Check for \includegraphics
        img_match = re.search(r'\\includegraphics(?:\[.*?\])?\{([^}]+)\}', stripped)
        if img_match:
            img_filename = img_match.group(1).strip()
            found_img_path = None
            if tmpdir:
                candidate = (tmpdir / img_filename).resolve()
                if candidate.exists() and candidate.is_file():
                    found_img_path = candidate
            if found_img_path:
                try:
                    from reportlab.platypus import Image as RLImage
                    story.append(RLImage(str(found_img_path), width=350, height=250, preserveAspectRatio=True))
                    story.append(Spacer(1, 6))
                except Exception:
                    story.append(Paragraph(f"<b>[ Asset Image: {img_filename} ]</b>", body_style))
            else:
                story.append(Paragraph(f"<b>[ Asset Image: {img_filename} ]</b>", body_style))
            continue

        section_match = re.match(r'\\section\{([^}]+)\}', stripped)
        if section_match:
            sec_title = clean_tex_syntax(section_match.group(1))
            if sec_title:
                story.append(Paragraph(sec_title.upper(), section_style))
            continue

        subsection_match = re.match(r'\\subsection\{([^}]+)\}', stripped)
        if subsection_match:
            subsec_title = clean_tex_syntax(subsection_match.group(1))
            if subsec_title:
                story.append(Paragraph(subsec_title, section_style))
            continue

        # Regular line
        cleaned = clean_tex_syntax(stripped)
        if len(cleaned) > 2:
            story.append(Paragraph(cleaned, body_style))

    doc.build(story)
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode("utf-8")


def write_file_safely(tmpdir: Path, filename: str, data_base64: str):
    """Safely decodes and writes a base64 file asset to tmpdir preventing path traversal."""
    resolved_path = (tmpdir / filename).resolve()
    if not str(resolved_path).startswith(str(tmpdir.resolve())):
        raise ValueError(f"Path traversal detected in asset filename: {filename}")

    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    raw_bytes = base64.b64decode(data_base64)
    resolved_path.write_bytes(raw_bytes)


def create_sample_image(target_path: Path, label: str):
    """Creates a clean sample/placeholder image file so LaTeX compilation succeeds natively with the real layout."""
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        ext = target_path.suffix.lower()
        if ext == ".pdf":
            try:
                from reportlab.pdfgen import canvas
                c = canvas.Canvas(str(target_path), pagesize=(500, 350))
                c.setFillColorRGB(0.93, 0.95, 0.98)
                c.rect(0, 0, 500, 350, fill=1, stroke=0)
                c.setStrokeColorRGB(0.7, 0.75, 0.85)
                c.setLineWidth(2)
                c.rect(10, 10, 480, 330, fill=0, stroke=1)
                c.setFillColorRGB(0.2, 0.25, 0.35)
                c.setFont("Helvetica-Bold", 18)
                c.drawCentredString(250, 185, "SAMPLE IMAGE")
                c.setFont("Helvetica", 11)
                c.drawCentredString(250, 155, label[:40])
                c.save()
                return
            except Exception:
                pass

        from PIL import Image, ImageDraw
        width, height = 600, 400
        img = Image.new("RGB", (width, height), color=(241, 245, 249))
        draw = ImageDraw.Draw(img)
        # Outer border
        draw.rectangle([(8, 8), (width - 8, height - 8)], outline=(203, 213, 225), width=3)
        # Diagonal accent lines
        draw.line([(8, 8), (width - 8, height - 8)], fill=(226, 232, 240), width=2)
        draw.line([(8, height - 8), (width - 8, 8)], fill=(226, 232, 240), width=2)
        # Center box
        draw.rectangle([(110, 130), (490, 270)], fill=(255, 255, 255), outline=(148, 163, 184), width=2)
        # Text
        draw.text((width // 2, 175), "SAMPLE IMAGE", fill=(30, 41, 59), anchor="mm")
        draw.text((width // 2, 220), label[:45], fill=(100, 116, 139), anchor="mm")

        fmt = "JPEG" if ext in [".jpg", ".jpeg"] else "PNG"
        img.save(str(target_path), format=fmt)
    except Exception as e:
        logger.warning(f"Failed to create sample image at {target_path}: {e}")


# Extensions graphicx tries for an \includegraphics target without one (pdfTeX, XeTeX
# and LuaTeX driver lists combined), in its own order, plus upper-case variants.
_GRAPHIC_EXTS = (".pdf", ".png", ".jpg", ".jpeg", ".mps", ".jbig2", ".jb2", ".eps", ".ps",
                 ".bmp", ".tif", ".tiff", ".gif", ".svg", ".webp")
_INCLUDEGRAPHICS_RE = re.compile(r"\\includegraphics\s*\*?\s*(?:\[[^\]]*\]\s*)*\{([^{}]+)\}")
_GRAPHICSPATH_RE = re.compile(r"\\graphicspath\s*\{((?:\s*\{[^{}]*\}\s*)+)\}")


def _graphicspath_dirs(text: str) -> List[str]:
    dirs: List[str] = []
    for m in _GRAPHICSPATH_RE.finditer(_strip_tex_comments(text or "")):
        for d in re.findall(r"\{([^{}]*)\}", m.group(1)):
            d = d.strip()
            if d and d not in dirs:
                dirs.append(d)
    return dirs


def _graphic_names(target: str) -> List[str]:
    """The file names graphicx would try for ``target``."""
    names = [target]
    ext = os.path.splitext(target)[1].lower()
    if ext not in _GRAPHIC_EXTS:
        for e in _GRAPHIC_EXTS:
            names.append(target + e)
            names.append(target + e.upper())
    return names


def resolve_graphic(target: str, tmpdir: Path, base_dir: Optional[Path] = None,
                    graphicspath: Iterable[str] = (), _index: Optional[Dict[str, List[Path]]] = None
                    ) -> Optional[Path]:
    """
    Where TeX would find an \\includegraphics target, or None: relative to the main
    file's directory, each \\graphicspath entry, then a recursive search of the
    project (TEXINPUTS carries ``<project>//``, so kpathsea finds ``fig/plot`` as any
    ``…/fig/plot.png`` in the tree), trying every extension graphicx tries.
    """
    base = base_dir or tmpdir
    root = tmpdir.resolve()
    names = _graphic_names(target)
    for d in [""] + list(graphicspath):
        for n in names:
            cand = (base / d / n) if d else (base / n)
            try:
                if cand.is_file():
                    return cand
            except OSError:
                continue
    # Recursive search (kpathsea's `//`): match on the trailing path components.
    if _index is None:
        _index = {}
        for f in root.rglob("*"):
            if f.is_file():
                _index.setdefault(f.name.lower(), []).append(f)
    for n in names:
        tail = Path(n.lstrip("./")).parts
        if not tail:
            continue
        for f in _index.get(tail[-1].lower(), []):
            parts = f.relative_to(root).parts
            if len(parts) >= len(tail) and [p.lower() for p in parts[-len(tail):]] == [p.lower() for p in tail]:
                return f
    return None


def ensure_sample_images_exist(latex_code: str, tmpdir: Path, base_dir: Optional[Path] = None,
                               search_text: Optional[str] = None) -> List[str]:
    r"""
    For every \includegraphics target that exists NOWHERE TeX would look — the main
    file's directory (``base_dir``), each \graphicspath entry, or anywhere in the
    project tree — writes a clean "SAMPLE IMAGE" placeholder so the layout still
    builds. A placeholder is never written over, or in front of, a real file:
    because TEXINPUTS starts with ".", a placeholder at ./plot.png used to shadow
    the real figures/plot.png. Returns the placeholders written (relative paths).

    ``search_text`` is every source the compile reads (chapters reference figures
    too); it defaults to ``latex_code``.
    """
    text = _strip_tex_comments(search_text if search_text is not None else latex_code)
    base = (base_dir or tmpdir)
    gpath = _graphicspath_dirs(text)
    root = tmpdir.resolve()
    index: Dict[str, List[Path]] = {}
    for f in root.rglob("*"):
        if f.is_file():
            index.setdefault(f.name.lower(), []).append(f)
    written: List[str] = []
    for raw_path in _INCLUDEGRAPHICS_RE.findall(text):
        clean_path = raw_path.strip().strip('"').strip("'")
        # A macro / parameter in the path cannot be resolved here; leave it to TeX.
        if not clean_path or "\\" in clean_path or "#" in clean_path or os.path.isabs(clean_path):
            continue
        if resolve_graphic(clean_path, tmpdir, base, gpath, index) is not None:
            continue
        has_ext = os.path.splitext(clean_path)[1].lower() in _GRAPHIC_EXTS
        target = (base / clean_path) if has_ext else (base / f"{clean_path}.png")
        try:
            resolved = target.resolve()
        except OSError:
            continue
        if root not in resolved.parents or resolved.exists():
            continue
        create_sample_image(resolved, Path(clean_path).name)
        if resolved.is_file():
            rel = resolved.relative_to(root).as_posix()
            written.append(rel)
            index.setdefault(resolved.name.lower(), []).append(resolved)
    return written


# --- Font substitution preflight ---------------------------------------------------------
# fontspec selects system fonts by family name. A family the server does not have makes
# XeLaTeX/LuaLaTeX error out or draw a text-less PDF. Before compiling, each such family is
# rewritten IN THE COMPILE COPY ONLY to an installed substitute: metric-compatible first,
# then by class. Substitutes are taken from fontconfig when installed there, else loaded
# by file name from the TeX tree (where TeX Live ships them).
_FONT_SELECTOR_RE = re.compile(
    r"\\(setmainfont|setsansfont|setmonofont|setromanfont|setmathfont|setmathrm|setboldmathrm|"
    r"newfontfamily|newfontface|fontspec|setCJKmainfont|setCJKsansfont|setCJKmonofont)\b")

# family (normalised) -> candidate substitutes, best first.
_METRIC_SUBS: Dict[str, Tuple[str, ...]] = {
    "calibri": ("Carlito",),
    "cambria": ("Caladea",),
    "cambriamath": ("TeX Gyre Termes Math", "Latin Modern Math"),
    "helvetica": ("TeX Gyre Heros", "Liberation Sans"),
    "helveticaneue": ("TeX Gyre Heros", "Liberation Sans"),
    "arial": ("Arial", "Liberation Sans", "TeX Gyre Heros"),
    "timesnewroman": ("Times New Roman", "Liberation Serif", "TeX Gyre Termes"),
    "times": ("Times New Roman", "Liberation Serif", "TeX Gyre Termes"),
    "couriernew": ("Courier New", "Liberation Mono", "TeX Gyre Cursor"),
    "courier": ("Liberation Mono", "TeX Gyre Cursor"),
    "palatino": ("TeX Gyre Pagella",),
    "palatinolinotype": ("TeX Gyre Pagella",),
    "bookantiqua": ("TeX Gyre Pagella",),
    "garamond": ("EB Garamond",),
    "ebgaramond": ("EB Garamond",),
    "consolas": ("Inconsolata", "DejaVu Sans Mono"),
    "segoeui": ("Noto Sans", "DejaVu Sans"),
    "menlo": ("DejaVu Sans Mono",),
    "monaco": ("DejaVu Sans Mono",),
    "georgia": ("TeX Gyre Schola", "DejaVu Serif"),
    "verdana": ("DejaVu Sans",),
    "tahoma": ("DejaVu Sans",),
    "centurygothic": ("TeX Gyre Adventor",),
    "bookmanoldstyle": ("TeX Gyre Bonum",),
}
_CLASS_SUBS = {
    "serif": ("TeX Gyre Termes", "Liberation Serif", "DejaVu Serif"),
    "sans": ("TeX Gyre Heros", "Liberation Sans", "DejaVu Sans"),
    "mono": ("Latin Modern Mono", "Liberation Mono", "DejaVu Sans Mono"),
    "math": ("Latin Modern Math", "TeX Gyre Termes Math"),
}
# Families TeX Live ships as files: base name, extension, {variant key: suffix}.
_TEXMF_FONTS: Dict[str, Tuple[str, str, Dict[str, str]]] = {
    "carlito": ("Carlito", ".ttf", {"UprightFont": "*-Regular", "BoldFont": "*-Bold",
                                     "ItalicFont": "*-Italic", "BoldItalicFont": "*-BoldItalic"}),
    "caladea": ("Caladea", ".ttf", {"UprightFont": "*-Regular", "BoldFont": "*-Bold",
                                     "ItalicFont": "*-Italic", "BoldItalicFont": "*-BoldItalic"}),
    "ebgaramond": ("EBGaramond", ".otf", {"UprightFont": "*-Regular", "BoldFont": "*-Bold",
                                           "ItalicFont": "*-Italic", "BoldItalicFont": "*-BoldItalic"}),
    "inconsolata": ("Inconsolatazi4", ".otf", {"UprightFont": "*-Regular", "BoldFont": "*-Bold"}),
    "latinmodernmono": ("lmmono10", ".otf", {"UprightFont": "*-regular", "ItalicFont": "*-italic"}),
    "latinmodernmath": ("latinmodern-math", ".otf", {}),
    "texgyretermesmath": ("texgyretermes-math", ".otf", {}),
    "notosans": ("NotoSans", ".ttf", {"UprightFont": "*-Regular", "BoldFont": "*-Bold",
                                       "ItalicFont": "*-Italic", "BoldItalicFont": "*-BoldItalic"}),
    "dejavusansmono": ("DejaVuSansMono", ".ttf", {"UprightFont": "*", "BoldFont": "*-Bold",
                                                   "ItalicFont": "*-Oblique", "BoldItalicFont": "*-BoldOblique"}),
}
for _gy in ("termes", "heros", "pagella", "cursor", "schola", "adventor", "bonum"):
    _TEXMF_FONTS["texgyre" + _gy] = ("texgyre" + _gy, ".otf", {
        "UprightFont": "*-regular", "BoldFont": "*-bold", "ItalicFont": "*-italic",
        "BoldItalicFont": "*-bolditalic"})

_FC_FAMILIES: Optional[set] = None
_KPSE_CACHE: Dict[str, bool] = {}


def _norm_family(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _fc_families() -> set:
    """Normalised family names fontconfig knows (cached for the process)."""
    global _FC_FAMILIES
    if _FC_FAMILIES is None:
        fams: set = set()
        try:
            out = subprocess.run(["fc-list", ":", "family"], capture_output=True, timeout=30)
            for line in (out.stdout or b"").decode("utf-8", "replace").splitlines():
                for fam in line.split(","):
                    if fam.strip():
                        fams.add(_norm_family(fam))
        except Exception:
            pass
        _FC_FAMILIES = fams
    return _FC_FAMILIES


def _kpse_has(filename: str) -> bool:
    if filename not in _KPSE_CACHE:
        try:
            out = subprocess.run(["kpsewhich", filename], capture_output=True, timeout=20)
            _KPSE_CACHE[filename] = bool((out.stdout or b"").strip())
        except Exception:
            _KPSE_CACHE[filename] = False
    return _KPSE_CACHE[filename]


def _substitute_spec(family: str) -> Optional[Tuple[str, Dict[str, str]]]:
    """(name to put in the braces, extra fontspec options) for an installed substitute."""
    key = _norm_family(family)
    if key in _fc_families():
        return family, {}
    spec = _TEXMF_FONTS.get(key)
    if spec:
        base, ext, variants = spec
        first = variants.get("UprightFont", "*").replace("*", base)
        if _kpse_has(first + ext):
            opts = {"Extension": ext}
            for k, v in variants.items():
                if _kpse_has(v.replace("*", base) + ext):
                    opts[k] = v
            return base, opts
    return None


def _font_class(selector: str, family: str) -> str:
    low = family.lower()
    if selector in ("setmathfont",) or "math" in low:
        return "math"
    if selector in ("setmonofont", "setCJKmonofont") or any(
            k in low for k in ("mono", "code", "consol", "courier", "menlo", "monaco", "typewriter")):
        return "mono"
    if selector in ("setsansfont", "setCJKsansfont") or any(
            k in low for k in ("sans", "arial", "helvetica", "calibri", "segoe", "verdana", "tahoma",
                               "roboto", "lato", "inter", "open", "gothic", "futura", "gill")):
        return "sans"
    return "serif"


def _skip_balanced(text: str, i: int, open_ch: str, close_ch: str) -> int:
    """Index just past the group opening at ``text[i] == open_ch`` (or -1 if unbalanced)."""
    depth = 0
    for j in range(i, len(text)):
        c = text[j]
        if c == "\\":
            continue
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return j + 1
    return -1


def _parse_font_command(text: str, pos: int, selector: str):
    """
    Parses ``\\sel [\\cs] [opts] {Family} [opts]`` starting at ``pos`` (just after the
    selector). Returns (end, pre_opts_span, name_span, post_opts_span) or None.
    """
    i = pos
    n = len(text)

    def ws(k):
        while k < n and text[k] in " \t\r\n":
            k += 1
        return k
    i = ws(i)
    if selector in ("newfontfamily", "newfontface"):
        if i < n and text[i] == "\\":
            m = re.match(r"\\[A-Za-z@]+", text[i:])
            if not m:
                return None
            i = ws(i + m.end())
        elif i < n and text[i] == "{":
            e = _skip_balanced(text, i, "{", "}")
            if e < 0:
                return None
            i = ws(e)
        else:
            return None
    pre = None
    if i < n and text[i] == "[":
        e = _skip_balanced(text, i, "[", "]")
        if e < 0:
            return None
        pre = (i, e)
        i = ws(e)
    if i >= n or text[i] != "{":
        return None
    e = _skip_balanced(text, i, "{", "}")
    if e < 0:
        return None
    name = (i + 1, e - 1)
    end = e
    post = None
    k = e
    # Trailing options on the same logical command (fontspec >= 2.4), possibly after spaces.
    k2 = k
    while k2 < n and text[k2] in " \t":
        k2 += 1
    if k2 < n and text[k2] == "[":
        e2 = _skip_balanced(text, k2, "[", "]")
        if e2 > 0:
            post = (k2, e2)
            end = e2
    return end, pre, name, post


def substitute_missing_fonts(code: str) -> Tuple[str, List[Tuple[str, str]]]:
    """
    Rewrites fontspec family selectors naming a font the server lacks. Returns
    (new_code, [(family, substitute), ...]). Families loaded from a project font file
    (Path= / Extension= options, or a file name) and installed families are left alone.
    Never adds or removes a line.
    """
    if not code or "\\" not in code:
        return code, []
    out: List[str] = []
    subs: List[Tuple[str, str]] = []
    pos = 0
    for m in _FONT_SELECTOR_RE.finditer(code):
        if m.start() < pos:
            continue
        line_start = code.rfind("\n", 0, m.start()) + 1
        if _COMMENT_RE.search(code[line_start:m.start()]):
            continue  # commented out
        parsed = _parse_font_command(code, m.end(), m.group(1))
        if not parsed:
            continue
        end, pre, name_span, post = parsed
        family = code[name_span[0]:name_span[1]].strip()
        opts_text = (code[pre[0]:pre[1]] if pre else "") + (code[post[0]:post[1]] if post else "")
        if (not family or "\\" in family or "#" in family
                or re.search(r"\b(?:Path|Extension)\s*=", opts_text)
                or re.search(r"\.(?:otf|ttf|ttc|pfb|afm)\s*$", family, re.I)
                or family.startswith("[")):
            continue
        if _norm_family(family) in _fc_families():
            continue
        candidates = list(_METRIC_SUBS.get(_norm_family(family), ())) + list(
            _CLASS_SUBS[_font_class(m.group(1), family)])
        chosen = None
        for cand in candidates:
            spec = _substitute_spec(cand)
            if spec:
                chosen = (cand, spec)
                break
        if chosen is None:
            continue
        cand, (new_name, extra) = chosen
        user_opts = []
        for a_b in (pre, post):
            if a_b:
                inner = code[a_b[0] + 1:a_b[1] - 1].strip()
                if inner:
                    user_opts.append(inner)
        if extra:
            # The substitute is loaded by file name; drop the user's per-face font
            # names (they name faces of the missing family) and keep the rest.
            kept = []
            for opt in ",".join(user_opts).split(","):
                if opt.strip() and not re.match(r"\s*(?:Upright|Bold|Italic|BoldItalic|Slanted|BoldSlanted|SmallCaps)Font\s*=", opt):
                    kept.append(opt.strip())
            kept += [f"{k}={v}" for k, v in extra.items()]
            opts = "[" + ", ".join(kept) + "]"
        else:
            opts = "[" + ", ".join(user_opts) + "]" if user_opts else ""
        head_end = pre[0] if pre else name_span[0] - 1
        cmd_head = code[m.start():head_end].rstrip()
        # keep any newlines that sat inside the replaced span so line numbers stay put
        span_nl = code[head_end:end].count("\n")
        out.append(code[pos:m.start()])
        out.append(cmd_head + "{" + new_name + "}" + opts + ("\n" * span_nl))
        pos = end
        subs.append((family, cand))
    out.append(code[pos:])
    return "".join(out), list(dict.fromkeys(subs))


def _font_notice(subs: List[Tuple[str, str]]) -> str:
    pairs = ", ".join(f"{a} → {b}" for a, b in subs)
    return (f"Font substitution: {pairs}. These fonts are not installed on the compile server; "
            f"the closest installed (metric-compatible where available) fonts were used. "
            f"Upload the font files to the project to use the originals.")


def _font_diagnostic(message: str) -> Dict[str, Any]:
    d = _bib_note_diagnostic(message)
    d["type"] = "FONT"
    return d


_TEMPLATE_ROOTS_CACHE: Optional[List[Path]] = None

def get_template_roots() -> List[Path]:
    global _TEMPLATE_ROOTS_CACHE
    if _TEMPLATE_ROOTS_CACHE is not None:
        return _TEMPLATE_ROOTS_CACHE
    templates_base_dir = Path(os.path.join(os.path.dirname(__file__), "templates")).resolve()
    template_roots = []
    if templates_base_dir.exists():
        for category_dir in sorted(templates_base_dir.iterdir()):
            if not category_dir.is_dir():
                continue
            if list(category_dir.glob("*.tex")):
                template_roots.append(category_dir)
            else:
                for tmpl_dir in sorted(category_dir.iterdir()):
                    if tmpl_dir.is_dir() and list(tmpl_dir.glob("*.tex")):
                        template_roots.append(tmpl_dir)
    _TEMPLATE_ROOTS_CACHE = template_roots
    return _TEMPLATE_ROOTS_CACHE


_CRITICAL_PACKAGES = {
    # Document structure & presentations
    "beamer", "beamertheme", "powerdot", "prosper",
    # Math & science
    "amsmath", "amssymb", "amsfonts", "amsthm", "mathtools", "bm", "physics", "siunitx",
    # Graphics & plotting
    "tikz", "pgfplots", "pgf", "graphicx", "graphics", "xcolor", "color", "tcolorbox", "adjustbox",
    # Layout & typography
    "geometry", "fancyhdr", "titlesec", "titling", "microtype", "setspace",
    # Fonts & engine-specific
    "fontspec", "unicode-math", "polyglossia", "babel", "inputenc", "fontenc",
    # Tables & floats
    "booktabs", "tabularx", "tabulary", "array", "longtable", "multirow", "multicol", "caption", "subcaption", "float",
    # Code & algorithms
    "listings", "minted", "algorithm", "algorithmic", "algorithm2e", "algpseudocode",
    # Citations & references
    "biblatex", "natbib", "cite", "hyperref", "url",
    # Lists & utils
    "enumitem", "etoolbox", "calc", "ifthen", "xparse", "expl3",
}


def _is_critical_package(pkg: str) -> bool:
    clean = pkg.strip().lower()
    if clean in _CRITICAL_PACKAGES:
        return True
    if clean.startswith(("beamertheme", "beamercolor", "beamerfont", "beamerinner", "beamerouter")):
        return True
    if clean.startswith(("tikz", "pgf", "amsmath", "amssymb", "firamath", "fontspec")):
        return True
    return False


def find_matched_template_roots(latex_code: str) -> List[Path]:
    """
    Finds all template directories whose assets (.cls, .sty, images, inputs)
    are referenced by the given LaTeX document.
    """
    code = latex_code or ""
    template_roots = get_template_roots()
    if not template_roots:
        return []

    # Extract themes, classes, packages, inputs, images
    theme_matches = set(re.findall(r"\\usetheme(?:\[[^\]]*\])?\{([a-zA-Z0-9_-]+)\}", code))
    color_theme_matches = set(re.findall(r"\\usecolortheme(?:\[[^\]]*\])?\{([a-zA-Z0-9_-]+)\}", code))
    font_theme_matches = set(re.findall(r"\\usefonttheme(?:\[[^\]]*\])?\{([a-zA-Z0-9_-]+)\}", code))
    inner_theme_matches = set(re.findall(r"\\useinnertheme(?:\[[^\]]*\])?\{([a-zA-Z0-9_-]+)\}", code))
    outer_theme_matches = set(re.findall(r"\\useoutertheme(?:\[[^\]]*\])?\{([a-zA-Z0-9_-]+)\}", code))
    doc_classes = set(re.findall(r"\\documentclass(?:\[[^\]]*\])?\{([a-zA-Z0-9_-]+)\}", code))

    pkg_blocks = re.findall(r"\\(?:usepackage|RequirePackage)(?:\[[^\]]*\])?\{([^}]+)\}", code)
    pkgs = set()
    for block in pkg_blocks:
        for p in block.split(","):
            clean_p = p.strip()
            if clean_p:
                pkgs.add(clean_p)

    input_matches = set(re.findall(r"\\(?:input|include)\{([^}]+)\}", code))
    graphics_matches = set(re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", code))
    graphics_basenames = {Path(g).name for g in graphics_matches}
    graphics_stems = {Path(g).stem for g in graphics_matches}

    matched_roots: List[Path] = []
    for tmpl_root in template_roots:
        tmpl_files = {
            f.name
            for f in tmpl_root.rglob("*")
            if f.is_file() and f.name not in ("main.tex", "metadata.json", "thumbnail.png")
        }
        matched = False
        for tf_name in tmpl_files:
            stem = Path(tf_name).stem
            # Document class match
            if tf_name.endswith(".cls") and stem in doc_classes:
                matched = True
                break
            # Package match
            if tf_name.endswith(".sty") and stem in pkgs:
                matched = True
                break
            # Beamer themes match
            if tf_name.endswith(".sty") and stem.startswith("beamertheme") and stem[11:] in theme_matches:
                matched = True
                break
            if tf_name.endswith(".sty") and stem.startswith("beamercolortheme") and stem[16:] in color_theme_matches:
                matched = True
                break
            if tf_name.endswith(".sty") and stem.startswith("beamerfonttheme") and stem[15:] in font_theme_matches:
                matched = True
                break
            if tf_name.endswith(".sty") and stem.startswith("beamerinnertheme") and stem[15:] in inner_theme_matches:
                matched = True
                break
            if tf_name.endswith(".sty") and stem.startswith("beameroutertheme") and stem[15:] in outer_theme_matches:
                matched = True
                break
            # Input / include file match
            if any(tf_name == inp or tf_name == f"{inp}.tex" or stem == inp for inp in input_matches):
                matched = True
                break
            # Graphic image file match
            if tf_name in graphics_basenames or stem in graphics_stems:
                matched = True
                break

        if matched:
            matched_roots.append(tmpl_root)

    return matched_roots


def load_project_text_file(project_id: Optional[str], rel_path: str = "main.tex") -> Optional[str]:
    """
    Current text of one of a project's files — the uploads directory first, then
    Supabase's ``latex_documents`` (the same two places ``compile_latex`` reads
    project files from) — or None when it cannot be found.
    """
    if not project_id or not str(project_id).strip():
        return None
    pid = str(project_id).strip()
    safe_project = re.sub(r'[^a-zA-Z0-9_-]', '_', pid)
    base = Path(os.getenv("UPLOADS_BASE_DIR", os.path.join(os.path.dirname(__file__), "..", "uploads", "projects"))).resolve()
    project_dir = (base / safe_project).resolve()
    candidate = (project_dir / rel_path).resolve()
    if str(candidate).startswith(str(project_dir)) and candidate.is_file():
        try:
            return candidate.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            pass
    try:
        from project_storage import get_supabase_client
        supabase = get_supabase_client()
        if supabase:
            res = (supabase.table("latex_documents").select("raw_code")
                   .eq("project_id", pid).eq("file_path", rel_path).limit(1).execute())
            raw = (res.data or [{}])[0].get("raw_code")
            if raw and not str(raw).startswith("[Binary Asset:"):
                return raw
    except Exception:
        pass
    return None


def _save_synctex_artifacts(tmpdir: Path, project_id: Optional[str], workdir: Optional[Path] = None,
                            jobname: str = "main") -> None:
    """
    Save the PDF, its synctex, and source .tex files to the persistent build directory.
    ``workdir``/``jobname`` locate the output (the main file's directory and stem); it is
    stored as main.pdf / main.synctex.gz, the names synctex_service reads.
    """
    try:
        from synctex_service import get_project_build_dir, invalidate_project_synctex_cache
        build_dir = get_project_build_dir(project_id)
        invalidate_project_synctex_cache(project_id)
        out_dir = workdir or tmpdir
        pdf_path = out_dir / f"{jobname}.pdf"
        if pdf_path.exists():
            shutil.copy2(pdf_path, build_dir / "main.pdf")
        synctex_gz = out_dir / f"{jobname}.synctex.gz"
        if synctex_gz.exists():
            shutil.copy2(synctex_gz, build_dir / "main.synctex.gz")
        synctex_raw = out_dir / f"{jobname}.synctex"
        if synctex_raw.exists():
            shutil.copy2(synctex_raw, build_dir / "main.synctex")
        for tex_file in tmpdir.rglob("*.tex"):
            rel_t = tex_file.relative_to(tmpdir)
            target_t = build_dir / rel_t
            target_t.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(tex_file, target_t)
    except Exception as synctex_err:
        logger.debug(f"SyncTeX caching note: {synctex_err}")


_RE_TEX_CONTEXT_LINE = re.compile(r"^l\.\d+\b")


def _compile_failure(output: str) -> dict:
    """
    Clean compilation error for the caller to show, or to hand to the AI fixer.

    ``error_log`` keeps TeX's own error lines — ``./main.tex:42: …`` (compiles
    run with -file-line-error) and ``! …`` — each followed by its ``l.N``
    context line, which shows the offending code. It used to keep only lines
    starting with ``!`` or containing ``error:``, which dropped
    ``Undefined control sequence``, ``Missing $ inserted`` and runaway arguments
    and left "Ask AI to Fix" with nothing but "Fatal error occurred". ``errors``
    is the complete list from the full log (``raw_log`` is only its tail).
    """
    clean_err = (output or "").strip() or "LaTeX compilation failed."
    lines = clean_err.split("\n")
    picked: List[str] = []
    for i, line in enumerate(lines):
        s = line.strip()
        low = s.lower()
        if (_TEX_ERROR_RE.match(s) or "fatal error" in low or "emergency stop" in low
                or s.startswith("[TIMEOUT]") or s.startswith("[INFRASTRUCTURE ERROR]")):
            picked.append(s)
            # \errorcontextlines puts several context pairs between an error and its l.N line.
            for nxt in lines[i + 1:i + 60]:
                if _RE_TEX_CONTEXT_LINE.match(nxt.strip()):
                    picked.append(nxt.strip())
                    break
                if _TEX_ERROR_RE.match(nxt.strip()):
                    break
    picked = list(dict.fromkeys(picked))
    summary = "\n".join(picked[:20]) if picked else clean_err[-1500:]
    return {"success": False, "error_log": summary, "raw_log": clean_err[-32000:], "errors": tex_errors(clean_err)}


_RE_LOG_LINE_REFS = (
    re.compile(r"(main\.tex:)(\d+)(:)"),                       # -file-line-error
    re.compile(r"(^|\n)(l\.)(\d+)()"),                         # TeX's "l.<n> <context>"
    re.compile(r"((?:on input line|detected at line) )(\d+)()"),
)
_RE_LOG_LINE_RANGE = re.compile(r"(at lines )(\d+)(--)(\d+)")


def _healed_to_source_lines(healed: str, source: str) -> Dict[int, int]:
    """1-based line in ``healed`` -> the line of ``source`` it came from (or was inserted at)."""
    import difflib
    a, b = healed.splitlines(), source.splitlines()
    mapping: Dict[int, int] = {}
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        for k in range(i1, i2):
            if tag == "equal":
                mapping[k + 1] = j1 + (k - i1) + 1
            elif tag == "replace":
                mapping[k + 1] = min(j1 + (k - i1), j2 - 1) + 1
            else:  # a line the heal added: report it at the source line it follows
                mapping[k + 1] = max(1, min(j1, len(b)))
    return mapping


def _remap_result_lines(result: dict, healed: str, source: str) -> None:
    """Rewrites every TeX line reference in ``result`` from ``healed`` to ``source`` numbering."""
    mapping = _healed_to_source_lines(healed, source)

    def to_src(n: str) -> str:
        return str(mapping.get(int(n), int(n)))

    def remap_text(text: str) -> str:
        if not isinstance(text, str) or not text:
            return text
        text = _RE_LOG_LINE_REFS[0].sub(lambda m: m.group(1) + to_src(m.group(2)) + m.group(3), text)
        text = _RE_LOG_LINE_REFS[1].sub(lambda m: m.group(1) + m.group(2) + to_src(m.group(3)), text)
        text = _RE_LOG_LINE_REFS[2].sub(lambda m: m.group(1) + to_src(m.group(2)), text)
        return _RE_LOG_LINE_RANGE.sub(
            lambda m: m.group(1) + to_src(m.group(2)) + m.group(3) + to_src(m.group(4)), text)

    for key in ("log", "error_log", "raw_log"):
        if key in result:
            result[key] = remap_text(result[key])
    if isinstance(result.get("errors"), list):
        result["errors"] = [remap_text(e) for e in result["errors"]]
    for box in result.get("overfull") or []:
        if isinstance(box, dict) and isinstance(box.get("lines"), list):
            box["lines"] = [mapping.get(n, n) if isinstance(n, int) else n for n in box["lines"]]
    for d in result.get("diagnostics") or []:
        if not isinstance(d, dict) or str(d.get("file") or "main.tex").replace("./", "", 1) != "main.tex":
            continue
        for key in ("line", "reported_line"):
            if isinstance(d.get(key), int):
                d[key] = mapping.get(d[key], d[key])
        if isinstance(d.get("span"), list):
            d["span"] = [mapping.get(n, n) if isinstance(n, int) else n for n in d["span"]]
        if isinstance(d.get("raw"), str):
            d["raw"] = remap_text(d["raw"])


_MAIN_MARKER = ".obmain"  # project_storage.MAIN_MARKER (kept in sync; avoids importing supabase here)
# \include of a file in a parent directory (only rewritten in the compile copy).
_INCLUDE_PARENT_RE = re.compile(r"(?<!%)\\include\s*\{\s*(\.\./[^{}]*)\}")


def _safe_project_rel(rel: Optional[str]) -> Optional[str]:
    """A project-relative POSIX path that stays inside the project, or None."""
    if not rel:
        return None
    r = str(rel).strip().replace("\\", "/")
    while r.startswith("./"):
        r = r[2:]
    if not r or r.startswith("/") or re.match(r"^[A-Za-z]:", r):
        return None
    if any(part in ("", "..") for part in r.split("/")):
        return None
    return r


def _resolve_main_document(project_id: str, tmpdir: Path) -> Optional[str]:
    """
    The project's main document inside the compile copy: the recorded one
    (marker / projects.default_branch), else main.tex, else a detected root document.
    """
    def exists(rel: str) -> bool:
        safe = _safe_project_rel(rel)
        return bool(safe) and (tmpdir / safe).is_file()
    try:
        import project_storage
        rel = project_storage.get_main_document(project_id, exists=exists)
        if rel and exists(rel):
            return _safe_project_rel(rel)
        found = project_storage.detect_main_document_in_dir(tmpdir)
        if found and exists(found):
            return found
    except Exception as e:
        logger.warning(f"main document lookup for {project_id} failed: {e}")
        if (tmpdir / "main.tex").is_file():
            return "main.tex"
    return None


def compile_latex(
    latex_code: str,
    engine: str = "pdfLaTeX",
    images: Optional[List[Dict[str, str]]] = None,
    files: Optional[List[Dict[str, str]]] = None,
    project_id: Optional[str] = None,
    timeout_seconds: Optional[int] = None,  # None: TEX_COMPILE_TIMEOUT (env, default 120s)
    persist_synctex: bool = True,
    allow_recovery: bool = True,
    pre_heal: Optional[bool] = None,
    active_file: Optional[str] = None,
    active_text: Optional[str] = None,
) -> dict:
    """
    Compiles ``latex_code`` (see ``_compile_latex_impl``), optionally healing it first.

    ``pre_heal`` (default: follows ``allow_recovery``) runs the deterministic
    whole-document healer before TeX — unclosed environments, lonely \\item, TikZ
    semicolons, \\bottom -> \\bottomrule, bare & in frame titles, … — the same
    speculative healer the agent runs on every write, discarded internally if it
    raises the structural error count. The PDF importer (allow_recovery=False)
    must see *its exact* code's errors, and the agent's shadow compiler passes
    pre_heal=False because it heals the lines it edited itself.

    A heal can insert lines (e.g. ``\\usetikzlibrary{calc}`` after
    ``\\usepackage{tikz}``), which shifts every line TeX reports below it, so
    the reported lines are translated back to ``latex_code``'s numbering —
    otherwise the error panel, SyncTeX-free jumps and "Ask AI to Fix" all point
    at the wrong line.

    ``active_file`` / ``active_text`` (project compiles from the editor): the open
    buffer is overlaid at its own path in the project copy and the project's MAIN
    DOCUMENT is compiled (see _compile_latex_impl). ``latex_code`` is then only a
    fallback. That compile is never pre-healed — like Overleaf it builds what the
    user wrote; the recovery cascade still applies.
    """
    project_mode = bool(active_file and project_id and str(project_id).strip())
    do_heal = (allow_recovery if pre_heal is None else pre_heal) and not project_mode
    source = latex_code
    if do_heal:
        try:
            from latex_error_fixer import auto_heal_latex_code
            healed, _fixes = auto_heal_latex_code(latex_code)
            if healed:
                latex_code = healed
        except Exception:
            pass

    result = _compile_latex_impl(
        latex_code, engine=engine, images=images, files=files, project_id=project_id,
        timeout_seconds=timeout_seconds, persist_synctex=persist_synctex,
        allow_recovery=allow_recovery, active_file=active_file, active_text=active_text,
    )
    if latex_code != source:
        try:
            _remap_result_lines(result, latex_code, source)
        except Exception as e:
            logger.debug(f"line remap after pre-heal skipped: {e}")
    return result


def _compile_latex_impl(
    latex_code: str,
    engine: str = "pdfLaTeX",
    images: Optional[List[Dict[str, str]]] = None,
    files: Optional[List[Dict[str, str]]] = None,
    project_id: Optional[str] = None,
    timeout_seconds: Optional[int] = None,
    persist_synctex: bool = True,
    allow_recovery: bool = True,
    active_file: Optional[str] = None,
    active_text: Optional[str] = None,
) -> dict:
    """
    TeX compiler pipeline: latexmk from the main file's directory first (what Overleaf
    runs), then direct engine passes and the recovery cascade as fallbacks.

    Two modes:
    * legacy (no ``active_file``): ``latex_code`` IS the document, compiled as main.tex
      at the root of a copy of the project (the agent's shadow compile, old clients).
    * project (``active_file`` + ``project_id``): the whole project is copied, the open
      buffer ``active_text`` is overlaid at ``active_file``, and the project's main
      document (projects.default_branch / marker, see project_storage) is compiled
      from its own directory — never the active file itself.
    """
    start_time = time.time()
    augment_path_for_latex()

    eng_clean = (engine or "pdfLaTeX").strip().lower()

    # Honor `% !TEX program = xelatex|lualatex` when the caller asked for the default engine
    magic_engine = detect_magic_engine(latex_code)
    if magic_engine and eng_clean in _DEFAULT_ENGINES:
        eng_clean = magic_engine
    recovery_engine = eng_clean if eng_clean in ("xelatex", "lualatex") else "pdflatex"

    # Fast ReportLab engine override check
    if eng_clean in ["fast", "reportlab"]:
        try:
            pdf_base64 = generate_fallback_pdf(latex_code)
            elapsed_ms = int((time.time() - start_time) * 1000)
            return {
                "success": True,
                "pdf_base64": pdf_base64,
                "compile_time_ms": elapsed_ms,
                "log": "Rendered via Fast TeX Engine",
            }
        except Exception as fast_err:
            pass

    with tempfile.TemporaryDirectory() as tmpdir_str:
        tmpdir = Path(tmpdir_str)
        last_output = ""
        final_pass = ""  # output of the last complete engine pass: what diagnostics are read from
        project_mode = bool(active_file and project_id and project_id.strip())
        main_rel = "main.tex"
        workdir = tmpdir
        stem = "main"
        main_name = "main.tex"
        pdf_out = tmpdir / "main.pdf"
        notices: List[str] = []
        try:
            has_disk_files = False
            # 1. Copy project disk assets if project_id is provided. In legacy mode the
            # request's code replaces main.tex; in project mode everything is copied and
            # the open buffer is overlaid below.
            if project_id and project_id.strip():
                safe_project = re.sub(r'[^a-zA-Z0-9_-]', '_', project_id.strip())
                uploads_base_dir = Path(os.getenv("UPLOADS_BASE_DIR", os.path.join(os.path.dirname(__file__), "..", "uploads", "projects"))).resolve()
                project_dir = uploads_base_dir / safe_project
                if project_dir.exists():
                    for item in project_dir.rglob("*"):
                        if item.is_file():
                            rel_path = item.relative_to(project_dir)
                            if str(rel_path) == _MAIN_MARKER:
                                continue
                            if str(rel_path) == "main.tex" and not project_mode:
                                continue
                            dest = tmpdir / rel_path
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(item, dest)
                            has_disk_files = True

                # Only query DB if no disk files were present
                if not has_disk_files:
                    try:
                        from project_storage import get_supabase_client
                        supabase = get_supabase_client()
                        if supabase:
                            docs_res = supabase.table("latex_documents").select("file_path, raw_code").eq("project_id", project_id.strip()).execute()
                            if docs_res.data:
                                for doc in docs_res.data:
                                    f_path = doc.get("file_path")
                                    r_code = doc.get("raw_code")
                                    if not f_path or (f_path == "main.tex" and not project_mode):
                                        continue
                                    dest = (tmpdir / f_path).resolve()
                                    if tmpdir.resolve() not in dest.parents:
                                        continue
                                    dest.parent.mkdir(parents=True, exist_ok=True)
                                    if r_code and not r_code.startswith("[Binary Asset:"):
                                        dest.write_text(r_code, encoding="utf-8", errors="ignore")
                    except Exception:
                        pass

            # 2. Project mode: overlay the open buffer at its own path, then resolve the
            # project's main document. That file — not the active one — is compiled.
            if project_mode:
                active_rel = _safe_project_rel(active_file)
                overlay = active_text if active_text is not None else latex_code
                if active_rel is not None and overlay is not None:
                    dest = tmpdir / active_rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text(overlay, encoding="utf-8")
                resolved_main = _resolve_main_document(project_id.strip(), tmpdir)
                if resolved_main is not None:
                    main_rel = resolved_main
                    latex_code = (tmpdir / main_rel).read_text(encoding="utf-8", errors="replace")
                else:
                    # Nothing compilable in the project: compile the buffer itself as before.
                    project_mode = False
                    latex_code = overlay if overlay is not None else latex_code
                if project_mode:
                    magic_engine = detect_magic_engine(latex_code)
                    eng_clean = (engine or "pdfLaTeX").strip().lower()
                    if magic_engine and eng_clean in _DEFAULT_ENGINES:
                        eng_clean = magic_engine
                    recovery_engine = eng_clean if eng_clean in ("xelatex", "lualatex") else "pdflatex"

            if not project_mode:
                # 2b. Legacy: the request's code is the document.
                try:
                    from document_index import ensure_document_environment
                    latex_code = ensure_document_environment(latex_code)
                except Exception:
                    pass

            tex_path = tmpdir / main_rel
            workdir = tex_path.parent
            main_name = tex_path.name
            stem = tex_path.stem
            pdf_out = workdir / f"{stem}.pdf"
            tex_path.parent.mkdir(parents=True, exist_ok=True)
            tex_path.write_text(latex_code, encoding="utf-8")
            # Build outputs that came with the project (an uploaded main.pdf) must never
            # be mistaken for this compile's output.
            for _ext in (".pdf", ".synctex.gz", ".synctex", ".fdb_latexmk", ".fls"):
                try:
                    (workdir / f"{stem}{_ext}").unlink()
                except OSError:
                    pass

            # 3. Write extra payload asset files and images
            if images:
                for img in images:
                    write_file_safely(tmpdir, img.get("filename", ""), img.get("data", ""))

            if files:
                for f in files:
                    write_file_safely(tmpdir, f.get("filename", ""), f.get("data", ""))

            # 4. Smart template asset resolution — copy all matched template assets (.cls, .sty, images, inputs)
            matched_roots = find_matched_template_roots(latex_code)
            for matched_root in matched_roots:
                for tmpl_file in matched_root.rglob("*"):
                    if tmpl_file.is_file():
                        rel_path = tmpl_file.relative_to(matched_root)
                        if str(rel_path) == "main.tex" or rel_path.name in ("metadata.json", "thumbnail.png"):
                            continue
                        dest_file = tmpdir / rel_path
                        if not dest_file.exists():
                            try:
                                dest_file.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(tmpl_file, dest_file)
                            except Exception:
                                pass

            # A main document in a sub-folder that reaches into its parent: \include
            # writes <name>.aux next to the included file, which openout_any=p refuses
            # for ../ paths. \input of the same file reads it without writing, so the
            # compile copy uses \clearpage\input{…}\clearpage (\include's own effect).
            reaches_parent = False
            if workdir != tmpdir:
                for _src in [tex_path] + [p for p in tmpdir.rglob("*.tex") if p != tex_path]:
                    try:
                        _txt = _src.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        continue
                    if "../" in _strip_tex_comments(_txt):
                        reaches_parent = True
                    _new = _INCLUDE_PARENT_RE.sub(lambda m: r"\clearpage\input{" + m.group(1) + r"}\clearpage", _txt)
                    if _new != _txt:
                        _src.write_text(_new, encoding="utf-8")
                        if _src == tex_path:
                            latex_code = _new

            # 5. Font substitution preflight (compile copy only): fontspec families the
            # server does not have are swapped for installed, metric-compatible ones.
            font_subs: List[Tuple[str, str]] = []
            latex_code, _subs = substitute_missing_fonts(latex_code)
            font_subs += _subs
            if _subs:
                tex_path.write_text(latex_code, encoding="utf-8")
            for _src in list(tmpdir.rglob("*")):
                if (_src.is_file() and _src != tex_path and _src.suffix.lower() in (".tex", ".sty", ".cls")
                        and _src.stat().st_size < 4_000_000):
                    try:
                        _txt = _src.read_text(encoding="utf-8")
                    except (OSError, UnicodeDecodeError):
                        continue
                    if not _FONT_SELECTOR_RE.search(_txt):
                        continue
                    _new, _subs = substitute_missing_fonts(_txt)
                    if _subs:
                        _src.write_text(_new, encoding="utf-8")
                        font_subs += _subs
            font_subs = list(dict.fromkeys(font_subs))
            if font_subs:
                notices.append(_font_notice(font_subs))

            # 6. Every source TeX will read (chapters, too) — on disk, not just the request.
            project_text = _project_tex_text(latex_code, tmpdir, main_path=tex_path if project_mode else None)
            # What the main document actually reads. A project can hold other root
            # documents (a standalone review, old drafts) that it never \input's; their
            # text must not decide whether this PDF "looks blank" or needs XeLaTeX.
            reachable_text, reachable_complete = _reachable_tex_text(latex_code, workdir, tmpdir)

            # 7. Referenced images missing everywhere TeX looks get a placeholder.
            ensure_sample_images_exist(latex_code, tmpdir, base_dir=workdir, search_text=project_text)

            # 8. Bibliography: everything below looks at the WHOLE project (an \addbibresource
            # or \cite inside an \input chapter counts), and only the compile copy is touched.
            bib_notes: List[str] = []
            for _stub in _generate_stub_bibs(tmpdir, project_text, base_dir=workdir if project_mode else None):
                bib_notes.append(f"{_stub} was not found; generated a placeholder from the document's citation keys.")
            _compile_copy = _inject_hyperref(latex_code, project_text, tmpdir)
            if _compile_copy != latex_code:
                tex_path.write_text(_compile_copy, encoding="utf-8")

            # Environment: an allowlist (no service secrets reach TeX), openout_any=p, and
            # TEXINPUTS/BIBINPUTS/BSTINPUTS rooted at the project (tex_sandbox).
            from tex_sandbox import project_tex_env
            comp_env = project_tex_env(tmpdir, workdir, extra=dict(_TEX_LOG_ENV),
                                       openin="r" if reaches_parent else "p")

            # Heavy TikZ/pgfplots or very long documents take far longer than a plain
            # article; Overleaf lets them run for minutes. Weight is judged on every
            # source in the compile directory (a thesis main.tex is thirty lines of
            # \input), plus any .tex/.sty/.cls sent in the request.
            base_timeout = int(timeout_seconds) if timeout_seconds else TEX_COMPILE_TIMEOUT
            COMPILE_TIMEOUT = base_timeout
            _extra_sources = [_project_tex_text("", tmpdir, (".tex", ".sty", ".cls"),
                                                main_path=tex_path if project_mode else None)]
            for _f in (files or []):
                _name = str(_f.get("filename", ""))
                if _name.rsplit(".", 1)[-1].lower() in ("tex", "sty", "cls"):
                    try:
                        _extra_sources.append(base64.b64decode(_f.get("data", "")).decode("utf-8", "replace"))
                    except Exception:
                        pass
            if is_heavy_document(latex_code, _extra_sources):
                COMPILE_TIMEOUT = max(base_timeout, TEX_COMPILE_TIMEOUT_HEAVY)

            # Unicode-font documents (fontspec / unicode-math / system fonts /
            # polyglossia) only compile under XeLaTeX or LuaLaTeX. Overleaf picks
            # this from the project's compiler setting; detect it from the source
            # when the caller asked for the default engine and no magic comment
            # already pinned one. A project's preamble may live in an \input file.
            engine_probe = (reachable_text if reachable_complete else project_text) if project_mode else latex_code
            unicode_engine = None
            if eng_clean in _DEFAULT_ENGINES and not magic_engine and needs_unicode_engine(engine_probe):
                unicode_engine = "xelatex"
                recovery_engine = "xelatex"

            # SyncTeX costs an extra output file per run, so it is only asked for when the
            # artifacts will actually be kept (the editor); the PDF importer compiles throwaway
            # pages and never navigates them.
            sx = ["-synctex=1"] if persist_synctex else []

            def _direct(engine_bin: str) -> List[str]:
                return _engine_command(engine_bin, *sx, jobname=stem, entry=main_name)

            def _lmk(engine_bin: str) -> List[str]:
                return _latexmk_command(engine_bin, main_rel, jobname=stem, synctex=persist_synctex)

            # Candidates: latexmk first (run from the project root with -cd, so it works
            # from the main file's directory like Overleaf), then a direct engine run of
            # the same engine (the fallback that also drives the recovery cascade).
            if eng_clean in ["xelatex", "xe"]:
                primary = "xelatex"
            elif eng_clean in ["lualatex", "lua"]:
                primary = "lualatex"
            else:
                primary = unicode_engine or "pdflatex"
            if eng_clean == "tectonic":
                cmd_list = [["tectonic", main_name]]
            else:
                cmd_list = [_lmk(primary), _direct(primary)]
                if eng_clean not in ["pdflatex", "pdf", "latex", "xelatex", "xe", "lualatex", "lua", "latexmk", ""]:
                    # unknown engine name: try the other Unicode engine too, as before
                    cmd_list.append(_direct("lualatex" if primary == "xelatex" else "xelatex"))

            # Blank-output fallback: if the chosen (Xe/Lua) engine renders a text-less PDF
            # because a selected system font is not installed, a dual-engine-safe document
            # (fontspec only behind an \ifPDFTeX guard) can still be rendered by pdfLaTeX.
            # Append it so the blank-output guard below has somewhere to fall through to.
            if not needs_unicode_engine(engine_probe) and not any(c and c[0] == "pdflatex" for c in cmd_list):
                cmd_list.append(_direct("pdflatex"))

            bib_backend = _bibliography_backend(_strip_tex_comments(project_text))
            if bib_backend == "biber" and shutil.which("biber") is None:
                bib_backend = "bibtex"
                bib_notes.append("biblatex detected but biber is not installed; fell back to bibtex.")
            extra_pass_timeout = max(15, COMPILE_TIMEOUT // 2)

            last_output = ""
            blank_seen = False
            skip_direct_of: Optional[str] = None
            for cmd in cmd_list:
                is_latexmk = cmd[0] == "latexmk"
                is_direct = cmd[0] in ["pdflatex", "xelatex", "lualatex"]
                # latexmk already produced (and we rejected) this engine's PDF: a direct
                # run of the same engine would only reproduce it.
                if is_direct and skip_direct_of == cmd[0]:
                    continue
                try:
                    pdf_out.unlink()
                except OSError:
                    pass
                run_cwd = tmpdir if is_latexmk else workdir
                try:
                    # Pass 1 (latexmk: every pass, bibliography and index tools)
                    result = _run_tex(
                        cmd,
                        cwd=run_cwd,
                        timeout=COMPILE_TIMEOUT,
                        env=comp_env
                    )
                    last_output = (result.stdout or "") + "\n" + (result.stderr or "")
                    final_pass = last_output
                    if is_latexmk:
                        _log = workdir / f"{stem}.log"
                        if _log.is_file():
                            try:
                                final_pass = _log.read_text(encoding="utf-8", errors="replace")
                            except OSError:
                                pass
                        if "Latexmk:" not in last_output and "Rule '" not in last_output and not pdf_out.exists():
                            last_output += "\n[LATEXMK] latexmk produced no output; falling back to a direct engine run."

                    pdf_path = pdf_out

                    if pdf_path.exists() and is_direct:
                        # Bibliography: run biber/bibtex, then two more passes so the
                        # citations and the bibliography actually resolve (Overleaf's
                        # latexmk does this automatically).
                        if bib_backend:
                            _run_bibliography(bib_backend, workdir, extra_pass_timeout, comp_env, bib_notes,
                                              jobname=stem)
                            for _ in range(2):
                                try:
                                    rb = _run_tex(
                                        cmd,
                                        cwd=workdir,
                                        timeout=extra_pass_timeout,
                                        env=comp_env,
                                    )
                                    final_pass = (rb.stdout or "") + "\n" + (rb.stderr or "")
                                    last_output += "\n" + final_pass
                                except Exception:
                                    break
                        else:
                            needs_pass2 = (
                                r"\tableofcontents" in project_text
                                or r"\ref{" in project_text
                                or _has_citations(project_text)
                                or r"\label{" in project_text
                                or "Rerun" in last_output
                                or "undefined references" in last_output.lower()
                            )
                            if needs_pass2:
                                result2 = _run_tex(
                                    cmd,
                                    cwd=workdir,
                                    timeout=extra_pass_timeout,
                                    env=comp_env
                                )
                                final_pass = (result2.stdout or "") + "\n" + (result2.stderr or "")
                                last_output += "\n" + final_pass

                    # If PDF was created, persist artifacts and return it.
                    if pdf_path.exists() and pdf_path.stat().st_size > 0 and "Emergency stop" not in last_output:
                        engine_of_cmd = primary if is_latexmk else cmd[0]
                        # A PDF that compiled but has no text layer (a system font selected by
                        # the document is not installed, so the engine drew no glyphs) is a blank
                        # result, not a success. Treat it as a failed attempt and try the next
                        # engine candidate (a dual-engine-safe document falls back to pdfLaTeX).
                        if _looks_blank(pdf_path, reachable_text):
                            blank_seen = True
                            if is_latexmk:
                                skip_direct_of = engine_of_cmd
                            msg = (f"'{cmd[0]}' produced a PDF with no visible text — a selected font may "
                                   f"not be installed on the server.")
                            last_output += f"\n[BLANK OUTPUT] {msg} Trying the next engine."
                            logger.warning(f"⚠️ [COMPILER] {msg}")
                            continue
                        # Beamer syntax (\begin{frame}, \column) in a non-beamer class leaves
                        # pdflatex producing a one-page error-content PDF while the real slides
                        # went undefined. Treat this as a failed pass so the cascade can promote
                        # the documentclass to beamer and re-render.
                        if (_looks_like_beamer_body(project_text)
                                and "Environment columns undefined" in last_output
                                and _promote_to_beamer(project_text)[1] is not None):
                            logger.warning("⚠️ [COMPILER] beamer syntax in non-beamer class; "
                                           "treating pass as failed to allow class promotion recovery")
                            if is_latexmk:
                                skip_direct_of = engine_of_cmd
                            continue
                        if persist_synctex:
                            _save_synctex_artifacts(tmpdir, project_id, workdir, stem)
                        pdf_bytes = pdf_path.read_bytes()
                        pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")
                        elapsed_ms = int((time.time() - start_time) * 1000)
                        compiled = {
                            "success": True,
                            "pdf_base64": pdf_base64,
                            "compile_time_ms": elapsed_ms,
                            "log": last_output[-1000:] if last_output else f"Compiled via {cmd[0]}",
                            "errors": tex_errors(final_pass if is_latexmk else last_output),
                            # Overfull boxes are warnings, so they never reach the
                            # truncated log above; keep them for layout checks.
                            "overfull": _overfull_boxes(final_pass if is_latexmk else last_output),
                            "main_file": main_rel,
                            "engine_used": ("latexmk " + engine_of_cmd) if is_latexmk else cmd[0],
                        }
                        # A PDF produced despite errors is the common case for the
                        # errors that matter here (a misplaced & never stops TeX),
                        # and the truncated log above holds none of their context.
                        _attach_diagnostics(compiled, final_pass, workdir, main_name, tmpdir)
                        if bib_notes:
                            # diagnostics, never errors: a bibliography problem must not fail the compile
                            compiled.setdefault("diagnostics", []).extend(
                                _bib_note_diagnostic(n) for n in dict.fromkeys(bib_notes))
                        if notices:
                            compiled["notices"] = list(notices)
                            compiled.setdefault("diagnostics", []).extend(_font_diagnostic(n) for n in notices)
                            compiled["log"] = "\n".join(notices) + "\n\n" + compiled["log"]
                        return compiled
                except subprocess.TimeoutExpired:
                    last_output += f"\n[TIMEOUT] {cmd[0]} exceeded {COMPILE_TIMEOUT}s"
                    # The whole process group was killed. Another engine run of the same
                    # document would only burn the same budget again.
                    break
                except FileNotFoundError as fnf:
                    last_output += f"\n[INFRASTRUCTURE ERROR] Executable '{cmd[0]}' not found: {fnf}"
                    continue
                except Exception as exc:
                    last_output += f"\n[INFRASTRUCTURE ERROR] Command '{cmd[0]}' failed: {exc}"
                    continue

            if not allow_recovery:
                # A caller that only wants to know whether THIS code compiles (the PDF importer,
                # which then hands the errors to the model) must not pay for the cascade below:
                # every patch is another engine run, up to seven of them, and a PDF obtained by
                # silently disabling a package is a result such a caller rejects anyway.
                failed = _compile_failure(last_output)
                _mark_blank_failure(failed, blank_seen)
                _attach_diagnostics(failed, final_pass or last_output, workdir, main_name, tmpdir)
                return failed

            # Every recovery run must still report the TeX errors it saw: a PDF obtained
            # by disabling a package says nothing about the rest of the document, and
            # the agent's compile gate reads ``errors`` to decide whether an edit broke it.
            # A patch that inserts a line (lmodern) shifts TeX's line numbers, so they
            # are mapped back to the code this function was given.
            def _recovery_success(log_text: str, output_text: str, patched: str) -> dict:
                if persist_synctex:
                    _save_synctex_artifacts(tmpdir, project_id, workdir, stem)
                res = {
                    "success": True,
                    "pdf_base64": base64.b64encode((pdf_out).read_bytes()).decode("utf-8"),
                    "compile_time_ms": int((time.time() - start_time) * 1000),
                    "log": log_text,
                    "errors": tex_errors(output_text),
                    "overfull": _overfull_boxes(output_text),
                }
                res["main_file"] = main_rel
                _attach_diagnostics(res, output_text, workdir, main_name, tmpdir)
                if notices:
                    res["notices"] = list(notices)
                    res.setdefault("diagnostics", []).extend(_font_diagnostic(n) for n in notices)
                if patched != latex_code:
                    try:
                        _remap_result_lines(res, patched, latex_code)
                    except Exception:
                        pass
                return res

            # 1. Missing LaTeX package iterative auto-recovery patch
            patched_code = latex_code
            all_disabled_pkgs = []
            cur_output = last_output
            for pass_num in range(4):
                # `! LaTeX Error: …` in a classic log, `./main.tex:3: LaTeX Error: …` with
                # -file-line-error (every direct engine run) — the latter never matched before.
                missing_pkgs = re.findall(
                    r"(?:!|\S+\.tex:\d+:) LaTeX Error: File [`\x27]([^\x27`]+)\.sty[`\x27] not found", cur_output)
                if not missing_pkgs:
                    break

                # Critical packages gate: NEVER silently disable critical packages (beamer, tikz, amsmath, etc.)
                # Disabling them causes TeX to dump raw parameters/macros as visual "jargon" into the PDF.
                critical_missing = [p for p in missing_pkgs if _is_critical_package(p)]
                if critical_missing:
                    logger.warning(
                        f"❌ [COMPILER RECOVERY] Missing critical package(s): {', '.join(critical_missing)}. "
                        "Refusing to auto-disable critical package to avoid generating corrupted jargon PDF."
                    )
                    break

                for pkg in set(missing_pkgs):
                    if pkg not in all_disabled_pkgs:
                        patched_code = re.sub(
                            r'\\usepackage(?:\[[^\]]*\])?\{' + re.escape(pkg) + r'\}',
                            f'% [AUTO-DISABLED: {pkg}.sty not installed on server]',
                            patched_code
                        )
                        all_disabled_pkgs.append(pkg)

                tex_path.write_text(patched_code, encoding="utf-8")
                try:
                    result = _run_tex(
                        _direct(recovery_engine),
                        cwd=workdir,
                        timeout=15,
                        env=comp_env
                    )
                    cur_output = (result.stdout or "") + "\n" + (result.stderr or "")
                    pdf_path = pdf_out
                    if pdf_path.exists() and pdf_path.stat().st_size > 0:
                        errs = tex_errors(cur_output)
                        has_fatal_or_jargon = any(
                            "emergency stop" in e.lower()
                            or "fatal error" in e.lower()
                            or "undefined control sequence" in e.lower()
                            for e in errs
                        ) or "Emergency stop" in cur_output

                        if not has_fatal_or_jargon:
                            pkg_notice = (
                                f"Missing auxiliary LaTeX package(s) on server: {', '.join(all_disabled_pkgs)}. "
                                f"Install on server: 'pacman -S texlive-latexextra' (Arch) / 'apt-get install texlive-latex-extra' (Ubuntu) / 'tlmgr install <pkg>'."
                            )
                            logger.info(f"✅ [COMPILER RECOVERY] Auto-recovered by disabling non-critical package(s): {', '.join(all_disabled_pkgs)}")
                            return _recovery_success(
                                f"Compiled via package auto-recovery ({', '.join(all_disabled_pkgs)} disabled)\n\n[PACKAGE NOTICE]\n{pkg_notice}",
                                cur_output, patched_code,
                            )
                        else:
                            logger.warning(
                                f"❌ [COMPILER RECOVERY] Disabling {all_disabled_pkgs} caused fatal or undefined control sequences. "
                                "Aborting recovery to prevent serving corrupted PDF."
                            )
                            break
                except Exception:
                    break

            # 2. Font metric error auto-recovery patch
            font_error_keywords = ["not loadable", "Metric (TFM) file not found", "ecrm1000", "cm-super"]
            if any(kw.lower() in last_output.lower() for kw in font_error_keywords):
                patched_code = latex_code
                if "lmodern" not in patched_code:
                    if r"\usepackage[T1]{fontenc}" in patched_code:
                        patched_code = patched_code.replace(r"\usepackage[T1]{fontenc}", r"\usepackage[T1]{fontenc}" + "\n" + r"\usepackage{lmodern}")
                    elif r"\documentclass" in patched_code:
                        # A literal \usepackage{lmodern} appears in a re.sub replacement string;
                        # re on Python 3.12+ rejects "\u" as a bad escape in a replacement, so
                        # a lambda is used to keep the backslash literal.
                        patched_code = re.sub(
                            r'(\\documentclass(?:\[.*?\])?\{.*?\})',
                            lambda m: m.group(1) + "\n" + r"\usepackage{lmodern}",
                            patched_code,
                            count=1,
                        )

                if patched_code != latex_code:
                    tex_path.write_text(patched_code, encoding="utf-8")
                    try:
                        result = _run_tex(_direct(recovery_engine), cwd=workdir, timeout=15, env=comp_env)
                        pdf_path = pdf_out
                        if pdf_path.exists() and pdf_path.stat().st_size > 0 and "Emergency stop" not in (result.stdout or ""):
                            return _recovery_success(
                                "Compiled via font auto-recovery (lmodern patch)",
                                (result.stdout or "") + "\n" + (result.stderr or ""), patched_code,
                            )
                    except Exception:
                        pass

            # 3. Invalid beamercolorbox bg key auto-recovery patch
            if "Package keyval Error: bg undefined" in last_output or "bg undefined" in last_output:
                patched_code = re.sub(
                    r"\[([^\]]*?),?\s*bg=[^,\]]+([^\]]*)\]",
                    lambda m: f"[{m.group(1)}{m.group(2)}]".replace("[,", "[").replace(",,", ",").replace("[,]", "[]"),
                    latex_code
                )
                if patched_code != latex_code:
                    tex_path.write_text(patched_code, encoding="utf-8")
                    try:
                        result = _run_tex(
                            _direct(recovery_engine),
                            cwd=workdir,
                            timeout=15,
                            env=comp_env
                        )
                        pdf_path = pdf_out
                        if pdf_path.exists() and pdf_path.stat().st_size > 0 and "Emergency stop" not in (result.stdout or ""):
                            return _recovery_success(
                                "Compiled via beamercolorbox bg auto-recovery",
                                (result.stdout or "") + "\n" + (result.stderr or ""), patched_code,
                            )
                    except Exception:
                        pass

            # 4. Modern LaTeX3 titlesec \MakeUppercase / Bad math delimiter auto-recovery patch
            titlesec_error_keywords = [
                "__text_expand_loop:w",
                "Bad math environment delimiter",
                "titlesec Error",
                "has an extra }"
            ]
            if any(kw in last_output for kw in titlesec_error_keywords) or (r"\titleformat" in latex_code and r"\MakeUppercase" in latex_code):
                patched_code = latex_code
                patched_lines = []
                # `\\[6pt]` is a row break inside a table. Rewriting it to
                # `\par\vspace{6pt}` there leaves the rows unterminated: they merge,
                # and the caller is shown "Extra alignment tab" errors for a document
                # it never wrote. The rewrite is for title pages and headings only.
                try:
                    from latex_specials import ALIGNMENT_ENVS as _alignment_envs
                except Exception:
                    _alignment_envs = frozenset({"tabular", "tabularx", "longtable", "array", "align"})
                open_alignments = 0
                for line in patched_code.split("\n"):
                    begins = [e for e in re.findall(r"\\begin\s*\{([A-Za-z*]+)\}", line) if e in _alignment_envs]
                    ends = [e for e in re.findall(r"\\end\s*\{([A-Za-z*]+)\}", line) if e in _alignment_envs]
                    in_alignment = open_alignments > 0 or bool(begins)
                    open_alignments = max(0, open_alignments + len(begins) - len(ends))
                    if "titleformat" in line and "\\MakeUppercase" in line:
                        line = line.replace("\\MakeUppercase", "")
                    elif "\\MakeUppercase" in line and any(k in line for k in ["centering", "normalfont", "bfseries"]):
                        line = line.replace("\\MakeUppercase", "")
                    if (not in_alignment and "\\\\" in line
                            and any(unit in line for unit in ["cm]", "in]", "mm]", "pt]", "em]"])):
                        line = re.sub(r'\\\\\s*\[(\d+(?:\.\d+)?(?:cm|in|mm|pt|em|ex))\]', r'\\par\\vspace{\1}', line)
                    patched_lines.append(line)
                patched_code = "\n".join(patched_lines)

                if patched_code != latex_code:
                    tex_path.write_text(patched_code, encoding="utf-8")
                    try:
                        result = _run_tex(
                            _direct(recovery_engine),
                            cwd=workdir,
                            timeout=15,
                            env=comp_env,
                        )
                        pdf_path = pdf_out
                        if pdf_path.exists() and pdf_path.stat().st_size > 0 and "Emergency stop" not in (result.stdout or ""):
                            return _recovery_success(
                                "Compiled via titlesec/spacing auto-recovery",
                                (result.stdout or "") + "\n" + (result.stderr or ""), patched_code,
                            )
                    except Exception:
                        pass

            # 5. Missing system font / blank-output recovery.
            # Two signatures of a missing system font selected via fontspec:
            #  (a) an engine produced a well-paginated but text-less PDF (blank_seen).
            #  (b) an engine hard-errored on the font load ("fontspec Error", "not
            #      loadable", "I can't find file") and no PDF was produced.
            # In either case: strip fontspec setup and retry under pdflatex so the
            # body renders in Computer Modern.
            font_missing_signals = (
                "fontspec Error",
                "not loadable",
                "cannot be\n(fontspec)",
                "cannot be found",
            )
            has_font_markers = any(m in latex_code for m in _UNICODE_ENGINE_MARKERS)
            font_hard_error = has_font_markers and any(s in last_output for s in font_missing_signals)
            if blank_seen or font_hard_error:
                patched_code = _strip_fontspec_setup(latex_code)
                if patched_code != latex_code:
                    tex_path.write_text(patched_code, encoding="utf-8")
                    try:
                        result = _run_tex(_direct("pdflatex"), cwd=workdir, timeout=15, env=comp_env)
                        pdf_path = pdf_out
                        out = (result.stdout or "") + "\n" + (result.stderr or "")
                        if (pdf_path.exists() and pdf_path.stat().st_size > 0
                                and "Emergency stop" not in out
                                and not _looks_blank(pdf_path, patched_code)):
                            notice = (
                                "System fonts selected via fontspec are not installed on the server. "
                                "The document was rendered in Computer Modern as a fallback — install the "
                                "fonts on the server or guard \\setmainfont behind \\ifPDFTeX in the source."
                            )
                            logger.info("✅ [COMPILER RECOVERY] fontspec-stripped pdflatex pass succeeded")
                            return _recovery_success(
                                f"Compiled via fontspec strip (fonts missing on server)\n\n[FONT NOTICE]\n{notice}",
                                out, patched_code,
                            )
                    except Exception:
                        pass

            # 6. Beamer-syntax-in-non-beamer-class recovery.
            # When the body uses \begin{frame}, \column{} or \usetheme but the
            # documentclass is not beamer, every \end{frame} and \column goes
            # undefined and the log is a wall of "Environment X undefined" lines.
            # Promote the class to beamer and retry.
            if (_looks_like_beamer_body(latex_code)
                    and ("undefined" in last_output.lower() or "Package keyval Error" in last_output)):
                patched_code, prior_class = _promote_to_beamer(latex_code)
                if prior_class is not None and patched_code != latex_code:
                    tex_path.write_text(patched_code, encoding="utf-8")
                    try:
                        result = _run_tex(_direct("pdflatex"), cwd=workdir, timeout=15, env=comp_env)
                        pdf_path = pdf_out
                        out = (result.stdout or "") + "\n" + (result.stderr or "")
                        if pdf_path.exists() and pdf_path.stat().st_size > 0 and "Emergency stop" not in out:
                            notice = (
                                f"The source used beamer commands (\\begin{{frame}}, \\column, …) but the "
                                f"document class was '{prior_class}'. Promoted to \\documentclass{{beamer}} "
                                f"so the deck would compile — change the first line of the source to make this permanent."
                            )
                            logger.info("✅ [COMPILER RECOVERY] documentclass promoted %r → beamer", prior_class)
                            return _recovery_success(
                                f"Compiled via beamer class promotion ({prior_class} → beamer)\n\n[CLASS NOTICE]\n{notice}",
                                out, patched_code,
                            )
                    except Exception:
                        pass

        except Exception:
            pass

        # No fallback PDFs — return clean compilation error directly so user can see it and ask AI to fix it
        failed = _compile_failure(last_output)
        _mark_blank_failure(failed, blank_seen)
        _attach_diagnostics(failed, final_pass or last_output, workdir, main_name, tmpdir)
        return failed

