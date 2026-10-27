"""
tex_health.py — is the TeX toolchain in THIS process's environment able to build a PDF?

A tiny document is built with every engine through the same sandboxed environment the real
compiles use, and each result reports its wall time. The first xelatex / lualatex run in a
fresh container builds font caches (minutes with a full TeX Live plus system fonts); that
cost is paid once by ``warm_up`` at startup instead of by the first user's compile, which
used to hit the compile timeout and show as "compilation failed".
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

from tex_sandbox import build_tex_env, run_tex_process

logger = logging.getLogger("tex_health")

_DOC = {
    "pdflatex": r"\documentclass{article}\begin{document}Hello $x^2$\end{document}",
    "xelatex": r"\documentclass{article}\usepackage{fontspec}\begin{document}Hello\end{document}",
    "lualatex": r"\documentclass{article}\usepackage{fontspec}\begin{document}Hello\end{document}",
}
_WARM_TIMEOUT_S = int(os.getenv("TEX_WARMUP_TIMEOUT", "600"))
_CACHE_TTL_S = 60.0
_cache: Dict[str, Any] = {"at": 0.0, "value": None}


def _version(binary: str, env: Dict[str, str]) -> str:
    try:
        out = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=20, env=env)
        return (out.stdout or out.stderr).splitlines()[0] if (out.stdout or out.stderr) else ""
    except Exception as exc:  # noqa: BLE001
        return f"error: {exc!r}"


def _probe(engine: str, timeout: float) -> Dict[str, Any]:
    env = build_tex_env()
    path = shutil.which(engine, path=env.get("PATH"))
    info: Dict[str, Any] = {"engine": engine, "path": path}
    if not path:
        info.update(ok=False, error="not found on PATH")
        return info
    info["version"] = _version(engine, env)
    with tempfile.TemporaryDirectory(prefix="ob-health-") as tmp:
        (Path(tmp) / "main.tex").write_text(_DOC[engine], encoding="utf-8")
        t0 = time.perf_counter()
        try:
            res = run_tex_process([engine, "-interaction=nonstopmode", "-halt-on-error", "main.tex"],
                                  cwd=tmp, timeout=timeout, env=env)
            info["ok"] = (Path(tmp) / "main.pdf").is_file()
            if not info["ok"]:
                info["error"] = (res.stdout + res.stderr)[-600:]
        except subprocess.TimeoutExpired:
            info.update(ok=False, error=f"timed out after {timeout}s")
        info["seconds"] = round(time.perf_counter() - t0, 1)
    return info


def check(timeout: float = 120.0, refresh: bool = False) -> Dict[str, Any]:
    now = time.time()
    if not refresh and _cache["value"] and now - _cache["at"] < _CACHE_TTL_S:
        return _cache["value"]
    engines: List[Dict[str, Any]] = [_probe(e, timeout) for e in ("pdflatex", "xelatex", "lualatex")]
    env = build_tex_env()
    value = {
        "ok": all(e.get("ok") for e in engines),
        "latexmk": shutil.which("latexmk", path=env.get("PATH")),
        "home": env.get("HOME"),
        "engines": engines,
    }
    _cache.update(at=now, value=value)
    return value


def warm_up() -> None:
    """Runs once per process at startup (in a thread); logs what it found."""
    try:
        result = check(timeout=_WARM_TIMEOUT_S, refresh=True)
        for e in result["engines"]:
            level = logging.INFO if e.get("ok") else logging.ERROR
            logger.log(level, "[TEX_WARMUP] %s ok=%s %ss %s", e["engine"], e.get("ok"),
                       e.get("seconds"), e.get("error", "") or e.get("version", ""))
    except Exception:  # noqa: BLE001 - never block startup
        logger.exception("[TEX_WARMUP] failed")
