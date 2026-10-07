"""
errors.py — Failure classification shared by every LLM provider.

A provider failure is only worth retrying elsewhere when the *provider* was the
problem: a rate limit, an exhausted quota, a timeout, an outage, a model that is
not being served. A malformed request fails the same way on every provider, and
a user cancellation must stop everything, so neither of those falls back.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Optional, Tuple


class FailureKind(str, Enum):
    RATE_LIMIT = "rate_limit"
    QUOTA = "quota"
    AUTH = "auth"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    MODEL_UNAVAILABLE = "model_unavailable"
    BAD_REQUEST = "bad_request"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


# Kinds that justify moving on to the next provider in the chain.
FALLBACK_KINDS = frozenset({
    FailureKind.RATE_LIMIT,
    FailureKind.QUOTA,
    FailureKind.AUTH,
    FailureKind.TIMEOUT,
    FailureKind.UNAVAILABLE,
    FailureKind.MODEL_UNAVAILABLE,
    FailureKind.UNKNOWN,
})

# Kinds that justify trying the next key of the same provider.
KEY_ROTATION_KINDS = frozenset({
    FailureKind.RATE_LIMIT,
    FailureKind.QUOTA,
    FailureKind.AUTH,
    FailureKind.TIMEOUT,
    FailureKind.UNAVAILABLE,
    FailureKind.UNKNOWN,
})

_HTTP_STATUS_RE = re.compile(r"\bHTTP\s*([1-5][0-9]{2})\b")
_RETRY_AFTER_RE = re.compile(r"retry[- _]after[\"':\s]*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)


def _retry_after_from(text: str) -> Optional[float]:
    m = _RETRY_AFTER_RE.search(text or "")
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def classify(status_code: Optional[int], message: str = "") -> Tuple[FailureKind, Optional[float]]:
    """
    Maps an HTTP status and/or error text to a FailureKind plus an optional
    Retry-After in seconds. Status codes win over text; text catches SDK errors
    and gateways that return 200 with an error body.
    """
    low = (message or "").lower()
    retry_after = _retry_after_from(message)
    if status_code is None:
        m = _HTTP_STATUS_RE.search(message or "")
        if m:
            status_code = int(m.group(1))

    if status_code == 429:
        return FailureKind.RATE_LIMIT, retry_after
    if status_code == 402:
        return FailureKind.QUOTA, retry_after
    if status_code in (401, 403):
        return FailureKind.AUTH, retry_after
    if status_code in (408, 504, 524):
        return FailureKind.TIMEOUT, retry_after
    if status_code == 404 and "model" in low:
        return FailureKind.MODEL_UNAVAILABLE, retry_after
    if status_code in (500, 502, 503, 520, 521, 522, 529):
        return FailureKind.UNAVAILABLE, retry_after

    if "rate limit" in low or "rate_limit" in low or "too many requests" in low or "resource_exhausted" in low:
        return FailureKind.RATE_LIMIT, retry_after
    if "quota" in low or "insufficient credits" in low or "billing" in low:
        return FailureKind.QUOTA, retry_after
    if "timed out" in low or "timeout" in low or "deadline" in low:
        return FailureKind.TIMEOUT, retry_after
    if ("model" in low and ("not found" in low or "unavailable" in low or "no endpoints" in low
                            or "not available" in low or "does not exist" in low)):
        return FailureKind.MODEL_UNAVAILABLE, retry_after
    if "unauthorized" in low or "invalid api key" in low or "forbidden" in low:
        return FailureKind.AUTH, retry_after
    if ("unavailable" in low or "overloaded" in low or "connection" in low or "bad gateway" in low
            or "empty response" in low or "refusal" in low):
        return FailureKind.UNAVAILABLE, retry_after

    if status_code is not None and 400 <= status_code < 500:
        return FailureKind.BAD_REQUEST, retry_after
    return FailureKind.UNKNOWN, retry_after


def classify_exception(exc: BaseException) -> Tuple[FailureKind, Optional[float]]:
    """Classifies any exception, honouring a kind already attached to it."""
    from cancellation import LLMOperationCancelled

    if isinstance(exc, LLMOperationCancelled):
        return FailureKind.CANCELLED, None
    kind = getattr(exc, "kind", None)
    if isinstance(kind, FailureKind):
        return kind, getattr(exc, "retry_after", None)
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    return classify(status if isinstance(status, int) else None, str(exc))
