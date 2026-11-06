"""
server.py — HTTP front of the compile sandbox (the `tex-runner` sidecar).

  POST /compile  {"workdir": "<path relative to TEX_RUNNER_ROOT>", "main": "main.tex",
                  "engine": "xelatex", "timeout_s": 120}
                 header X-Runner-Token: <TEX_RUNNER_TOKEN>
                 -> the `run_compile` dict (200, also for rejected paths: ok=false + detail)
  GET  /health   -> {ok, engines: {xelatex, pdflatex, lualatex, latexmk}, root_exists} (no auth)

No file upload: the job files are on the volume both containers mount. The request body is
capped, the token is compared in constant time, an empty TEX_RUNNER_TOKEN refuses everything
(503) unless TEX_RUNNER_ALLOW_NO_TOKEN=1, and at most TEX_RUNNER_CONCURRENCY compiles run at
once; a request that waits longer than TEX_RUNNER_QUEUE_WAIT_S for a slot gets 429.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import os
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .compile import ENGINES, build_env, engine_paths, run_compile

MAX_BODY_BYTES = 8 * 1024


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name) or default)
    except ValueError:
        return default


def runner_root() -> Path:
    return Path((os.getenv("TEX_RUNNER_ROOT") or "/work").rstrip("/") or "/work")


def _auth_error(request: Request):
    """None when the request may proceed, else the response refusing it."""
    expected = os.getenv("TEX_RUNNER_TOKEN") or ""
    if not expected:
        if os.getenv("TEX_RUNNER_ALLOW_NO_TOKEN") == "1":
            return None
        return JSONResponse({"ok": False, "detail": "TEX_RUNNER_TOKEN is not configured"}, status_code=503)
    given = request.headers.get("x-runner-token") or ""
    if not hmac.compare_digest(given.encode(), expected.encode()):
        return JSONResponse({"ok": False, "detail": "bad or missing X-Runner-Token"}, status_code=401)
    return None


class _TooLarge(Exception):
    pass


async def _read_body(request: Request) -> bytes:
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            if int(declared) > MAX_BODY_BYTES:
                raise ValueError
        except ValueError:
            raise _TooLarge()
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            raise _TooLarge()
        chunks.append(chunk)
    return b"".join(chunks)


def create_app() -> FastAPI:
    """The runner app. Concurrency and wait cap are read once, here; token and root per request."""
    app = FastAPI(title="tex-runner", docs_url=None, redoc_url=None, openapi_url=None)
    concurrency = max(1, _env_int("TEX_RUNNER_CONCURRENCY", 2))
    wait_cap = max(1, _env_int("TEX_RUNNER_QUEUE_WAIT_S", 300))
    max_timeout = max(1, _env_int("TEX_RUNNER_MAX_TIMEOUT", 600))
    default_timeout = max(1, _env_int("TEX_RUNNER_TIMEOUT", 120))
    state: Dict[str, Any] = {"sem": None}

    def _sem() -> asyncio.Semaphore:
        if state["sem"] is None:
            state["sem"] = asyncio.Semaphore(concurrency)
        return state["sem"]

    @app.get("/health")
    async def health() -> Dict[str, Any]:
        tools = await asyncio.to_thread(engine_paths, build_env())
        engines = {name: bool(path) for name, path in tools.items()}
        root_exists = runner_root().is_dir()
        return {"ok": bool(root_exists and engines.get("xelatex") and engines.get("latexmk")),
                "engines": engines, "root_exists": root_exists}

    @app.post("/compile")
    async def compile_endpoint(request: Request):
        refused = _auth_error(request)
        if refused is not None:
            return refused
        try:
            payload = json.loads(await _read_body(request) or b"null")
        except _TooLarge:
            return JSONResponse({"ok": False, "detail": "request body too large"}, status_code=413)
        except (ValueError, UnicodeDecodeError):
            return JSONResponse({"ok": False, "detail": "body is not JSON"}, status_code=400)
        if not isinstance(payload, dict) or not isinstance(payload.get("workdir"), str):
            return JSONResponse({"ok": False, "detail": "workdir (string) is required"}, status_code=400)
        workdir = payload["workdir"]
        main = payload.get("main") or "main.tex"
        engine = payload.get("engine") or "xelatex"
        if not isinstance(main, str) or not isinstance(engine, str) or engine not in ENGINES:
            return JSONResponse({"ok": False, "detail": "bad main or engine"}, status_code=400)
        try:
            timeout_s = min(float(payload.get("timeout_s") or default_timeout), float(max_timeout))
        except (TypeError, ValueError):
            return JSONResponse({"ok": False, "detail": "timeout_s must be a number"}, status_code=400)
        if not workdir or workdir.startswith("/") or "\x00" in workdir:
            return JSONResponse({"ok": False, "detail": "workdir must be relative to the runner root"},
                                status_code=400)

        root = runner_root()
        sem = _sem()
        try:
            await asyncio.wait_for(sem.acquire(), timeout=wait_cap)
        except asyncio.TimeoutError:
            return JSONResponse({"ok": False, "detail": "runner busy, retry later"}, status_code=429)
        try:
            # run_compile confines the joined path to the root (realpath), so "../x" is refused there.
            return await asyncio.to_thread(run_compile, root / workdir, main, engine, timeout_s,
                                           root=root)
        finally:
            sem.release()

    return app
