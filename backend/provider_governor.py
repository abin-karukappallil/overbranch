"""
provider_governor.py — Adaptive AIMD Provider Concurrency & Circuit Breaker

Implements Additive-Increase / Multiplicative-Decrease (AIMD) concurrency control
and circuit-breaker failover per LLM provider.
Starts cautious, auto-tunes throughput during clean operation, and immediately pulls back
or trips circuit failover on 429/502 degradation.
"""

import time
import asyncio
import logging
import collections
from typing import Dict, Any, List, Optional, Callable

try:
    from providers.router import provider_router
    from providers.base_provider import LLMProvider, LLMProviderError
except ImportError:
    from backend.providers.router import provider_router
    from backend.providers.base_provider import LLMProvider, LLMProviderError

logger = logging.getLogger("provider_governor")


class CircuitOpenError(Exception):
    """Raised when a provider's circuit is tripped due to degradation."""
    pass


class EmptyResponseError(Exception):
    """Raised when a provider returns an empty or whitespace-only response."""
    pass


class AdaptiveProviderGovernor:
    """
    AIMD (Additive-Increase / Multiplicative-Decrease) concurrency controller.
    Controls in-flight calls and trips circuit breaker on elevated error rates.
    """

    def __init__(self, provider_name: str, min_concurrency: int = 1, max_concurrency: int = 10):
        self.provider_name = provider_name
        self.min_concurrency = min_concurrency
        self.max_concurrency = max_concurrency
        self.current_limit = min_concurrency          # start conservative
        self._consecutive_successes = 0
        self._circuit_open_until: Optional[float] = None  # epoch time; None = closed (healthy)
        self._in_flight = 0
        self._lock = asyncio.Lock()
        self._waiters: List[asyncio.Event] = []
        self._recent_results = collections.deque(maxlen=20)  # (timestamp, success, error_type)

    async def acquire(self):
        """
        Acquire a slot under the current concurrency limit.
        Raises CircuitOpenError immediately if circuit is open.
        """
        while True:
            ev = None
            async with self._lock:
                now = time.time()
                if self._circuit_open_until is not None:
                    if now < self._circuit_open_until:
                        raise CircuitOpenError(
                            f"{self.provider_name} circuit is open until {self._circuit_open_until:.1f}; "
                            f"route to fallback provider instead."
                        )
                    else:
                        # Circuit cooldown has elapsed — reset circuit
                        logger.info(f"Circuit cooldown elapsed for {self.provider_name}; resetting circuit.")
                        self._circuit_open_until = None
                        self._consecutive_successes = 0

                if self._in_flight < self.current_limit:
                    self._in_flight += 1
                    return

                # Wait for capacity
                ev = asyncio.Event()
                self._waiters.append(ev)

            # Wait outside the lock
            await ev.wait()

    def release(self):
        """Release a concurrency slot and notify waiting callers."""
        self._in_flight = max(0, self._in_flight - 1)
        if self._waiters:
            ev = self._waiters.pop(0)
            ev.set()

    def _recent_502_rate(self) -> float:
        """Calculate fraction of recent calls that experienced 502/503 gateway errors."""
        if not self._recent_results:
            return 0.0
        err_count = sum(
            1 for _, success, err in self._recent_results
            if not success and err in ("gateway_502", "gateway_503")
        )
        return err_count / len(self._recent_results)

    async def report_result(self, success: bool, error_type: Optional[str] = None):
        """
        Report completion of an LLM call to adjust concurrency window via AIMD.
        """
        async with self._lock:
            self._recent_results.append((time.time(), success, error_type))

            if success:
                self._consecutive_successes += 1
                # Additive increase: after 5 consecutive clean calls, cautiously widen window
                if self._consecutive_successes >= 5 and self.current_limit < self.max_concurrency:
                    self._grow_limit(by=1)
                    self._consecutive_successes = 0
            else:
                self._consecutive_successes = 0
                if error_type in ("rate_limited", "gateway_502", "gateway_503"):
                    # Multiplicative decrease: cut concurrency hard upon load signals
                    self._shrink_limit(factor=0.5)
                    if error_type in ("gateway_502", "gateway_503") and self._recent_502_rate() > 0.3:
                        # Trip circuit entirely — stop hammering a degrading provider
                        self._circuit_open_until = time.time() + 30  # 30s cooldown
                        logger.warning(
                            f"Trip circuit breaker for {self.provider_name} (502 rate: {self._recent_502_rate():.2f}) "
                            f"for 30 seconds."
                        )

    def _grow_limit(self, by: int = 1):
        old_limit = self.current_limit
        self.current_limit = min(self.max_concurrency, self.current_limit + by)
        logger.info(f"Governor [{self.provider_name}]: Additive increase concurrency {old_limit} → {self.current_limit}")
        # Wake waiters if limit grew
        while self._waiters and self._in_flight < self.current_limit:
            ev = self._waiters.pop(0)
            ev.set()

    def _shrink_limit(self, factor: float = 0.5):
        old_limit = self.current_limit
        self.current_limit = max(self.min_concurrency, int(self.current_limit * factor))
        logger.warning(f"Governor [{self.provider_name}]: Multiplicative decrease concurrency {old_limit} → {self.current_limit}")


# ---------------------------------------------------------------------------
# Governor instances per provider
# ---------------------------------------------------------------------------

GOVERNORS: Dict[str, AdaptiveProviderGovernor] = {
    "gemini_web2api": AdaptiveProviderGovernor("gemini_web2api", min_concurrency=1, max_concurrency=4),
    "gemini":         AdaptiveProviderGovernor("gemini", min_concurrency=1, max_concurrency=4),
    "gemini_api":     AdaptiveProviderGovernor("gemini_api", min_concurrency=3, max_concurrency=12),
    "groq":           AdaptiveProviderGovernor("groq", min_concurrency=5, max_concurrency=15),
    "openrouter":     AdaptiveProviderGovernor("openrouter", min_concurrency=3, max_concurrency=10),
    "freellm":        AdaptiveProviderGovernor("freellm", min_concurrency=2, max_concurrency=8),
}

FALLBACK_CHAIN: Dict[str, str] = {
    "gemini_web2api": "groq",
    "gemini": "groq",
    "gemini_api": "groq",
    "groq": "openrouter",
    "openrouter": "freellm",
    "freellm": "groq",
}


def get_governor(provider_name: str) -> AdaptiveProviderGovernor:
    """Get or create the AdaptiveProviderGovernor for a given provider name."""
    clean_name = provider_name.strip().lower()
    if clean_name not in GOVERNORS:
        GOVERNORS[clean_name] = AdaptiveProviderGovernor(clean_name, min_concurrency=1, max_concurrency=6)
    return GOVERNORS[clean_name]


def next_fallback(provider_name: str) -> str:
    """Determine the next fallback provider when a circuit trips or fails."""
    clean_name = provider_name.strip().lower()
    return FALLBACK_CHAIN.get(clean_name, "groq")


async def call_provider_governed(
    provider_name: str,
    messages: List[Any],
    model: Optional[str] = None,
    temperature: float = 0.1,
    max_tokens: int = 4096,
    api_keys: Optional[Dict[str, str]] = None,
    max_failover_depth: int = 3,
) -> Dict[str, Any]:
    """
    Dispatches an LLM call under the provider's adaptive concurrency governor.
    Handles CircuitOpenError by immediately failing over to the next fallback provider.
    Adjusts concurrency on rate_limited / gateway_502 responses.
    """
    if max_failover_depth <= 0:
        raise LLMProviderError(f"All fallback providers exhausted starting from {provider_name}.")

    governor = get_governor(provider_name)
    try:
        await governor.acquire()
    except CircuitOpenError as e:
        logger.warning(f"{e} Rerouting immediately to fallback.")
        fallback = next_fallback(provider_name)
        return await call_provider_governed(
            provider_name=fallback,
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            api_keys=api_keys,
            max_failover_depth=max_failover_depth - 1,
        )

    try:
        provider = provider_router._providers.get(provider_name) or provider_router.route(model or provider_name)
        
        # Execute chat call in thread (all providers have sync chat method)
        response = await asyncio.to_thread(
            provider.chat,
            messages=messages,
            model=model or provider_router.get_default_model(),
            temperature=temperature,
            max_tokens=max_tokens,
            api_keys=api_keys,
        )

        content = response.get("content", "") if isinstance(response, dict) else getattr(response, "content", "")
        if not response or not (content and content.strip()):
            await governor.report_result(success=False, error_type="empty_response")
            raise EmptyResponseError(f"{provider_name} returned an empty response.")

        await governor.report_result(success=True)
        return response

    except LLMProviderError as e:
        status_code = getattr(e, "status_code", None)
        error_type = "gateway_502" if status_code in (502, 503) else \
                     "rate_limited" if status_code == 429 else "other"
        await governor.report_result(success=False, error_type=error_type)
        raise

    except Exception as e:
        error_str = str(e).lower()
        error_type = "gateway_502" if ("502" in error_str or "503" in error_str) else \
                     "rate_limited" if ("429" in error_str or "rate limit" in error_str) else "other"
        await governor.report_result(success=False, error_type=error_type)
        raise

    finally:
        governor.release()
