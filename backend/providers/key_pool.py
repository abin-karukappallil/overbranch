"""
key_pool.py — Health-tracked rotation over a provider's server-side API keys.

Selection is sticky: the pool keeps handing out the key that last worked and
only moves on when that key fails. A failed key is put on a cooldown sized to
the failure (a 429 honours Retry-After, an exhausted quota waits an hour, a
rejected key waits hours) and rejoins the rotation by itself once the cooldown
has passed. Keys are identified to callers and logs by ``key_id`` only
(``openrouter#2``) — the secret never leaves this module's state.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .errors import FailureKind

RATE_LIMIT_BASE_S = 30.0
RATE_LIMIT_MAX_S = 600.0
QUOTA_COOLDOWN_S = 3600.0
AUTH_COOLDOWN_S = 6 * 3600.0
TRANSIENT_COOLDOWN_S = 15.0


@dataclass
class KeyState:
    key_id: str
    secret: str = field(repr=False)
    status: str = "healthy"          # healthy | cooling_down
    last_failure: Optional[str] = None
    last_failure_at: Optional[float] = None
    cooldown_until: float = 0.0
    failure_count: int = 0           # consecutive failures; reset on success

    def public(self, now: float) -> Dict[str, object]:
        """The state as it may be shown or logged: no secret."""
        return {
            "key_id": self.key_id,
            "status": "healthy" if now >= self.cooldown_until else "cooling_down",
            "last_failure": self.last_failure,
            "cooldown_remaining_s": max(0.0, round(self.cooldown_until - now, 1)),
            "failure_count": self.failure_count,
        }


@dataclass
class Lease:
    """One key handed out for one request."""
    key_id: str
    secret: str = field(repr=False)


class KeyPool:
    def __init__(self, provider: str, secrets: List[str], clock: Callable[[], float] = time.monotonic):
        self.provider = provider
        self._clock = clock
        self._lock = threading.Lock()
        self._keys: List[KeyState] = []
        self._current = 0
        self.set_keys(secrets)

    # ------------------------------------------------------------------
    def set_keys(self, secrets: List[str]) -> None:
        """Replaces the key list, keeping the health state of keys that remain."""
        with self._lock:
            old = {k.secret: k for k in self._keys}
            new: List[KeyState] = []
            for i, s in enumerate(dict.fromkeys(x for x in secrets if x)):
                st = old.get(s) or KeyState(key_id=f"{self.provider}#{i + 1}", secret=s)
                st.key_id = f"{self.provider}#{i + 1}"
                new.append(st)
            current_secret = self._keys[self._current].secret if self._keys and self._current < len(self._keys) else None
            self._keys = new
            self._current = next((i for i, k in enumerate(new) if k.secret == current_secret), 0)

    def __len__(self) -> int:
        return len(self._keys)

    # ------------------------------------------------------------------
    def candidates(self) -> List[Lease]:
        """
        Keys to try for one request, in order: the current key first (if healthy),
        then the other healthy keys in rotation order. Keys on cooldown are left
        out; if *every* key is cooling down, the one whose cooldown ends soonest is
        offered so the request is not refused outright.
        """
        with self._lock:
            n = len(self._keys)
            if not n:
                return []
            now = self._clock()
            order = [self._keys[(self._current + i) % n] for i in range(n)]
            healthy = [k for k in order if now >= k.cooldown_until]
            if not healthy:
                healthy = [min(order, key=lambda k: k.cooldown_until)]
            return [Lease(k.key_id, k.secret) for k in healthy]

    def report_success(self, key_id: str) -> None:
        with self._lock:
            for i, k in enumerate(self._keys):
                if k.key_id == key_id:
                    k.failure_count = 0
                    k.cooldown_until = 0.0
                    k.status = "healthy"
                    self._current = i  # sticky: keep using what works
                    return

    def report_failure(self, key_id: str, kind: FailureKind, retry_after: Optional[float] = None) -> float:
        """Puts the key on cooldown; returns the cooldown length in seconds."""
        with self._lock:
            for i, k in enumerate(self._keys):
                if k.key_id != key_id:
                    continue
                now = self._clock()
                k.failure_count += 1
                k.last_failure = kind.value
                k.last_failure_at = now
                cooldown = self._cooldown_for(kind, retry_after, k.failure_count)
                k.cooldown_until = now + cooldown
                k.status = "cooling_down" if cooldown > 0 else "healthy"
                if cooldown > 0 and i == self._current and len(self._keys) > 1:
                    self._current = (i + 1) % len(self._keys)
                return cooldown
        return 0.0

    def snapshot(self) -> List[Dict[str, object]]:
        with self._lock:
            now = self._clock()
            return [k.public(now) for k in self._keys]

    @staticmethod
    def _cooldown_for(kind: FailureKind, retry_after: Optional[float], failures: int) -> float:
        if kind == FailureKind.RATE_LIMIT:
            if retry_after and retry_after > 0:
                return min(RATE_LIMIT_MAX_S, retry_after)
            return min(RATE_LIMIT_MAX_S, RATE_LIMIT_BASE_S * (2 ** max(0, failures - 1)))
        if kind == FailureKind.QUOTA:
            return QUOTA_COOLDOWN_S
        if kind == FailureKind.AUTH:
            return AUTH_COOLDOWN_S
        if kind in (FailureKind.TIMEOUT, FailureKind.UNAVAILABLE, FailureKind.UNKNOWN):
            return TRANSIENT_COOLDOWN_S
        # BAD_REQUEST / MODEL_UNAVAILABLE / CANCELLED say nothing about the key.
        return 0.0
