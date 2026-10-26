"""
router.py — Provider Router by Task Type

Routes tasks and model names to the appropriate LLM provider:
  - Task classification (§2.1) → Fast tier (Groq GPT-OSS-120B / Gemini 3.7 Flash)
  - Query rewriting → Fast tier
  - Node-scoped editing → Mid-size strong instruction following (Gemini 3.7 Flash)
  - Document-wide restructuring → Strongest available reasoning (Gemini 3.7 Flash / MiniMax-M3)
  - PDF section synthesis → Strong long-context tier
  - Fidelity-diff vision check → Vision-capable tier (Gemini → Gemini secondary, looped)

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
from .errors import FALLBACK_KINDS, FailureKind, classify_exception
from .groq_provider import GroqProvider
from .multimodal import has_image_parts, strip_image_parts
from .gemini_provider import GeminiProvider, ALLOWED_MODEL_IDS as GEMINI_MODEL_IDS
from .nvidia_provider import NvidiaProvider
from .openrouter_provider import OpenRouterProvider

logger = logging.getLogger("provider_router")

DEFAULT_MODEL = "gemini-3.7-flash"


class TaskType(str, Enum):
    TASK_CLASSIFICATION = "task_classification"
    QUERY_REWRITING = "query_rewriting"
    FAST_PLAN = "fast_plan"
    OUTLINE_PLAN = "outline_plan"
    NODE_EDITING = "node_editing"
    DOC_RESTRUCTURING = "doc_restructuring"
    VISION_DIFF = "vision_diff"


# Task type to recommended model class mapping
TASK_ROUTING_TABLE: Dict[TaskType, str] = {
    TaskType.TASK_CLASSIFICATION: "llama-3.1-8b-instant",
    TaskType.QUERY_REWRITING: "llama-3.1-8b-instant",
    TaskType.FAST_PLAN: "llama-3.1-8b-instant",
    TaskType.OUTLINE_PLAN: "llama-3.1-8b-instant",
    TaskType.NODE_EDITING: "gemini-3.7-flash",
    TaskType.DOC_RESTRUCTURING: "gemini-3.7-flash",
    TaskType.VISION_DIFF: "gemini-3.7-flash",
}


# Primary is the Gemini Web2API endpoint. When it times out the next stop is its
# twin deployment (same provider class, GEMINI2_* env), then OpenRouter MiniMax M3.
# A request carrying images keeps only the image-capable hops, so it cycles
# gemini → gemini2 → gemini → … (see fallback_chain's needs_images).
DEFAULT_FALLBACK_CHAIN = "gemini2,openrouter:minimax/minimax-m3"


# Total wall-clock budget for ONE provider's attempt, when a fallback is still
# waiting behind it. Gemini rotates its own keys on timeout (GEMINI_TIMEOUT x up to
# 5 keys), so without a bound the caller can give up before the router ever sees a
# failure. The default clears one full GEMINI_TIMEOUT attempt and part of a second,
# so a slow-but-working endpoint still answers while a dead one is handed on rather
# than burning every key slot. 0 disables the bound.
DEFAULT_PROVIDER_ATTEMPT_TIMEOUT = 30.0


# Maximum number of fallback attempts when cycling through providers.
# The chain (e.g. gemini → gemini2 → openrouter) repeats until this cap.
DEFAULT_MAX_FALLBACK_ATTEMPTS = 12


def _attempt_timeout() -> float:
    try:
        return float(os.getenv("LLM_PROVIDER_ATTEMPT_TIMEOUT", DEFAULT_PROVIDER_ATTEMPT_TIMEOUT))
    except ValueError:
        return DEFAULT_PROVIDER_ATTEMPT_TIMEOUT


def _max_fallback_attempts() -> int:
    try:
        return int(os.getenv("LLM_MAX_FALLBACK_ATTEMPTS", DEFAULT_MAX_FALLBACK_ATTEMPTS))
    except ValueError:
        return DEFAULT_MAX_FALLBACK_ATTEMPTS


def _call_with_deadline(fn: Callable[[], Dict[str, Any]], timeout: float, label: str) -> Dict[str, Any]:
    """Runs fn() and gives up after ``timeout`` seconds with a TIMEOUT-kind error.
    The abandoned call finishes (or hits its own client timeout) on a daemon thread."""
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
        raise LLMProviderError(
            f"{label} timed out after {timeout:.0f}s (provider attempt budget)",
            status_code=504, provider=label, kind=FailureKind.TIMEOUT,
        )
    if "error" in box:
        raise box["error"]
    return box["value"]


def _fallback_entries() -> List[str]:
    """LLM_FALLBACK_CHAIN entries first, then the default entry unless already named,
    so a configured chain can never shrink the router to a single candidate."""
    raw = os.getenv("LLM_FALLBACK_CHAIN", DEFAULT_FALLBACK_CHAIN)
    entries = [e.strip() for e in raw.split(",") if e.strip()]
    for default in DEFAULT_FALLBACK_CHAIN.split(","):
        default = default.strip()
        if default and default.lower() not in (e.lower() for e in entries):
            entries.append(default)
    return entries


def _is_configured(provider: LLMProvider, name: str, api_keys: Optional[Dict[str, str]]) -> bool:
    """A fallback is only worth trying when it has a key: server-side or the user's own."""
    if api_keys and (api_keys.get(name) or "").strip():
        return True
    if hasattr(provider, "reload_keys"):
        provider.reload_keys()
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
    Routes model names and task types to provider instances.
    """

    def __init__(self):
        self.groq = GroqProvider()
        self.gemini = GeminiProvider()
        # The same Web2API provider against a second deployment, so a timed-out
        # primary endpoint falls over to its twin before leaving Gemini entirely.
        self.gemini2 = GeminiProvider(namespace="GEMINI2", label="Gemini (secondary)")
        self.openrouter = OpenRouterProvider()
        self.nvidia = NvidiaProvider()
        self._providers: Dict[str, LLMProvider] = {
            "groq": self.groq,
            "gemini": self.gemini,
            "gemini2": self.gemini2,
            "openrouter": self.openrouter,
            "nvidia": self.nvidia,
        }

    def route(self, model: str) -> LLMProvider:
        """Determines which provider handles a given model name."""
        if not model:
            return self.gemini

        clean_model = model.strip().lower()

        if clean_model in ("auto:smart", "auto", "smart", "default") or clean_model.startswith("auto"):
            return self.gemini

        if clean_model.startswith("gemini-") or clean_model in GEMINI_MODEL_IDS or "gemini" in clean_model:
            return self.gemini

        if (
            clean_model.startswith("groq/")
            or clean_model.startswith("groq:")
            or clean_model.startswith("llama-3")
            or clean_model.startswith("llama3")
            or clean_model in ("fast", "groq-fast", "mixtral", "gemma2-9b", "gemma2-9b-it")
            or "gpt-oss-120b" in clean_model
            or "instant" in clean_model
        ):
            return self.groq

        return self.openrouter

    def get_model_for_task(self, task_type: TaskType) -> str:
        """Returns the optimal model ID for a specific task type."""
        return TASK_ROUTING_TABLE.get(task_type, DEFAULT_MODEL)

    def get_default_model(self) -> str:
        return DEFAULT_MODEL

    def get_fallback_provider(self) -> LLMProvider:
        return self.openrouter

    def get_fallback_model(self) -> str:
        return self.openrouter.default_model

    def get_fast_model(self) -> str:
        return "llama-3.1-8b-instant"

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
        providers_list = []

        gemini_models = self.gemini.get_available_models()
        if gemini_models:
            providers_list.append({
                "name": "Gemini Web2API",
                "models": gemini_models,
            })

        groq_models = self.groq.get_available_models()
        if groq_models:
            providers_list.append({
                "name": "Groq (Ultra-Fast Inference)",
                "models": groq_models,
            })

        openrouter_models = self.openrouter.get_available_models()
        if openrouter_models:
            providers_list.append({
                "name": self.openrouter.get_provider_name(),
                "models": openrouter_models,
            })

        return {
            "providers": providers_list,
            "default_model": DEFAULT_MODEL,
        }

    # ------------------------------------------------------------------
    # Fallback chain
    # ------------------------------------------------------------------

    def register_provider(self, name: str, provider: LLMProvider) -> None:
        """Adds a provider that LLM_FALLBACK_CHAIN entries can name."""
        self._providers[name] = provider

    def fallback_chain(
        self,
        model: str,
        api_keys: Optional[Dict[str, str]] = None,
        allow_fallback: bool = True,
        needs_images: bool = False,
    ) -> List[Tuple[str, LLMProvider, str]]:
        """
        [(provider_name, provider, model)] to try in order: the provider that
        serves ``model`` first, then every configured fallback that is not the
        same provider+model. Fallbacks come from LLM_FALLBACK_CHAIN
        ("provider:model,provider:model"), plus DEFAULT_FALLBACK_CHAIN entries it
        does not already name — the second Web2API endpoint, then MiniMax M3.

        With ``needs_images`` (the request carries image parts) only providers that
        accept image input stay in the chain, so a vision request cycles
        Gemini → Gemini (secondary) instead of reaching a text-only hop that would
        have to drop the pictures the question is about.
        """
        primary = self.route(model)
        if needs_images and not getattr(primary, "supports_images", False):
            logger.info(
                f"Model '{model}' routes to a text-only provider but the request carries images; "
                f"using the Gemini Web2API endpoints instead."
            )
            primary, model = self.gemini, DEFAULT_MODEL
        primary_name = next((n for n, p in self._providers.items() if p is primary), primary.get_provider_name())
        chain: List[Tuple[str, LLMProvider, str]] = [(primary_name, primary, model)]
        if not allow_fallback:
            return chain
        for entry in _fallback_entries():
            name, _, fb_model = entry.partition(":")
            name = name.strip().lower()
            provider = self._providers.get(name)
            if provider is None:
                logger.warning(f"LLM_FALLBACK_CHAIN entry '{entry}' dropped: unknown provider '{name}'")
                continue
            fb_model = fb_model.strip() or (self.get_fallback_model() if provider is self.openrouter else model)
            if provider is primary and fb_model == model:
                logger.warning(f"LLM_FALLBACK_CHAIN entry '{entry}' dropped: same provider and model as the primary")
                continue
            if not _is_configured(provider, name, api_keys):
                logger.warning(f"LLM_FALLBACK_CHAIN entry '{entry}' dropped: provider '{name}' has no API key configured")
                continue
            if needs_images and not getattr(provider, "supports_images", False):
                logger.info(f"Fallback '{entry}' skipped for this call: it does not accept image input")
                continue
            chain.append((name, provider, fb_model))
        return chain

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
        Calls the provider for ``model`` and walks the fallback chain on provider
        failures (rate limit, quota, timeout, outage, unavailable model). A user
        cancellation or a malformed request is raised immediately — another
        provider would not do better.

        The response carries ``provider``, ``model_used``, ``key_id`` (never a
        key), ``is_fallback`` and ``attempts``. ``observer`` receives one dict per
        attempt, for tracing.
        """
        from cancellation import LLMOperationCancelled

        clean_model = (model or "").strip().lower()
        if not clean_model or clean_model in ("auto:smart", "auto", "smart", "default") or clean_model.startswith("auto"):
            model = DEFAULT_MODEL

        needs_images = has_image_parts(messages)
        chain = self.fallback_chain(
            model, api_keys, allow_fallback=allow_fallback, needs_images=needs_images
        )
        cancel_kwargs = {"cancel_token": cancel_token} if cancel_token is not None else {}
        attempts: List[Dict[str, Any]] = []

        # With fallbacks, cycle through the chain up to max_attempts, capped at 2 full cycles.
        max_attempts = min(_max_fallback_attempts(), len(chain) * 2) if allow_fallback and len(chain) > 1 else len(chain)
        dead_providers: set = set()

        for idx in range(max_attempts):
            if cancel_token is not None and cancel_token.is_cancelled():
                raise LLMOperationCancelled("LLM call cancelled.")

            name, provider, target_model = chain[idx % len(chain)]
            if name in dead_providers and len(dead_providers) < len(chain):
                continue
            t0 = time.time()
            # Image-capable providers are the only ones left in the chain when images are
            # present; a text-only provider can still be the single candidate (no fallback,
            # or none configured), and then it gets the same step as text.
            provider_messages = messages
            if needs_images and not getattr(provider, "supports_images", False):
                provider_messages = strip_image_parts(messages)
            is_last = idx == max_attempts - 1 or (len(dead_providers) + 1 >= len(chain))
            try:
                resp = _call_with_deadline(
                    lambda p=provider, pm=provider_messages, tm=target_model: p.chat(
                        messages=pm,
                        model=tm,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        api_keys=api_keys,
                        **cancel_kwargs,
                    ),
                    0 if is_last else _attempt_timeout(),
                    name,
                )
            except LLMOperationCancelled:
                raise
            except Exception as err:
                kind, _retry_after = classify_exception(err)
                status = getattr(err, "status_code", None)
                if status in (401, 402, 403, 404) or "SSL" in str(err) or "certificate" in str(err).lower():
                    dead_providers.add(name)
                attempt = {
                    "provider": name, "model": target_model, "ok": False, "failure": kind.value,
                    "status_code": status,
                    "latency_ms": round((time.time() - t0) * 1000, 1),
                }
                attempts.append(attempt)
                _notify(observer, attempt)
                if kind not in FALLBACK_KINDS or is_last:
                    tail = "no fallback for this failure" if not is_last else f"fallback chain exhausted after {len(attempts)} attempts"
                    logger.error(f"LLM call failed on {name} ({kind.value}); {tail}")
                    setattr(err, "attempts", attempts)
                    raise
                next_entry = chain[(idx + 1) % len(chain)]
                logger.warning(f"Provider '{name}' failed or delayed ({kind.value}); falling back to "
                               f"{next_entry[0]}:{next_entry[2]} (attempt {idx + 2}/{max_attempts})")
                continue

            resp = dict(resp)
            resp["provider"] = name
            resp.setdefault("model_used", target_model)
            resp.setdefault("key_id", None)
            resp["is_fallback"] = idx > 0
            attempt = {
                "provider": name, "model": resp.get("model_used") or target_model, "ok": True,
                "key_id": resp.get("key_id"), "latency_ms": round((time.time() - t0) * 1000, 1),
                "usage": resp.get("usage") or {},
            }
            attempts.append(attempt)
            _notify(observer, attempt)
            resp["attempts"] = attempts
            return resp

        raise LLMProviderError("No LLM provider is configured.", provider="router")

    def chat_fast_tier(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.1,
        max_tokens: int = 2048,
        api_keys: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        fast_model = self.get_fast_model()
        try:
            return self.groq.chat(
                messages=messages,
                model=fast_model,
                temperature=temperature,
                max_tokens=max_tokens,
                api_keys=api_keys,
            )
        except Exception as groq_err:
            logger.info(f"Fast tier Groq failed ({groq_err}), routing to Gemini Web2API fallback...")
            return self.gemini.chat(
                messages=messages,
                model=DEFAULT_MODEL,
                temperature=temperature,
                max_tokens=max_tokens,
                api_keys=api_keys,
            )

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
        provider = self.route(model)

        current_messages = list(messages)
        for attempt in range(max_retries + 1):
            try:
                resp = provider.chat(
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
