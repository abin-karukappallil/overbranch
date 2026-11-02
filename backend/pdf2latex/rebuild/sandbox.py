"""
sandbox.py — compile a rebuild work directory in the TeX sandbox.

`compile_dir(workdir)` is the only way the rebuild pipeline runs TeX. Two modes, one code path
(`tex_runner.run_compile`):
  local   (TEX_SANDBOX_MODE=local, the default) — `run_compile` in a worker thread, confined to the
          job directory (`settings.local_root`), at most MAX_CONCURRENT_COMPILES at once per loop.
  runner  (TEX_SANDBOX_MODE=runner) — POST to the `tex-runner` sidecar at TEX_RUNNER_URL. Both
          containers mount the job directory, so only the path relative to it travels; the PDF is
          read back from `workdir` on the shared volume.

Never raises for compile or transport problems: the result's `ok` / `detail` carry them.
`compile_queue` is not used for the local gate: its 45 s slot timeout and queue-depth cap are
tuned for interactive editor compiles and would fail pipeline pages under load instead of
letting them wait.
"""

from __future__ import annotations

import asyncio
import logging
import os
import weakref
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from tex_runner import run_compile
from tex_runner.compile import build_env, engine_paths

from .model import SandboxResult
from .settings import get_rebuild_settings

logger = logging.getLogger("pdf2latex.rebuild.sandbox")

_CONNECT_RETRIES = 2
_BACKOFF_S = (0.5, 1.5)
# Slack on top of the compile timeout for the HTTP call: the runner may queue the request
# (TEX_RUNNER_QUEUE_WAIT_S) and the compile itself overruns its timeout by the kill grace.
_HTTP_SLACK_S = 330.0

_gates: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore]" = weakref.WeakKeyDictionary()


def _gate() -> asyncio.Semaphore:
    """One semaphore per event loop (an asyncio.Semaphore is bound to the loop that first uses it)."""
    loop = asyncio.get_running_loop()
    sem = _gates.get(loop)
    if sem is None:
        try:
            size = int(os.getenv("MAX_CONCURRENT_COMPILES") or 4)
        except ValueError:
            size = 4
        sem = _gates[loop] = asyncio.Semaphore(max(1, size))
    return sem


def _from_dict(data: Dict[str, Any], workdir: Path, engine: str) -> SandboxResult:
    pdf_name = data.get("pdf")
    pdf_path = (workdir / pdf_name) if isinstance(pdf_name, str) and pdf_name else None
    errors = data.get("errors")
    return SandboxResult(
        ok=bool(data.get("ok")),
        pdf_path=pdf_path,
        log=str(data.get("log") or ""),
        errors=[str(e) for e in errors] if isinstance(errors, list) else [],
        timed_out=bool(data.get("timed_out")),
        engine=str(data.get("engine") or engine),
        pages=int(data.get("pages") or 0),
        seconds=float(data.get("seconds") or 0.0),
        detail=str(data.get("detail") or ""),
    )


async def _compile_local(workdir: Path, main: str, engine: str, timeout_s: int) -> SandboxResult:
    s = get_rebuild_settings()
    limits = {"cpu_s": s.compile_cpu_s, "mem_mb": s.compile_mem_mb, "fsize_mb": s.compile_fsize_mb}
    async with _gate():
        data = await asyncio.to_thread(run_compile, workdir, main, engine, timeout_s,
                                       root=s.local_root, limits=limits)
    return _from_dict(data, workdir, engine)


def _runner_relpath(workdir: Path, local_root: Path) -> Optional[str]:
    try:
        rel = Path(os.path.realpath(workdir)).relative_to(Path(os.path.realpath(local_root)))
    except ValueError:
        return None
    return rel.as_posix() if rel.parts else None


async def _compile_runner(workdir: Path, main: str, engine: str, timeout_s: int) -> SandboxResult:
    s = get_rebuild_settings()
    if not s.runner_url:
        return SandboxResult(ok=False, engine=engine, detail="TEX_SANDBOX_MODE=runner but TEX_RUNNER_URL is not set")
    rel = _runner_relpath(workdir, s.local_root)
    if rel is None:
        return SandboxResult(ok=False, engine=engine, detail="workdir is not inside the job directory")
    body = {"workdir": rel, "main": main, "engine": engine, "timeout_s": timeout_s}
    headers = {"X-Runner-Token": s.runner_token}
    timeout = httpx.Timeout(timeout_s + _HTTP_SLACK_S, connect=5.0)
    resp = None
    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(_CONNECT_RETRIES + 1):
            try:
                resp = await client.post(f"{s.runner_url}/compile", json=body, headers=headers)
                break
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                if attempt >= _CONNECT_RETRIES:
                    return SandboxResult(ok=False, engine=engine, detail=f"tex-runner unreachable: {exc!r}")
                await asyncio.sleep(_BACKOFF_S[attempt])
            except httpx.HTTPError as exc:
                return SandboxResult(ok=False, engine=engine, detail=f"tex-runner request failed: {exc!r}")
    if resp.status_code != 200:
        return SandboxResult(ok=False, engine=engine,
                             detail=f"tex-runner HTTP {resp.status_code}: {resp.text[:300]}")
    try:
        data = resp.json()
        if not isinstance(data, dict):
            raise ValueError("not an object")
        result = _from_dict(data, workdir, engine)
    except (ValueError, TypeError) as exc:
        return SandboxResult(ok=False, engine=engine, detail=f"tex-runner returned malformed JSON: {exc}")
    if result.pdf_path is not None and not result.pdf_path.is_file():
        result.ok = False
        result.detail = result.detail or "runner reported a PDF that is not on the shared volume"
        result.pdf_path = None
    return result


async def compile_dir(workdir: Path, main: str = "main.tex", engine: str = "xelatex",
                      timeout_s: Optional[int] = None) -> SandboxResult:
    """Compile `<workdir>/<main>` to `<workdir>/<stem>.pdf` in the configured sandbox."""
    s = get_rebuild_settings()
    timeout = int(timeout_s or s.compile_timeout_s)
    workdir = Path(workdir)
    try:
        if s.sandbox_mode == "runner":
            return await _compile_runner(workdir, main, engine, timeout)
        return await _compile_local(workdir, main, engine, timeout)
    except Exception as exc:  # noqa: BLE001 - a sandbox fault is a failed compile, not a crash
        logger.exception("sandbox compile failed")
        return SandboxResult(ok=False, engine=engine, detail=f"sandbox error: {exc!r}")


async def runner_health() -> Dict[str, Any]:
    """Reachability / toolchain of the sandbox, for /api/health/tex."""
    s = get_rebuild_settings()
    if s.sandbox_mode != "runner":
        tools = await asyncio.to_thread(engine_paths, build_env())
        engines = {name: bool(path) for name, path in tools.items()}
        root_exists = s.local_root.is_dir()
        return {"mode": "local", "reachable": True, "engines": engines, "root_exists": root_exists,
                "ok": bool(root_exists and engines.get("xelatex") and engines.get("latexmk"))}
    if not s.runner_url:
        return {"mode": "runner", "reachable": False, "ok": False, "detail": "TEX_RUNNER_URL is not set"}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=3.0)) as client:
            resp = await client.get(f"{s.runner_url}/health")
        data = resp.json() if resp.status_code == 200 else {}
        if not isinstance(data, dict):
            data = {}
        return {"mode": "runner", "reachable": resp.status_code == 200, "ok": bool(data.get("ok")),
                "engines": data.get("engines") or {}, "root_exists": bool(data.get("root_exists")),
                **({} if resp.status_code == 200 else {"detail": f"HTTP {resp.status_code}"})}
    except (httpx.HTTPError, ValueError) as exc:
        return {"mode": "runner", "reachable": False, "ok": False, "detail": f"{exc!r}"}
