"""
probe.py — Does the Web2API gateway chain answer text, and does it really look at images?

The gateways have been seen rejecting image input, and GeminiProvider then silently answers from a
text-only copy of the call (reported as `images_dropped`). The rebuild pipeline is only worth running
when the model sees the pages, so a job asks `probe_gateway()` first: a one-word text call and a
vision call that must read a random code off a generated PNG. The result is cached per process for
`probe_ttl_s`; a refresh first clears the providers' remembered "no images" latch so a transient
"empty response" does not leave the process text-only forever.
"""

import asyncio
import io
import logging
import random
import time
import weakref
from dataclasses import dataclass
from typing import Optional

from providers.router import reset_image_support

from ..llm import LLMCallFailed, complete_ex, llm_available
from .settings import get_rebuild_settings

logger = logging.getLogger("pdf2latex.rebuild.probe")

_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I: the model must read it, not guess
_PROBE_TIMEOUT_S = 90.0  # wall bound per probe call; llm.complete_ex alone would walk the whole chain


@dataclass(frozen=True)
class Probe:
    text_ok: bool
    vision_ok: bool
    detail: str
    checked_at: float


_clock = time.time  # tests replace this to move past the TTL
_cache: Optional[Probe] = None
_locks: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock]" = weakref.WeakKeyDictionary()


def _lock_for_loop() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lock = _locks.get(loop)
    if lock is None:
        lock = _locks[loop] = asyncio.Lock()
    return lock


def _fresh(probe: Optional[Probe]) -> bool:
    return probe is not None and _clock() - probe.checked_at < get_rebuild_settings().probe_ttl_s


def probe_cached() -> Optional[Probe]:
    """The last probe if it is still within the TTL, else None. Never touches the network."""
    return _cache if _fresh(_cache) else None


def clear_probe_cache() -> None:
    global _cache
    _cache = None


def _code_png(code: str) -> bytes:
    """A high-contrast PNG of `code` in the default bitmap font, scaled up so any vision model can read it."""
    from PIL import Image, ImageDraw, ImageFont

    font = ImageFont.load_default()
    scratch = Image.new("L", (1, 1), 255)
    left, top, right, bottom = ImageDraw.Draw(scratch).textbbox((0, 0), code, font=font)
    small = Image.new("L", (right - left + 8, bottom - top + 8), 255)
    ImageDraw.Draw(small).text((4 - left, 4 - top), code, fill=0, font=font)
    big = small.resize((small.width * 12, small.height * 12), Image.NEAREST)
    buf = io.BytesIO()
    big.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


async def _ask(user: str, images: tuple = ()):
    return await asyncio.wait_for(
        complete_ex("You are a connectivity check. Answer exactly as asked, nothing else.", user, images,
                    timeout=_PROBE_TIMEOUT_S, retries=0, concurrency=1, max_tokens=64, label="probe"),
        _PROBE_TIMEOUT_S + 5)


async def _run_probe() -> Probe:
    if not llm_available():
        return Probe(False, False, "no gateway configured", _clock())
    try:
        reply = await _ask("Reply with the single word OK.")
    except (LLMCallFailed, asyncio.TimeoutError) as e:
        return Probe(False, False, f"text probe failed: {str(e)[:200] or type(e).__name__}", _clock())
    if not reply.text.strip():
        return Probe(False, False, "text probe failed: empty response", _clock())

    code = "".join(random.choice(_CODE_ALPHABET) for _ in range(5))
    try:
        vision = await _ask("The image shows a 5-character code. Reply with only that code.",
                            (_code_png(code),))
    except (LLMCallFailed, asyncio.TimeoutError) as e:
        return Probe(True, False, f"vision probe failed: {str(e)[:200] or type(e).__name__}", _clock())
    echoed = code in vision.text.upper()
    if vision.images_dropped:
        return Probe(True, False, "gateway dropped the image and answered text-only", _clock())
    if not echoed:
        return Probe(True, False, "vision probe did not read the code from the image", _clock())
    return Probe(True, True, "ok", _clock())


async def probe_gateway(force: bool = False) -> Probe:
    """
    The gateway's text/vision health, cached per process for `probe_ttl_s`. Concurrent callers share
    one probe (a lock per event loop). Never raises: a failing gateway is reported as `text_ok=False`.
    """
    global _cache
    if not force and _fresh(_cache):
        return _cache
    async with _lock_for_loop():
        if not force and _fresh(_cache):
            return _cache
        if llm_available():
            reset_image_support()
        try:
            result = await _run_probe()
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — a probe must never take a job down
            result = Probe(False, False, f"probe error: {str(e)[:200]}", _clock())
        logger.info(f"gateway probe: text_ok={result.text_ok} vision_ok={result.vision_ok} ({result.detail})")
        if result.detail != "no gateway configured":
            _cache = result
        return result
