"""
llm.py — Page-level LLM calls through the agentic edit feature's own client.

Every call goes through providers.router.provider_router.chat with DEFAULT_MODEL,
i.e. the strict Web2API gateway chain (WEB2API_GATEWAYS, in order, cycled up to
LLM_CHAIN_CYCLES times). allow_fallback=True is the contract here: a page call may
walk and cycle the whole chain, so one dead gateway never fails a page. No other
provider (OpenRouter, Groq, NVIDIA) is ever consulted.

Because the router already retries internally, `complete()` does not retry on top of
it while the chain is active (that would nest retries 3 x attempts); the page-level
PDF2LATEX_PAGE_RETRIES only applies to the legacy single-endpoint setup.
"""

import asyncio
import logging
import os
import random
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from cancellation import CancellationToken
from providers.multimodal import image_part, text_part
from providers.router import DEFAULT_MODEL, provider_router
from providers.web2api_keys import gateways_configured

logger = logging.getLogger("pdf2latex.llm")

_slots_lock = threading.Lock()
_slots: Optional[threading.BoundedSemaphore] = None
_slots_size = 0
_pool: Optional[ThreadPoolExecutor] = None


class LLMCallFailed(RuntimeError):
    pass


@dataclass(frozen=True)
class LLMReply:
    """A completion plus what the gateway actually did with the images (see complete_ex)."""
    text: str
    images_sent: int        # images that went out on the attempt that answered (0 on a text-only attempt)
    images_dropped: bool    # the provider answered from a text-only copy of an image call
    model: str


def model_name() -> str:
    return DEFAULT_MODEL


def llm_available() -> bool:
    """True when any gateway of the chain (WEB2API_GATEWAYS, or the legacy GEMINI*/GEMINI2*) is configured."""
    return gateways_configured()


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
    resp = provider_router.chat(
        messages=messages,
        model=DEFAULT_MODEL,
        temperature=0.0,
        max_tokens=max_tokens,
        cancel_token=token,
        allow_fallback=True,
    )
    return str(resp.get("content") or "")


def _chat_ex(messages: List[Dict[str, Any]], max_tokens: int, token: CancellationToken) -> Dict[str, Any]:
    token.check_cancelled()
    return provider_router.chat(
        messages=messages,
        model=DEFAULT_MODEL,
        temperature=0.0,
        max_tokens=max_tokens,
        cancel_token=token,
        allow_fallback=True,
    )


async def complete(system: str, user: str, image_png: Optional[bytes] = None, *, timeout: float,
                   retries: int, concurrency: int, max_tokens: int = 16384, label: str = "") -> str:
    """
    One LLM completion with retries. The page image is sent on every attempt except a final
    text-only one, so a gateway that chokes on images still gets a chance to answer.
    """
    slots = _slots_for(concurrency)
    if provider_router.chain_active():
        # The router retries across gateways and cycles itself; don't nest 3 x attempts, and
        # don't let the per-page timeout cut the chain off after the first few dead gateways
        # (45s idle each). PDF2LATEX_CHAIN_TIMEOUT bounds the whole walk instead.
        retries = 0
        try:
            timeout = max(timeout, float(os.getenv("PDF2LATEX_CHAIN_TIMEOUT", "1800")))
        except ValueError:
            timeout = max(timeout, 1800.0)
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



async def complete_ex(system: str, user: str, images: Sequence[bytes] = (), *, timeout: float,
                      retries: int, concurrency: int, max_tokens: int = 16384, label: str = "") -> LLMReply:
    """
    `complete` for any number of images (sent in order, after the text) that also reports what the
    gateway did with them: `images_dropped` is True when the provider silently answered from a
    text-only copy because the endpoint rejects image input, so the caller can tell a reply that
    saw the page from one that did not. Chain, timeout, concurrency and cancellation behave as in
    `complete`; an empty final answer comes back as an empty `text`.
    """
    slots = _slots_for(concurrency)
    if provider_router.chain_active():
        retries = 0  # the router retries across gateways itself (see complete)
        try:
            timeout = max(timeout, float(os.getenv("PDF2LATEX_CHAIN_TIMEOUT", "1800")))
        except ValueError:
            timeout = max(timeout, 1800.0)
    attempts = retries + 1
    last_error = "no attempt made"
    for attempt in range(attempts):
        with_images = bool(images) and (attempts == 1 or attempt < attempts - 1)
        user_content: Any = [text_part(user), *(image_part(img) for img in images)] if with_images else user
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user_content}]
        token = CancellationToken(f"pdf2latex:{label}:{attempt}")
        while not slots.acquire(blocking=False):  # polling keeps task cancellation safe
            await asyncio.sleep(0.2)
        try:
            fut = asyncio.get_running_loop().run_in_executor(
                _pool_for(concurrency), _chat_ex, messages, max_tokens, token)
            resp = await asyncio.wait_for(fut, timeout)
            text = str(resp.get("content") or "")
            if text.strip():
                return LLMReply(text=text, images_sent=len(images) if with_images else 0,
                                images_dropped=bool(with_images and resp.get("images_dropped")),
                                model=str(resp.get("model_used") or DEFAULT_MODEL))
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
        return LLMReply(text="", images_sent=0, images_dropped=False, model=DEFAULT_MODEL)
    raise LLMCallFailed(last_error)
