"""
llm.py — Page-level LLM calls through the agentic edit feature's own client.

Every call goes through providers.router.provider_router.chat with DEFAULT_MODEL,
exactly like the OpenCode agent loop: same GeminiProvider (GEMINI_WEB2API_BASE_URL,
rotating GEMINI_WEB2API_API_KEY_*), same model, same OpenRouter fallback. This module
only adds what a batch of page calls needs: per-call timeout (the cancel token aborts
the stream), retries with backoff, and a process-wide concurrency cap.
"""

import asyncio
import logging
import random
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from cancellation import CancellationToken
from providers.multimodal import image_part, text_part
from providers.router import DEFAULT_MODEL, provider_router
from providers.web2api_keys import get_web2api_base_url, load_web2api_keys

logger = logging.getLogger("pdf2latex.llm")

_slots_lock = threading.Lock()
_slots: Optional[threading.BoundedSemaphore] = None
_slots_size = 0
_pool: Optional[ThreadPoolExecutor] = None


class LLMCallFailed(RuntimeError):
    pass


def model_name() -> str:
    return DEFAULT_MODEL


def llm_available() -> bool:
    if get_web2api_base_url() and load_web2api_keys():
        return True
    return bool(getattr(provider_router.openrouter, "candidates", None))


def _slots_for(n: int) -> threading.BoundedSemaphore:
    global _slots, _slots_size
    with _slots_lock:
        if _slots is None or _slots_size != n:
            _slots, _slots_size = threading.BoundedSemaphore(n), n
        return _slots


def _pool_for(n: int) -> ThreadPoolExecutor:
    """
    A pool of our own for the blocking provider call.

    asyncio.to_thread runs on the event loop's default executor, which holds only
    min(32, cpu_count + 4) threads — 8 on a 4-core host — and is shared with every compile
    (compile_queue hands work to the same default executor) and with page rendering and
    comparison. A handful of page calls, each parked on a socket for up to PDF2LATEX_PAGE_TIMEOUT
    seconds, filled it: compiles that had already taken a queue slot then sat waiting for a
    thread, and the editor's own compiles stalled behind the import. The semaphore above admits
    at most n calls at a time, so n workers never queue.
    """
    global _pool
    with _slots_lock:
        if _pool is None or _pool._max_workers < n:  # noqa: SLF001 — sizing only grows
            if _pool is not None:
                _pool.shutdown(wait=False)
            _pool = ThreadPoolExecutor(max_workers=n, thread_name_prefix="pdf2latex-llm")
        return _pool


def _chat(messages: List[Dict[str, Any]], max_tokens: int, token: CancellationToken) -> str:
    token.check_cancelled()
    resp = provider_router.chat(messages=messages, model=DEFAULT_MODEL, temperature=0.0,
                                max_tokens=max_tokens, cancel_token=token)
    return str(resp.get("content") or "")


async def complete(system: str, user: str, image_png: Optional[bytes] = None, *, timeout: float,
                   retries: int, concurrency: int, max_tokens: int = 16384, label: str = "") -> str:
    """
    One LLM completion with retries. The page image is sent on every attempt except a final
    text-only one, so a gateway that chokes on images still gets a chance to answer.
    """
    slots = _slots_for(concurrency)
    attempts = retries + 1
    last_error = "no attempt made"
    for attempt in range(attempts):
        with_image = image_png is not None and (attempts == 1 or attempt < attempts - 1)
        user_content: Any = [text_part(user), image_part(image_png)] if with_image else user
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user_content}]
        token = CancellationToken(f"pdf2latex:{label}:{attempt}")
        while not slots.acquire(blocking=False):  # polling keeps task cancellation safe
            await asyncio.sleep(0.2)
        try:
            fut = asyncio.get_running_loop().run_in_executor(
                _pool_for(concurrency), _chat, messages, max_tokens, token)
            text = await asyncio.wait_for(fut, timeout)
            if text.strip():
                return text
            last_error = "empty response"
        except asyncio.TimeoutError:
            token.cancel("page timeout")
            last_error = f"timed out after {timeout:.0f}s"
        except asyncio.CancelledError:
            token.cancel("conversion cancelled")
            raise
        except Exception as e:  # noqa: BLE001 — provider errors vary by gateway
            last_error = str(e)[:300]
        finally:
            slots.release()
        logger.warning(f"LLM call {label} attempt {attempt + 1}/{attempts} failed: {last_error}")
        if attempt < attempts - 1:
            await asyncio.sleep(min(20.0, 2.0 ** attempt + random.uniform(0, 1)))
    if last_error == "empty response":
        return ""  # the caller decides whether an empty page is worth another try
    raise LLMCallFailed(last_error)
