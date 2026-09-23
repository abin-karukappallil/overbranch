"""
backend/rate_limiter.py — In-Memory Sliding Window Rate Limiter for OverBranch
==============================================================================
Protects API endpoints against DDoS attacks, automated scraping, and resource exhaustion.
Uses sliding-window timestamp tracking keyed by authenticated user ID, guest ID, or client IP.
"""

from __future__ import annotations

import time
import asyncio
import logging
from collections import defaultdict
from typing import Dict, List, Optional
from fastapi import Request, HTTPException, status

logger = logging.getLogger("rate_limiter")


def get_client_ip(request: Request) -> str:
    """
    Extracts the client IP address from proxy headers (X-Forwarded-For, X-Real-IP)
    or the direct client connection.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # First IP in comma-separated chain is the client IP
        client_ip = forwarded.split(",")[0].strip()
        if client_ip:
            return client_ip

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    if request.client and request.client.host:
        return request.client.host

    return "unknown"


class SlidingWindowRateLimiter:
    """
    Thread-safe in-memory sliding window rate limiter.
    Stores timestamp lists for each client key and evicts entries older than the window.
    """

    def __init__(self, times: int = 60, seconds: int = 60):
        self.times = times
        self.seconds = seconds
        self._history: Dict[str, List[float]] = defaultdict(list)
        self._lock = asyncio.Lock()
        self._last_cleanup = time.monotonic()

    async def _cleanup_old_keys(self, now: float) -> None:
        """Periodically cleans up dead keys to prevent memory leaks."""
        if now - self._last_cleanup > 300:  # every 5 minutes
            self._last_cleanup = now
            threshold = now - self.seconds
            dead_keys = [
                key for key, timestamps in self._history.items()
                if not timestamps or timestamps[-1] < threshold
            ]
            for key in dead_keys:
                del self._history[key]

    async def check(self, key: str) -> tuple[bool, int, float]:
        """
        Records an attempt and checks if within limits.
        Returns: (is_allowed, remaining_requests, retry_after_seconds)
        """
        async with self._lock:
            now = time.monotonic()
            await self._cleanup_old_keys(now)

            window_start = now - self.seconds
            timestamps = self._history[key]

            # Remove timestamps outside the sliding window
            self._history[key] = [t for t in timestamps if t > window_start]
            valid_timestamps = self._history[key]

            if len(valid_timestamps) >= self.times:
                oldest_in_window = valid_timestamps[0]
                retry_after = max(1.0, (oldest_in_window + self.seconds) - now)
                return False, 0, retry_after

            # Allow request and append timestamp
            self._history[key].append(now)
            remaining = self.times - len(self._history[key])
            return True, remaining, 0.0


class RateLimiter:
    """
    FastAPI dependency factory for endpoint-level rate limiting.
    Usage:
        @router.post("/api/...", dependencies=[Depends(RateLimiter(times=20, seconds=60))])
    """

    def __init__(self, times: int = 60, seconds: int = 60, key_prefix: str = "rl"):
        self.times = times
        self.seconds = seconds
        self.key_prefix = key_prefix
        self._limiter = SlidingWindowRateLimiter(times=times, seconds=seconds)

    async def __call__(self, request: Request) -> None:
        # Determine tracking key based on user identity or client IP
        # 1. Check if user is already authenticated on request state
        user_id = getattr(request.state, "user_id", None)
        
        # 2. Check cookies / tokens
        if not user_id:
            token = (
                request.cookies.get("__Secure-better-auth.session_token")
                or request.cookies.get("better-auth.session_token")
                or request.cookies.get("session_token")
                or request.cookies.get("guest_token")
            )
            if token:
                user_id = token[:32]

        if not user_id:
            auth_header = request.headers.get("Authorization") or ""
            if auth_header.lower().startswith("bearer "):
                user_id = auth_header[7:39].strip()

        identifier = f"{self.key_prefix}:{user_id}" if user_id else f"{self.key_prefix}:ip:{get_client_ip(request)}"

        allowed, remaining, retry_after = await self._limiter.check(identifier)

        if not allowed:
            logger.warning(f"Rate limit exceeded for key {identifier}: limit={self.times}/{self.seconds}s")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded: maximum {self.times} requests per {self.seconds}s. Please retry in {int(retry_after)} seconds.",
                headers={
                    "Retry-After": str(int(retry_after)),
                    "X-RateLimit-Limit": str(self.times),
                    "X-RateLimit-Remaining": "0",
                },
            )
