"""
router.py — Provider Router: the strict Web2API gateway chain

Every LLM request goes through the same ordered chain of self-hosted Web2API
Gemini gateways (WEB2API_GATEWAYS, e.g. g1 → g2 → g3 → g4 → g5 → model → overmodel)
and the WHOLE chain is cycled up to LLM_CHAIN_CYCLES (12) times. No other provider
(OpenRouter, Groq, NVIDIA) is ever consulted.

Rules
  - Attempts per call = gateways × cycles. Between full cycles the router backs off
    1, 2, 4, 8, 15, 15… seconds (cancellation-aware).
  - A gateway that timed out or answered 5xx is skipped for LLM_GATEWAY_COOLDOWN
    (30s) — unless every gateway is cooling, in which case all are tried.
  - A 400 moves on to the next gateway, but no further cycle is started after the
    pass that saw it (the same request will fail everywhere).
  - Timeouts are liveness-based: the HTTP read timeout (LLM_IDLE_TIMEOUT, 120s) is
    the max silence between two streamed chunks, so a slow answer that keeps
    streaming is never cut off. One attempt is capped at LLM_ATTEMPT_WALL_CAP (300s).
  - Exhaustion raises LLMProviderError whose message is only "Model outage — please retry."

Includes JSON schema validation and reject-retry-fail-loud error handling.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple, Callable

from .base_provider import LLMProvider, LLMProviderError
from .errors import OUTAGE_MESSAGE, FailureKind, classify_exception
from .multimodal import has_image_parts, strip_image_parts
from .gemini_provider import GeminiProvider, ALLOWED_GEMINI_MODELS, ALLOWED_MODEL_IDS as GEMINI_MODEL_IDS
from .web2api_keys import GatewaySpec, get_chain_cycles, get_gateway_specs

logger = logging.getLogger("provider_router")


def _log_llm_response(resp: dict, attempt: dict) -> None:
    """
    Prints what the model answered, so a run can be followed in the console / `docker logs`.
    LLM_LOG_RESPONSES=0 turns it off; LLM_LOG_MAX_CHARS (default 4000) bounds one entry.
    """
    if os.getenv("LLM_LOG_RESPONSES", "1").strip().lower() in ("0", "false", "no", "off"):
        return
    try:
        limit = max(200, int(os.getenv("LLM_LOG_MAX_CHARS", "4000")))
        content = str(resp.get("content") or "")
        shown = content if len(content) <= limit else content[:limit] + f"... [+{len(content) - limit} chars]"
        tool_calls = resp.get("tool_calls")
        logger.info(
            "[LLM_RESPONSE] provider=%s model=%s latency_ms=%s chars=%d%s\n%s",
            attempt.get("provider"), attempt.get("model"), attempt.get("latency_ms"), len(content),
            f" tool_calls={json.dumps(tool_calls, default=str)[:limit]}" if tool_calls else "",
            shown,
        )
    except Exception:  # noqa: BLE001 - logging must never break a call
        pass

DEFAULT_MODEL = "gemini-3.7-flash"


class TaskType(str, Enum):
    TASK_CLASSIFICATION = "task_classification"
    QUERY_REWRITING = "query_rewriting"
    FAST_PLAN = "fast_plan"
    OUTLINE_PLAN = "outline_plan"
    NODE_EDITING = "node_editing"
    DOC_RESTRUCTURING = "doc_restructuring"
    VISION_DIFF = "vision_diff"


# Every task runs on a gateway model; the gateways serve Gemini only.
TASK_ROUTING_TABLE: Dict[TaskType, str] = {t: DEFAULT_MODEL for t in TaskType}


# Pause before cycle 2, 3, 4, 5 and every later one.
CYCLE_BACKOFF_SECONDS = (1.0, 2.0, 4.0, 8.0, 15.0)

# A gateway that timed out / answered 5xx sits out this long (seconds).
DEFAULT_GATEWAY_COOLDOWN = 30.0

# Hard cap on ONE attempt, however lively its stream. The idle (read) timeout is
# what normally ends a dead attempt; this only bounds a stream that never finishes.
DEFAULT_ATTEMPT_WALL_CAP = 300.0


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def _attempt_wall_cap() -> float:
    return max(0.05, _env_float("LLM_ATTEMPT_WALL_CAP", DEFAULT_ATTEMPT_WALL_CAP))


def _gateway_cooldown() -> float:
    return max(0.0, _env_float("LLM_GATEWAY_COOLDOWN", DEFAULT_GATEWAY_COOLDOWN))


class _AttemptToken:
    """Cancellation view for ONE attempt: cancelled when the caller's token is, or when
    the router abandons the attempt (wall cap), which also closes its open stream so
    the worker thread stops instead of streaming on in the background."""

    def __init__(self, parent: Optional[Any]):
        self._parent = parent
        self._abandoned = False
        self._lock = threading.Lock()
        self._resources: set = set()

    def is_cancelled(self) -> bool:
        return self._abandoned or bool(self._parent is not None and self._parent.is_cancelled())

    def check_cancelled(self) -> None:
        from cancellation import LLMOperationCancelled
        if self.is_cancelled():
            raise LLMOperationCancelled("LLM call cancelled.")

    def register_resource(self, res: Any) -> None:
        if res is None:
            return
        with self._lock:
            self._resources.add(res)
            abandoned = self._abandoned
        if self._parent is not None:
            self._parent.register_resource(res)
        if abandoned:
            self._close(res)

    def unregister_resource(self, res: Any) -> None:
        with self._lock:
            self._resources.discard(res)
        if self._parent is not None:
            self._parent.unregister_resource(res)

    def abandon(self) -> None:
        with self._lock:
            self._abandoned = True
            resources = list(self._resources)
            self._resources.clear()
        for res in resources:
            self._close(res)

    @staticmethod
    def _close(res: Any) -> None:
        try:
            if hasattr(res, "close") and callable(res.close):
                res.close()
        except Exception:
            pass


def _call_with_deadline(
    fn: Callable[[], Dict[str, Any]], timeout: float, label: str, on_abandon: Optional[Callable[[], None]] = None
) -> Dict[str, Any]:
    """Runs fn() and gives up after ``timeout`` seconds with a TIMEOUT-kind error.
    The abandoned call is told to stop (``on_abandon``) and finishes on a daemon thread."""
    if timeout <= 0:
        return fn()
    box: Dict[str, Any] = {}

    def runner() -> None:
        try:
            box["value"] = fn()
        except BaseException as e:  # re-raised in the caller's thread
            box["error"] = e

    t = threading.Thread(target=runner, daemon=True, name=f"llm-{label}")
    t.start()
    t.join(timeout)
    if t.is_alive():
        if on_abandon is not None:
            try:
                on_abandon()
            except Exception:
                pass
        raise LLMProviderError(
            f"{label} timed out after {timeout:.0f}s (attempt wall cap)",
            status_code=504, provider=label, kind=FailureKind.TIMEOUT,
        )
    if "error" in box:
        raise box["error"]
    return box["value"]


def _is_configured(provider: LLMProvider, name: str, api_keys: Optional[Dict[str, str]]) -> bool:
    """A gateway is only worth trying with a URL and a key: server-side or the user's own."""
    if api_keys and (api_keys.get("gemini") or "").strip():
        return True
    if hasattr(provider, "reload_keys"):
        provider.reload_keys()
    if not getattr(provider, "base_url", "x"):
        return False
    candidates = getattr(provider, "candidates", None)
    if candidates is None:
        return True
    return bool(candidates)


def _notify(observer: Optional[Callable[[Dict[str, Any]], None]], attempt: Dict[str, Any]) -> None:
    if observer is None:
        return
    try:
        observer(attempt)
    except Exception as e:  # tracing must never break a call
        logger.debug(f"LLM attempt observer failed: {e}")


def validate_json_schema(payload: Any, required_fields: List[str]) -> Tuple[bool, str]:
    """Validates that payload is a dictionary containing all required_fields."""
    if not isinstance(payload, dict):
        return False, f"Expected JSON object, got {type(payload).__name__}"
    for field in required_fields:
        if field not in payload:
            return False, f"Missing required field '{field}' in JSON payload"
    return True, ""


class ProviderRouter:
    """
    Routes every request through the ordered Web2API gateway chain.
    """

    def __init__(self):
        self._clock: Callable[[], float] = time.monotonic
        self._sleep: Callable[[float], None] = time.sleep
        self._lock = threading.Lock()
        self._cooldown_until: Dict[str, float] = {}
        self._gateways: List[Tuple[str, LLMProvider]] = []
        self._gateway_sig: Optional[Tuple[Any, ...]] = None
        self._pinned = False
        self._sync_gateways()

    # ------------------------------------------------------------------
    # Gateway chain
    # ------------------------------------------------------------------

    def _sync_gateways(self) -> None:
        """(Re)builds the chain when the gateway env changed; reuses providers otherwise."""
        if self._pinned:
            return
        specs = get_gateway_specs()
        sig = tuple((s.name, s.base_url, s.shared_key, s.namespace) for s in specs)
        if sig == self._gateway_sig:
            return
        existing = dict(self._gateways)
        built: List[Tuple[str, LLMProvider]] = []
        for spec in specs:
            prev = existing.get(spec.name)
            if isinstance(prev, GeminiProvider) and prev.base_url == (spec.base_url or prev.base_url):
                built.append((spec.name, prev))
            else:
                built.append((spec.name, self._make_gateway(spec)))
        self._gateways = built
        self._gateway_sig = sig
        logger.info("LLM gateway chain: " + " -> ".join(n for n, _ in built) if built
                    else "LLM gateway chain: (none configured)")

    @staticmethod
    def _make_gateway(spec: GatewaySpec) -> GeminiProvider:
        return GeminiProvider(namespace=spec.namespace, label=spec.label or spec.name,
                              base_url=spec.base_url, shared_key=spec.shared_key)

    def set_gateway_chain(self, entries: List[Tuple[str, LLMProvider]]) -> None:
        """Pins an explicit ordered chain (tests, tooling); env changes no longer rebuild it."""
        self._gateways = list(entries)
        self._pinned = True
        self._cooldown_until.clear()

    def gateway_chain(self, api_keys: Optional[Dict[str, str]] = None) -> List[Tuple[str, LLMProvider]]:
        """The ordered, usable gateways: configured ones only, order preserved."""
        self._sync_gateways()
        return [(n, p) for n, p in self._gateways if _is_configured(p, n, api_keys)]

    def chain_active(self) -> bool:
        """True when at least one gateway is configured."""
        return bool(self.gateway_chain())

    @property
    def gemini(self) -> Optional[LLMProvider]:
        """The first gateway (compat for callers that wanted 'the Gemini provider')."""
        chain = self.gateway_chain()
        return chain[0][1] if chain else None

    # -- cooldown ------------------------------------------------------

    def _is_cooling(self, name: str, now: float) -> bool:
        with self._lock:
            return self._cooldown_until.get(name, 0.0) > now

    def _mark_down(self, name: str) -> None:
        with self._lock:
            self._cooldown_until[name] = self._clock() + _gateway_cooldown()

    def _mark_up(self, name: str) -> None:
        with self._lock:
            self._cooldown_until.pop(name, None)

    def _wait(self, seconds: float, cancel_token: Optional[Any]) -> None:
        """Backoff sleep that notices a cancellation within ~0.25s."""
        from cancellation import LLMOperationCancelled
        remaining = seconds
        while remaining > 0:
            if cancel_token is not None and cancel_token.is_cancelled():
                raise LLMOperationCancelled("LLM call cancelled.")
            step = min(0.25, remaining)
            self._sleep(step)
            remaining -= step
        if cancel_token is not None and cancel_token.is_cancelled():
            raise LLMOperationCancelled("LLM call cancelled.")

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def route(self, model: str) -> LLMProvider:
        """Every model is served by the gateway chain; this is its first gateway."""
        chain = self.gateway_chain()
        if not chain:
            raise LLMProviderError(OUTAGE_MESSAGE, provider="router", kind=FailureKind.UNAVAILABLE)
        return chain[0][1]

    @staticmethod
    def gateway_model(model: Optional[str]) -> str:
        """The gateway model for a requested name: itself when the gateways serve it, else the default."""
        clean = (model or "").strip()
        if clean in GEMINI_MODEL_IDS:
            return clean
        if clean.lower() in GEMINI_MODEL_IDS:
            return clean.lower()
        return DEFAULT_MODEL

    def get_model_for_task(self, task_type: TaskType) -> str:
        """Returns the optimal model ID for a specific task type."""
        return TASK_ROUTING_TABLE.get(task_type, DEFAULT_MODEL)

    def get_default_model(self) -> str:
        return DEFAULT_MODEL

    def get_fallback_provider(self) -> LLMProvider:
        return self.route(DEFAULT_MODEL)

    def get_fallback_model(self) -> str:
        return DEFAULT_MODEL

    def get_fast_model(self) -> str:
        return DEFAULT_MODEL

    def get_strong_model(self) -> str:
        return DEFAULT_MODEL

    def get_context_window(self, model: str) -> int:
        """Returns the context window size (in tokens) for a given model.
        Delegates to the context_strategy module's registry."""
        try:
            from context_strategy import get_model_context_window
            return get_model_context_window(model)
        except ImportError:
            return 120_000  # Conservative default

    def get_available_models(self) -> Dict[str, Any]:
        """Gateway models only."""
        return {
            "providers": [{"name": "Gemini Web2API", "models": list(ALLOWED_GEMINI_MODELS)}],
            "default_model": DEFAULT_MODEL,
        }

    def fallback_chain(
        self,
        model: str,
        api_keys: Optional[Dict[str, str]] = None,
        allow_fallback: bool = True,
        needs_images: bool = False,
    ) -> List[Tuple[str, LLMProvider, str]]:
        """[(gateway_name, provider, model)] in the order they are tried: one pass of the chain.

        ``allow_fallback`` only controls cycling (see chat): the gateways themselves are
        always the whole chain. ``needs_images`` drops a gateway whose provider cannot
        take image parts (every Web2API gateway can)."""
        target = self.gateway_model(model)
        chain: List[Tuple[str, LLMProvider, str]] = []
        for name, provider in self.gateway_chain(api_keys):
            if needs_images and not getattr(provider, "supports_images", False):
                logger.info(f"Gateway '{name}' skipped for this call: it does not accept image input")
                continue
            chain.append((name, provider, target))
        return chain

    # ------------------------------------------------------------------
    # chat
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        api_keys: Optional[Dict[str, str]] = None,
        cancel_token: Optional[Any] = None,
        observer: Optional[Callable[[Dict[str, Any]], None]] = None,
        allow_fallback: bool = True,
    ) -> Dict[str, Any]:
        """
        Walks the gateway chain in order, cycling it up to LLM_CHAIN_CYCLES times (see the
        module docstring for the cooldown / 400 / backoff rules). A user cancellation is
        raised immediately.

        ``allow_fallback=False`` makes ONE pass over the chain instead of cycling it.

        The response carries ``provider`` (the gateway name), ``model_used``, ``key_id``
        (never a key), ``is_fallback`` (True when an earlier attempt failed) and
        ``attempts``. ``observer`` receives one dict per attempt: provider, model, ok,
        failure, status_code, latency_ms, attempt, total, cycle, cycles, will_retry.
        """
        from cancellation import LLMOperationCancelled

        needs_images = has_image_parts(messages)
        chain = self.fallback_chain(model, api_keys, allow_fallback=allow_fallback, needs_images=needs_images)
        attempts: List[Dict[str, Any]] = []
        if not chain:
            logger.error("LLM call failed: no Web2API gateway is configured (set WEB2API_GATEWAYS + WEB2API_API_KEY)")
            err = LLMProviderError(OUTAGE_MESSAGE, provider="router", kind=FailureKind.UNAVAILABLE)
            setattr(err, "attempts", attempts)
            raise err

        n = len(chain)
        cycles = get_chain_cycles() if allow_fallback else 1
        total = n * cycles
        attempt_no = 0
        last_err: Optional[BaseException] = None
        last_kind = FailureKind.UNAVAILABLE
        last_status: Optional[int] = None

        for cycle in range(cycles):
            if cycle > 0:
                self._wait(CYCLE_BACKOFF_SECONDS[min(cycle - 1, len(CYCLE_BACKOFF_SECONDS) - 1)], cancel_token)
            if cancel_token is not None and cancel_token.is_cancelled():
                raise LLMOperationCancelled("LLM call cancelled.")

            now = self._clock()
            cooling = {name for name, _, _ in chain if self._is_cooling(name, now)}
            skip = cooling if len(cooling) < n else set()
            pass_saw_bad_request = False
            pass_names = [i for i, (name, _, _) in enumerate(chain) if name not in skip]

            for idx in pass_names:
                name, provider, target_model = chain[idx]
                if cancel_token is not None and cancel_token.is_cancelled():
                    raise LLMOperationCancelled("LLM call cancelled.")
                attempt_no += 1
                t0 = time.time()
                provider_messages = messages
                if needs_images and not getattr(provider, "supports_images", False):
                    provider_messages = strip_image_parts(messages)
                attempt_token = _AttemptToken(cancel_token)
                try:
                    resp = _call_with_deadline(
                        lambda p=provider, pm=provider_messages, tm=target_model, tok=attempt_token: p.chat(
                            messages=pm,
                            model=tm,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            api_keys=api_keys,
                            cancel_token=tok,
                        ),
                        _attempt_wall_cap(),
                        name,
                        on_abandon=attempt_token.abandon,
                    )
                except LLMOperationCancelled:
                    raise
                except Exception as err:
                    if cancel_token is not None and cancel_token.is_cancelled():
                        raise LLMOperationCancelled("LLM call cancelled.")
                    kind, _retry_after = classify_exception(err)
                    status = getattr(err, "status_code", None)
                    if kind == FailureKind.CANCELLED:
                        raise
                    if kind == FailureKind.BAD_REQUEST:
                        pass_saw_bad_request = True
                    elif kind in (FailureKind.TIMEOUT, FailureKind.UNAVAILABLE, FailureKind.UNKNOWN) or (
                            isinstance(status, int) and status >= 500):
                        self._mark_down(name)
                    last_err, last_kind, last_status = err, kind, status if isinstance(status, int) else None
                    later_in_pass = idx != pass_names[-1]
                    will_retry = later_in_pass or (cycle < cycles - 1 and not pass_saw_bad_request)
                    attempt = {
                        "provider": name, "model": target_model, "ok": False, "failure": kind.value,
                        "status_code": status,
                        "latency_ms": round((time.time() - t0) * 1000, 1),
                        "attempt": attempt_no, "total": total, "cycle": cycle + 1, "cycles": cycles,
                        "will_retry": will_retry,
                    }
                    attempts.append(attempt)
                    _notify(observer, attempt)
                    logger.warning(
                        f"Gateway '{name}' failed ({kind.value}, status={status}): {str(err)[:200]} "
                        f"[attempt {attempt_no}/{total}, cycle {cycle + 1}/{cycles}"
                        f"{'' if will_retry else ', chain exhausted'}]"
                    )
                    continue

                self._mark_up(name)
                resp = dict(resp)
                resp["provider"] = name
                resp.setdefault("model_used", target_model)
                resp.setdefault("key_id", None)
                resp["is_fallback"] = attempt_no > 1
                attempt = {
                    "provider": name, "model": resp.get("model_used") or target_model, "ok": True,
                    "key_id": resp.get("key_id"), "latency_ms": round((time.time() - t0) * 1000, 1),
                    "usage": resp.get("usage") or {},
                    "attempt": attempt_no, "total": total, "cycle": cycle + 1, "cycles": cycles,
                    "will_retry": False,
                }
                attempts.append(attempt)
                _notify(observer, attempt)
                resp["attempts"] = attempts
                _log_llm_response(resp, attempt)
                return resp

            if pass_saw_bad_request:
                logger.error("LLM call rejected as a bad request by a gateway; not cycling the chain again")
                break

        logger.error(f"LLM call failed: gateway chain exhausted after {len(attempts)} attempt(s) "
                     f"(last: {last_kind.value}: {str(last_err)[:200]})")
        err = LLMProviderError(OUTAGE_MESSAGE, status_code=last_status, provider="router", kind=last_kind)
        err.__cause__ = last_err
        setattr(err, "attempts", attempts)
        raise err

    def chat_fast_tier(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.1,
        max_tokens: int = 2048,
        api_keys: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """The fast tier is the same gateway chain."""
        return self.chat(messages=messages, model=self.get_fast_model(), temperature=temperature,
                         max_tokens=max_tokens, api_keys=api_keys)

    def chat_json_with_retry(
        self,
        messages: List[Dict[str, Any]],
        task_type: TaskType,
        required_fields: List[str],
        temperature: float = 0.1,
        max_tokens: int = 2048,
        api_keys: Optional[Dict[str, str]] = None,
        max_retries: int = 1,
    ) -> Dict[str, Any]:
        """
        Executes a task-appropriate LLM call with JSON schema validation.
        Implements reject-retry-then-fail-loud pattern.
        """
        model = self.get_model_for_task(task_type)

        current_messages = list(messages)
        for attempt in range(max_retries + 1):
            try:
                resp = self.chat(
                    messages=current_messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    api_keys=api_keys,
                )
                raw_content = resp.get("content", "").strip()
                if raw_content.startswith("```"):
                    raw_content = re.sub(r"^```(?:json)?\s*", "", raw_content)
                    raw_content = re.sub(r"\s*```$", "", raw_content)
                raw_content = raw_content.strip()

                parsed = json.loads(raw_content)
                valid, err_msg = validate_json_schema(parsed, required_fields)
                if valid:
                    return parsed

                if attempt < max_retries:
                    logger.warning(f"Output schema validation failed ({err_msg}). Retrying with error feedback...")
                    current_messages.append({"role": "assistant", "content": raw_content})
                    current_messages.append({
                        "role": "user",
                        "content": f"ERROR: The response was invalid JSON or missing fields: {err_msg}. Return the corrected JSON object strictly matching schema."
                    })
                else:
                    raise LLMProviderError(f"Malformed output failed schema validation: {err_msg}")

            except json.JSONDecodeError as jde:
                if attempt < max_retries:
                    logger.warning(f"JSON parsing error ({jde}). Retrying with format correction prompt...")
                    current_messages.append({
                        "role": "user",
                        "content": "ERROR: Response was not valid JSON. Output ONLY a valid JSON object without surrounding commentary."
                    })
                else:
                    raise LLMProviderError(f"Failed to parse JSON response after {max_retries + 1} attempts: {jde}")

        raise LLMProviderError(f"Task '{task_type.value}' failed JSON validation after retries.")


# Singleton instance
provider_router = ProviderRouter()


def get_fallback_provider() -> LLMProvider:
    return provider_router.get_fallback_provider()


def get_fallback_model() -> str:
    return provider_router.get_fallback_model()


def get_fast_model() -> str:
    return provider_router.get_fast_model()


def get_strong_model() -> str:
    return provider_router.get_strong_model()
