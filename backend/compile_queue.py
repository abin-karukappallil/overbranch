"""
compile_queue.py — Concurrency-Limited LaTeX Compilation Queue

Guards system resources during simultaneous LaTeX compilation requests:
- Async semaphore limits concurrent pdflatex / latexmk processes to MAX_CONCURRENT_COMPILES (default: 4)
- Bounded queue depth applies backpressure (HTTP 429) when overloaded
- Tracks latency, queue wait time, and compilation throughput metrics
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Callable, Dict, Optional, TypeVar

logger = logging.getLogger("compile_queue")

MAX_CONCURRENT_COMPILES = int(os.getenv("MAX_CONCURRENT_COMPILES", "4"))
MAX_QUEUE_DEPTH = int(os.getenv("MAX_QUEUE_DEPTH", "20"))
QUEUE_TIMEOUT_SECONDS = float(os.getenv("COMPILE_QUEUE_TIMEOUT", "45.0"))

T = TypeVar("T")


class CompileQueueFullError(Exception):
    """Raised when compilation concurrency limit and wait queue are saturated."""
    def __init__(self, message: str = "Compilation queue is full. Please retry in a few seconds.", estimated_wait_s: float = 3.0):
        super().__init__(message)
        self.estimated_wait_s = estimated_wait_s


class CompileQueue:
    """Manages concurrent compilation tasks with semaphore gating and backpressure."""

    def __init__(self, max_concurrent: int = MAX_CONCURRENT_COMPILES, max_depth: int = MAX_QUEUE_DEPTH):
        self.max_concurrent = max_concurrent
        self.max_depth = max_depth
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._current_waiting: int = 0
        self._active_compiles: int = 0
        self._total_completed: int = 0

    def _get_semaphore(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.max_concurrent)
        return self._semaphore

    @property
    def active_count(self) -> int:
        return self._active_compiles

    @property
    def waiting_count(self) -> int:
        return self._current_waiting

    async def submit(self, func: Callable[..., T], *args, **kwargs) -> T:
        """
        Submits a synchronous compilation function to the concurrency-controlled queue.
        Executes in loop threadpool while holding semaphore.
        """
        if self._current_waiting >= self.max_depth:
            logger.warning(f"Compile queue depth exceeded limit ({self._current_waiting}/{self.max_depth}). Rejecting request.")
            raise CompileQueueFullError(
                message=f"Compilation queue is at capacity ({self._current_waiting} waiting). Please try again shortly.",
                estimated_wait_s=round(self._current_waiting * 2.0, 1),
            )

        sem = self._get_semaphore()
        self._current_waiting += 1
        wait_start = time.perf_counter()
        acquired = False

        try:
            # Wait for available slot
            try:
                await asyncio.wait_for(sem.acquire(), timeout=QUEUE_TIMEOUT_SECONDS)
                acquired = True
            except asyncio.TimeoutError:
                logger.error(f"Timed out waiting {QUEUE_TIMEOUT_SECONDS}s for compilation slot.")
                raise CompileQueueFullError(
                    message="Compilation slot acquisition timed out due to heavy server load.",
                    estimated_wait_s=5.0,
                )
        finally:
            self._current_waiting -= 1

        wait_latency = (time.perf_counter() - wait_start) * 1000
        self._active_compiles += 1
        logger.info(f"[COMPILE_QUEUE] Slot acquired after {wait_latency:.1f}ms wait. Active: {self._active_compiles}/{self.max_concurrent}")

        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(None, lambda: func(*args, **kwargs))
            self._total_completed += 1
            return result
        finally:
            self._active_compiles -= 1
            if acquired:
                sem.release()

    def run_sync(self, func: Callable[..., T], *args, **kwargs) -> T:
        """
        Synchronous fallback execution for non-async callers.
        """
        return func(*args, **kwargs)


compile_queue = CompileQueue(
    max_concurrent=MAX_CONCURRENT_COMPILES,
    max_depth=MAX_QUEUE_DEPTH,
)
