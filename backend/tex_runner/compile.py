"""
compile.py — one confined LaTeX compile of a directory (stdlib only).

`run_compile(workdir, main, engine, timeout_s, root=..., limits=...)` builds `<workdir>/<stem>.pdf`
with latexmk (or the engine directly, re-run until labels settle, when latexmk is missing) and
returns a plain dict. It never raises for compile problems; a rejected request comes back as
`ok=False` with `detail` saying why.

Confinement, each layer measured on TeX Live 2026 (tests/test_rebuild_sandbox.py):
  paths        `workdir` must resolve (symlinks followed) strictly inside `root`; `main` is a plain
               relative `.tex` path inside `workdir` (no `..`, no dotfiles, no leading `-`).
  shell escape fully off: `-no-shell-escape` plus `shell_escape=f` in the environment, so neither
               `\\write18` nor `\\input|"cmd"` runs anything (not even TeX Live's restricted list).
  file writes  `openout_any=p`: no `\\openout` to an absolute path, a parent directory or a dotfile.
               (`openin_any` is ignored since TeX Live 2026; reads are kept harmless by the env
               allowlist and, in the sidecar, by the container only mounting the job volume.)
  environment  built from an allowlist; HOME / TMPDIR / TEXMFVAR / TEXMFCONFIG / XDG_CACHE_HOME
               point at a private writable directory (TEX_RUNNER_TMP), shared by compiles so the
               fontconfig / luaotfload caches are built once per process, not per compile.
  rlimits      CPU seconds, address space, file size, open files and process count, applied in
               the child by a tiny `python -I -S` trampoline that then exec()s latexmk (no
               preexec_fn: it is unsafe in the threaded server that calls this).
  wall clock   the child gets its own session; on timeout the whole process group (latexmk,
               the engine, xdvipdfmx, ...) is SIGTERMed then SIGKILLed, and stragglers are
               reaped after a normal exit too.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger("tex_runner")

ENGINES = ("xelatex", "pdflatex", "lualatex")
LOG_TAIL_CHARS = 32000
MAX_ERRORS = 50

_LATEXMK_FLAG = {"pdflatex": "-pdf", "xelatex": "-pdfxe", "lualatex": "-pdflua"}

#: Host variables a TeX run may see. Unlike `tex_sandbox`, HOME / TMPDIR / TEXMFVAR / TEXMFHOME
#: are not inherited (they point at the private directory) and neither are TEXINPUTS & co (a host
#: search path would let server directories shadow the job's files).
_ENV_ALLOWLIST = (
    "PATH",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TERM",
    "SOURCE_DATE_EPOCH",
    "TEXMFCNF",
    "TEXMFSYSVAR",
    "TEXMFSYSCONFIG",
    "TEXMFLOCAL",
    "TEXFONTS",
    "TEXFORMATS",
    "TEXPSHEADERS",
    "FONTCONFIG_PATH",
    "FONTCONFIG_FILE",
    "OSFONTDIR",
)

#: Applied last, so neither the host nor a caller can loosen them. kpathsea reads texmf.cnf
#: variables from the environment first. The *_line values stop the log wrapping at 79 columns,
#: which would otherwise cut error messages in half.
_SECURITY_ENV = {
    "openout_any": "p",
    "openin_any": "p",
    "shell_escape": "f",
    "shell_escape_commands": "",
    "max_print_line": "10000",
    "error_line": "254",
    "half_error_line": "238",
}

# A file-line-error error line ("./main.tex:12: Undefined control sequence.") or a classic one.
_FILE_LINE_RE = re.compile(r"^(?P<file>[^\s:()]+\.[A-Za-z]+):(?P<line>\d+): (?P<msg>.+)$")
_BANG_RE = re.compile(r"^! (?P<msg>.+)$")
_LNUM_RE = re.compile(r"^l\.(\d+)")
_PAGES_RE = re.compile(r"Output written on \S+\.(?:pdf|xdv) \((\d+) pages?")
_RERUN_RE = re.compile(r"Rerun to get|Label\(s\) may have changed|There were undefined references")
_MAIN_RE = re.compile(r"^(?:[A-Za-z0-9_][A-Za-z0-9_.\-]*/)*[A-Za-z0-9_][A-Za-z0-9_.\-]*\.tex$")

# Applies the rlimits handed in argv[1:6], then exec()s the real command (argv[7:]). Python ignores
# SIGXFSZ / SIGPIPE at start-up and an ignored signal survives exec(), so they are reset first:
# otherwise a file-size bomb only gets EFBIG, which TeX silently drops, and keeps running.
_TRAMPOLINE = (
    "import os,resource as r,signal as g,sys\n"
    "g.signal(g.SIGXFSZ,g.SIG_DFL)\n"
    "g.signal(g.SIGPIPE,g.SIG_DFL)\n"
    "a=sys.argv\n"
    "c,m,f,p,n=(int(x) for x in a[1:6])\n"
    "def s(k,soft,hard):\n"
    "    _,h=r.getrlimit(k)\n"
    "    if h!=r.RLIM_INFINITY:\n"
    "        soft,hard=min(soft,h),min(hard,h)\n"
    "    r.setrlimit(k,(soft,hard))\n"
    "if c>0: s(r.RLIMIT_CPU,c,c+5)\n"
    "if m>0: s(r.RLIMIT_AS,m<<20,m<<20)\n"
    "if f>0: s(r.RLIMIT_FSIZE,f<<20,f<<20)\n"
    "if p>0: s(r.RLIMIT_NPROC,p,p)\n"
    "if n>0: s(r.RLIMIT_NOFILE,n,n)\n"
    "s(r.RLIMIT_CORE,0,0)\n"
    "os.execvp(a[7],a[7:])\n"
)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name) or default)
    except ValueError:
        return default


def default_limits() -> Dict[str, int]:
    """
    rlimits per compile, from the same env names `pdf2latex.rebuild.settings` reads. `nproc` is
    headroom: RLIMIT_NPROC counts every task of the uid, so the limit is set to the uid's current
    task count plus this (a fixed number would fail every fork on a busy desktop, or be useless).
    """
    return {
        "cpu_s": max(1, _env_int("TEX_RUNNER_CPU_SECONDS", 150)),
        "mem_mb": max(64, _env_int("TEX_RUNNER_MEMORY_MB", 2048)),
        "fsize_mb": max(1, _env_int("TEX_RUNNER_FSIZE_MB", 128)),
        "nproc": max(8, _env_int("TEX_RUNNER_NPROC", 64)),
        "nofile": max(64, _env_int("TEX_RUNNER_NOFILE", 256)),
    }


# ---------------------------------------------------------------------------
# Private writable directories and the child environment
# ---------------------------------------------------------------------------

_PRIVATE: Dict[str, Path] = {}


def private_base() -> Path:
    """
    The writable directory TeX gets for HOME, caches and temp files: TEX_RUNNER_TMP, else
    `<tmp>/tex-runner-<uid>`. A pre-existing default that is a symlink or owned by someone else is
    not trusted (another user could have planted it); a fresh mkdtemp is used instead.
    """
    configured = (os.getenv("TEX_RUNNER_TMP") or "").strip()
    key = configured or "<default>"
    cached = _PRIVATE.get(key)
    if cached is not None and cached.is_dir():
        return cached
    uid = os.getuid() if hasattr(os, "getuid") else 0
    base = Path(configured) if configured else Path(tempfile.gettempdir()) / f"tex-runner-{uid}"
    try:
        base.mkdir(mode=0o700, parents=True, exist_ok=True)
        st = os.lstat(base)
        if not configured and (os.path.islink(base) or st.st_uid != uid):
            raise PermissionError(f"untrusted {base}")
    except OSError:
        base = Path(tempfile.mkdtemp(prefix="tex-runner-"))
    for sub in ("home", "texmf-var", "texmf-config", "cache", "tmp"):
        (base / sub).mkdir(mode=0o700, exist_ok=True)
    _PRIVATE[key] = base
    return base


def build_env(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """The child environment: allowlisted host variables, private dirs, `extra`, security knobs."""
    base = private_base()
    env: Dict[str, str] = {}
    for key in _ENV_ALLOWLIST:
        value = os.environ.get(key)
        if value is not None:
            env[key] = value
    env.setdefault("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin")
    env.setdefault("LANG", "C.UTF-8")
    home = str(base / "home")
    env.update({
        "HOME": home,
        "TEXMFHOME": str(base / "home" / "texmf"),
        "TEXMFVAR": str(base / "texmf-var"),
        "TEXMFCONFIG": str(base / "texmf-config"),
        "XDG_CACHE_HOME": str(base / "cache"),
        "XDG_CONFIG_HOME": str(base / "home" / ".config"),
        "TMPDIR": str(base / "tmp"),
    })
    for key, value in (extra or {}).items():
        env[str(key)] = str(value)
    env.pop("TEXMFOUTPUT", None)  # would whitelist an absolute output directory under openout_any=p
    env.update(_SECURITY_ENV)
    return env


def engine_paths(env: Optional[Dict[str, str]] = None) -> Dict[str, Optional[str]]:
    """Where each engine (and latexmk) is on the sandbox PATH, or None."""
    path = (env or build_env()).get("PATH")
    return {name: shutil.which(name, path=path) for name in ENGINES + ("latexmk",)}


# ---------------------------------------------------------------------------
# Process control
# ---------------------------------------------------------------------------

def _uid_tasks() -> int:
    """Tasks (threads included) the current real uid owns — what RLIMIT_NPROC counts."""
    uid = os.getuid()
    total = 0
    try:
        entries = os.listdir("/proc")
    except OSError:
        return 0
    for pid in entries:
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/status", "rb") as fh:
                ruid = threads = None
                for line in fh:
                    if line.startswith(b"Uid:"):
                        ruid = int(line.split()[1])
                    elif line.startswith(b"Threads:"):
                        threads = int(line.split()[1])
                        break
            if ruid == uid:
                total += threads or 1
        except (OSError, ValueError, IndexError):
            continue
    return total


def _limit_argv(limits: Dict[str, int]) -> List[str]:
    nproc = int(limits.get("nproc") or 0)
    if nproc > 0 and hasattr(os, "getuid") and os.getuid() != 0:
        nproc += _uid_tasks()
    else:
        nproc = 0  # root ignores RLIMIT_NPROC; the container's pids_limit bounds it instead
    return [str(int(limits.get(k) or 0)) for k in ("cpu_s", "mem_mb", "fsize_mb")] + [
        str(nproc), str(int(limits.get("nofile") or 0))]


def _kill_group(pgid: int, popen: Optional[subprocess.Popen] = None) -> None:
    """SIGTERM then SIGKILL every process of the group (latexmk + engine + helpers)."""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
        except (ProcessLookupError, PermissionError, OSError):
            return
        if popen is not None:
            try:
                popen.wait(timeout=2)
            except subprocess.TimeoutExpired:
                continue
        if sig == signal.SIGTERM:
            time.sleep(0.2)


def spawn(cmd: Sequence[str], *, cwd: Path, env: Dict[str, str], timeout_s: float,
          limits: Dict[str, int]) -> Tuple[Optional[int], bool, str]:
    """
    Runs `cmd` under the rlimits in a session of its own. Returns (returncode, timed_out,
    output tail). Output goes to a file in the private tmp dir, not a pipe, so a chatty run can
    neither deadlock nor balloon this process's memory.
    """
    argv = [sys.executable, "-I", "-S", "-c", _TRAMPOLINE, *_limit_argv(limits), "--", *cmd]
    timed_out = False
    with tempfile.TemporaryFile(dir=str(private_base() / "tmp")) as out:
        popen = subprocess.Popen(argv, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL,
                                 stdout=out, stderr=subprocess.STDOUT, start_new_session=True,
                                 close_fds=True)
        try:
            popen.wait(timeout=max(0.1, timeout_s))
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_group(popen.pid, popen)
            try:
                popen.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        # Anything still in the group (a helper the engine left behind) goes too.
        _kill_group(popen.pid)
        out.seek(0, os.SEEK_END)
        size = out.tell()
        out.seek(max(0, size - LOG_TAIL_CHARS * 2))
        text = out.read().decode("utf-8", errors="replace")
    return popen.returncode, timed_out, text[-LOG_TAIL_CHARS:]


# ---------------------------------------------------------------------------
# Log parsing
# ---------------------------------------------------------------------------

def _clean_file(name: str) -> str:
    return name[2:] if name.startswith("./") else name


def parse_errors(log: str, main: str = "main.tex") -> List[str]:
    """
    Error lines of a -file-line-error log as "file:line: message". The few errors TeX still
    prints in the classic "! message" form take the line of their "l.N" context (attributed to
    `main`), or stay "! message" when there is none rather than get an invented line.
    """
    errors: List[str] = []
    lines = (log or "").splitlines()
    for i, raw in enumerate(lines):
        line = raw.rstrip()
        m = _FILE_LINE_RE.match(line)
        if m:
            errors.append(f"{_clean_file(m.group('file'))}:{m.group('line')}: {m.group('msg').strip()}")
            continue
        m = _BANG_RE.match(line)
        if m:
            msg = m.group("msg").strip()
            lnum = None
            for follow in lines[i + 1:i + 12]:
                lm = _LNUM_RE.match(follow)
                if lm:
                    lnum = lm.group(1)
                    break
                if _BANG_RE.match(follow) or _FILE_LINE_RE.match(follow):
                    break
            errors.append(f"{main}:{lnum}: {msg}" if lnum else f"! {msg}")
    return list(dict.fromkeys(errors))[:MAX_ERRORS]


def _read_tail(path: Path, max_bytes: int) -> str:
    try:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - max_bytes))
            return fh.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def _count_pages(log: str, pdf: Path) -> int:
    found = _PAGES_RE.findall(log or "")
    if found:
        return int(found[-1])
    try:
        data = pdf.read_bytes()
    except OSError:
        return 0
    m = re.findall(rb"/Type\s*/Pages\b[^>]*?/Count\s+(\d+)", data)
    if m:
        return max(int(x) for x in m)
    return len(re.findall(rb"/Type\s*/Page\b(?!s)", data))


# ---------------------------------------------------------------------------
# The compile
# ---------------------------------------------------------------------------

def _result(engine: str, t0: float, **kw: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {"ok": False, "pdf": None, "log": "", "errors": [], "timed_out": False,
                           "pages": 0, "seconds": round(time.monotonic() - t0, 3), "engine": engine,
                           "detail": "", "returncode": None}
    out.update(kw)
    return out


def _confine(workdir: Any, main: Any, root: Any) -> Tuple[Optional[Path], str]:
    """Resolved workdir, or (None, why) when the request escapes `root` or names a bad main."""
    try:
        root_r = Path(os.path.realpath(os.fspath(root)))
        wd_r = Path(os.path.realpath(os.fspath(workdir)))
    except (TypeError, ValueError, OSError) as exc:
        return None, f"bad path: {exc}"
    if not root_r.is_dir():
        return None, f"sandbox root does not exist: {root_r}"
    if wd_r == root_r or root_r not in wd_r.parents:
        return None, "workdir resolves outside the sandbox root"
    if not wd_r.is_dir():
        return None, "workdir is not a directory"
    if not isinstance(main, str) or not _MAIN_RE.match(main) or "\x00" in main:
        return None, "main must be a plain relative .tex path inside workdir"
    main_r = Path(os.path.realpath(wd_r / main))
    if wd_r not in main_r.parents:
        return None, "main resolves outside workdir"
    if not main_r.is_file():
        return None, f"main file not found: {main}"
    return wd_r, ""


def run_compile(workdir: Any, main: str = "main.tex", engine: str = "xelatex",
                timeout_s: float = 120, *, root: Any,
                limits: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    """
    Compiles `<workdir>/<main>` to `<workdir>/<stem>.pdf` (jobname = stem of `main`), leaving
    `<stem>.aux` / `<stem>.log` for the caller. Keys: ok, pdf (relative to workdir, or None),
    log (tail), errors ("file:line: message"), timed_out, pages, seconds, engine, detail,
    returncode. `ok` means a PDF exists, the run finished in time and the log has no TeX error.
    """
    t0 = time.monotonic()
    engine = (engine or "xelatex").strip().lower() if isinstance(engine, str) else ""
    if engine not in ENGINES:
        return _result(str(engine), t0, detail=f"unsupported engine (use one of {', '.join(ENGINES)})")
    wd, why = _confine(workdir, main, root)
    if wd is None:
        return _result(engine, t0, detail=why)
    lim = default_limits()
    lim.update({k: int(v) for k, v in (limits or {}).items() if v is not None})
    try:
        timeout = max(1.0, float(timeout_s or 120))
    except (TypeError, ValueError):
        timeout = 120.0

    stem = Path(main).stem
    pdf, log_path = wd / f"{stem}.pdf", wd / f"{stem}.log"
    for stale in (pdf, wd / f"{stem}.xdv"):
        try:
            stale.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            return _result(engine, t0, detail=f"cannot clear stale output: {exc}")

    env = build_env()
    tools = engine_paths(env)
    if not tools.get(engine):
        return _result(engine, t0, detail=f"{engine} not found on PATH")

    deadline = t0 + timeout
    timed_out = False
    returncode: Optional[int] = None
    output = ""
    if tools.get("latexmk"):
        cmd = ["latexmk", "-norc", "-f", "-interaction=nonstopmode", "-file-line-error",
               "-latexoption=-no-shell-escape", _LATEXMK_FLAG[engine], f"-jobname={stem}", main]
        returncode, timed_out, output = spawn(cmd, cwd=wd, env=env, timeout_s=timeout, limits=lim)
    else:
        cmd = [engine, "-no-shell-escape", "-interaction=nonstopmode", "-file-line-error",
               f"-jobname={stem}", main]
        for _ in range(3):
            returncode, timed_out, output = spawn(cmd, cwd=wd, env=env,
                                                  timeout_s=deadline - time.monotonic(), limits=lim)
            if timed_out or not pdf.is_file() or not _RERUN_RE.search(_read_tail(log_path, 1 << 20)):
                break
            if time.monotonic() >= deadline:
                break

    log = _read_tail(log_path, 4 << 20)
    errors = parse_errors(log, main)
    has_pdf = pdf.is_file() and pdf.stat().st_size > 0
    detail = ""
    if timed_out:
        detail = f"timed out after {timeout:g}s"
    elif not has_pdf:
        detail = f"no PDF produced (exit code {returncode})"
    tail = log[-LOG_TAIL_CHARS:] if log else output[-LOG_TAIL_CHARS:]
    if not log and output:
        errors = errors or parse_errors(output, main)
    return _result(
        engine, t0,
        ok=bool(has_pdf and not timed_out and not errors),
        pdf=pdf.name if has_pdf else None,
        log=tail,
        errors=errors,
        timed_out=timed_out,
        pages=_count_pages(log, pdf) if has_pdf else 0,
        detail=detail,
        returncode=returncode,
    )
