"""
tex_sandbox.py — how TeX processes are run: a scrubbed environment, kpathsea's
file-access knobs, project-rooted search paths, and a process group per run so
a timeout kills the engine *and* everything latexmk started.

Ported (local runner only) from the bench-baseline worktree. Every engine call in
``compiler.py`` goes through ``compiler._run_tex`` -> ``run_tex_process`` here.

Environment
    ``compile_latex`` used to hand TeX ``os.environ.copy()``. A TeX run can read
    its own environment (``\\openin`` on ``/proc/self/environ``) and the compile
    endpoint returns the log, so every credential the backend held (Supabase
    service key, model API keys, auth secret, DB URL) was one four-line document
    away from any user. Only the variables TeX needs are passed now.

kpathsea access control (measured on TeX Live 2026, not assumed)
    ``openout_any=p``  effective: no writes outside the job dir, to a parent, or
                       to a dotfile.
    ``openin_any=p``   has NO effect since TeX Live 2026 (texmf.cnf: "as of 2026,
                       openin_any no longer has any effect"); \\openin of
                       /proc/self/environ still succeeds. It is set for older TeX
                       Live images that honour it, but nothing relies on it — the
                       env allowlist is what keeps secrets out of reach.
    shell escape       left at TeX Live's default *restricted* mode (what Overleaf
                       runs): ``\\input{|"cat ..."}`` and ``\\write18{curl}`` are
                       refused, while allow-listed helpers (e.g. ``latexminted``,
                       ``bibtex``, ``kpsewhich``) still work.
"""

from __future__ import annotations

import os
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional, Sequence

#: Host variables a TeX run may see. Everything else is dropped.
_ENV_ALLOWLIST = (
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TERM",
    "TMPDIR",
    "SOURCE_DATE_EPOCH",
    # kpathsea / TeX tree layout
    "TEXMFHOME",
    "TEXMFVAR",
    "TEXMFCONFIG",
    "TEXMFSYSVAR",
    "TEXMFSYSCONFIG",
    "TEXMFLOCAL",
    "TEXMFCNF",
    "TEXINPUTS",
    "BIBINPUTS",
    "BSTINPUTS",
    "TEXFONTS",
    "TEXFORMATS",
    "TEXPSHEADERS",
    "FONTCONFIG_PATH",
    "FONTCONFIG_FILE",
    "OSFONTDIR",
    # latexmk's system rc (a server-side file, never a project one)
    "LATEXMKRCSYS",
)

#: Set last, so neither the host nor a caller can loosen them.
_TEX_SECURITY_ENV = {
    "openin_any": "p",
    "openout_any": "p",
}

#: Captured stdout/stderr is truncated here; TeX's real log is the .log file.
MAX_CAPTURED_OUTPUT_BYTES = int(os.getenv("TEX_MAX_CAPTURED_OUTPUT_BYTES", str(8 * 1024 * 1024)))


def search_path(dirs: Iterable[Path], *, recursive_root: Optional[Path] = None) -> str:
    """
    A kpathsea path list: ``.`` first, then ``dirs``, then ``recursive_root//``,
    then an empty element so TeX Live's own tree is searched last.
    """
    parts = ["."]
    for d in dirs:
        s = str(d)
        if s not in parts:
            parts.append(s)
    if recursive_root is not None:
        parts.append(f"{recursive_root}//")
    return ":".join(parts) + ":"


def build_tex_env(extra: Optional[Dict[str, str]] = None, *, openin: str = "p") -> Dict[str, str]:
    """
    The environment a TeX process gets: allowlisted host variables, then
    ``extra`` (TEXINPUTS etc. computed per job), then the kpathsea security
    settings, which ``extra`` cannot override.
    """
    env: Dict[str, str] = {}
    for key in _ENV_ALLOWLIST:
        value = os.environ.get(key)
        if value is not None:
            env[key] = value
    env.setdefault("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin")
    env.setdefault("HOME", os.environ.get("HOME") or "/tmp")
    for key, value in (extra or {}).items():
        env[str(key)] = str(value)
    env.update(_TEX_SECURITY_ENV)
    if openin in ("r", "p"):
        # "r" (no dotfiles, parents allowed) is only ever chosen by the compiler for a
        # main document in a sub-folder that reads ../ files; writes stay paranoid.
        env["openin_any"] = openin
    return env


def project_tex_env(project_root: Path, main_dir: Optional[Path] = None,
                    extra: Optional[Dict[str, str]] = None, *, openin: str = "p") -> Dict[str, str]:
    """
    ``build_tex_env`` with TEXINPUTS / BIBINPUTS / BSTINPUTS rooted at the job's
    project directory: the main file's directory, the project root, then the
    whole project tree recursively, then TeX Live's defaults. A host TEXINPUTS is
    deliberately NOT inherited — it would let the server's own directories shadow
    the project's files.
    """
    root = Path(project_root)
    dirs = [d for d in (main_dir, root) if d is not None]
    tex_dirs = list(dirs) + [root / "images"]
    env_extra = {
        "TEXINPUTS": search_path(tex_dirs, recursive_root=root),
        "BIBINPUTS": search_path(dirs, recursive_root=root),
        "BSTINPUTS": search_path(dirs, recursive_root=root),
    }
    env_extra.update(extra or {})
    return build_tex_env(env_extra, openin=openin)


def _truncate(text: str) -> str:
    if len(text) <= MAX_CAPTURED_OUTPUT_BYTES:
        return text
    return text[:MAX_CAPTURED_OUTPUT_BYTES] + "\n[OUTPUT TRUNCATED by tex_sandbox]"


@dataclass
class TexResult:
    """The subset of ``CompletedProcess`` the compiler reads."""
    args: Sequence[str]
    returncode: int
    stdout: str
    stderr: str


def kill_process_group(popen: "subprocess.Popen") -> None:
    """SIGTERM then SIGKILL the whole process group (latexmk + pdflatex + biber …)."""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(popen.pid, sig)
        except (ProcessLookupError, PermissionError, OSError):
            break
        try:
            popen.wait(timeout=3)
            return
        except subprocess.TimeoutExpired:
            continue


def run_tex_process(cmd: Sequence[str], *, cwd, timeout: float, env: Dict[str, str],
                    capture_output: bool = True) -> TexResult:
    """
    Runs one TeX-related command in its own process group. On timeout the whole
    group is killed (killing only latexmk would leave pdflatex/biber spinning)
    and ``subprocess.TimeoutExpired`` is raised. Output is decoded with
    ``errors='replace'`` — TeX logs routinely contain non-UTF-8 bytes.
    """
    use_setsid = os.name == "posix"
    popen = subprocess.Popen(
        list(cmd),
        cwd=str(cwd),
        stdout=subprocess.PIPE if capture_output else None,
        stderr=subprocess.PIPE if capture_output else None,
        stdin=subprocess.DEVNULL,
        env=env,
        # Its own session/process group, so a timeout can kill the whole tree. No
        # preexec_fn: it is unsafe in a threaded server (compiles run in a pool).
        start_new_session=use_setsid,
        close_fds=True,
    )
    try:
        out, err = popen.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        if use_setsid:
            kill_process_group(popen)
        else:  # pragma: no cover - non-POSIX
            popen.kill()
        try:
            out, err = popen.communicate(timeout=5)
        except Exception:
            out, err = b"", b""
        raise subprocess.TimeoutExpired(list(cmd), timeout, output=out or b"", stderr=err or b"")
    return TexResult(
        args=list(cmd),
        returncode=popen.returncode,
        stdout=_truncate((out or b"").decode("utf-8", errors="replace")),
        stderr=_truncate((err or b"").decode("utf-8", errors="replace")),
    )
