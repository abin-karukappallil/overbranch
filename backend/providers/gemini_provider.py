"""
gemini_provider.py — Gemini Web2API LLM Provider

Uses the OpenAI Python SDK pointed at an OpenAI-compatible Gemini endpoint.
Messages may include OpenAI-style image parts ({"type": "image_url", ...}); if the
endpoint rejects them, the call is retried once text-only and later calls skip images.
"""

import os
import time
import logging
from typing import List, Dict, Any, Optional

from .base_provider import LLMProvider, LLMProviderError
from .errors import classify
from .multimodal import has_image_parts, strip_image_parts
from .web2api_keys import get_web2api_base_url, load_web2api_keys

from cancellation import LLMOperationCancelled

logger = logging.getLogger("gemini_provider")

# Only these models are exposed to users
ALLOWED_GEMINI_MODELS = [
    {"id": "gemini-3.7-flash", "label": "Gemini 3.7 Flash", "default": False},
    {"id": "gemini-3.6-flash", "label": "Gemini 3.6 Flash", "default": False},
    {"id": "gemini-3.5-flash", "label": "Gemini 3.5 Flash", "default": False},
    {"id": "gemini-3.5-flash-thinking", "label": "Gemini 3.5 Flash Thinking", "default": True},
    {"id": "gemini-3.5-flash-thinking-lite", "label": "Gemini 3.5 Flash Thinking Lite", "default": False},
]

ALLOWED_MODEL_IDS = {m["id"] for m in ALLOWED_GEMINI_MODELS}


class GeminiProvider(LLMProvider):
    """
    Gemini Web2API Provider using the OpenAI Python SDK.

    Connects to an OpenAI-compatible endpoint at GEMINI_WEB2API_BASE_URL
    with Bearer token authentication via GEMINI_WEB2API_API_KEY_1..5.
    Automatically rotates across up to 5 server-side keys when rate limits occur.
    """

    def __init__(self):
        self.base_url = get_web2api_base_url()
        self.default_timeout = float(os.getenv("GEMINI_TIMEOUT", "30.0"))
        self._active_key_index = 0
        self.candidates = self._load_server_keys()
        self._clients: Dict[str, Any] = {}
        self._images_unsupported = False

    def _load_server_keys(self) -> List[Dict[str, str]]:
        """Loads up to 5 server-side Gemini Web2API keys via the shared loader."""
        keys = [{"name": k.name, "key": k.key} for k in load_web2api_keys()]
        logger.info(f"Gemini Web2API provider initialized with {len(keys)} server-side key(s)")
        return keys

    def _get_client_for_key(self, api_key: str, base_url: Optional[str] = None):
        """Lazy-initializes an OpenAI client for a given API key."""
        target_base = (base_url or self.base_url).rstrip("/")
        if not target_base:
            raise LLMProviderError(
                "Gemini Web2API not configured. Set GEMINI_WEB2API_BASE_URL and "
                "GEMINI_WEB2API_API_KEY_1..5 in .env.",
                provider="Gemini",
            )
        cache_key = f"{api_key}::{target_base}"
        if cache_key not in self._clients:
            try:
                from openai import OpenAI
                max_retries = int(os.getenv("GEMINI_MAX_RETRIES", "0"))
                self._clients[cache_key] = OpenAI(
                    api_key=api_key,
                    base_url=target_base,
                    timeout=self.default_timeout,
                    max_retries=max_retries,
                )
            except ImportError:
                raise LLMProviderError(
                    "openai package is not installed. Run: pip install openai",
                    provider="Gemini",
                )
        return self._clients[cache_key]

    def get_provider_name(self) -> str:
        return "Gemini"

    def get_available_models(self) -> List[Dict[str, Any]]:
        return list(ALLOWED_GEMINI_MODELS)

    def _validate_model(self, model: str) -> str:
        """Validates and returns the model ID. Falls back to first allowed model."""
        if model in ALLOWED_MODEL_IDS:
            return model
        logger.warning(
            f"Gemini model '{model}' not in allowed list. "
            f"Falling back to '{ALLOWED_GEMINI_MODELS[0]['id']}'."
        )
        return ALLOWED_GEMINI_MODELS[0]["id"]

    def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        api_keys: Optional[Dict[str, str]] = None,
        cancel_token: Optional[Any] = None,
        web_search: bool = False,
    ) -> Dict[str, Any]:
        args = (model, temperature, max_tokens, api_keys, cancel_token, web_search)
        if not has_image_parts(messages):
            return self._chat_once(messages, *args)
        if self._images_unsupported:
            return self._chat_once(strip_image_parts(messages), *args)
        try:
            return self._chat_once(messages, *args)
        except LLMProviderError as e:
            msg = str(e).lower()
            rejected = e.status_code in (400, 413, 415, 422) or "empty response" in msg or "image" in msg
            if not rejected:
                raise
            logger.warning(f"Gemini endpoint rejected image input ({str(e)[:120]}); retrying text-only.")
            self._images_unsupported = True
            return self._chat_once(strip_image_parts(messages), *args)

    def _chat_once(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float,
        max_tokens: int,
        api_keys: Optional[Dict[str, str]],
        cancel_token: Optional[Any],
        web_search: bool,
    ) -> Dict[str, Any]:
        if cancel_token and cancel_token.is_cancelled():
            raise LLMOperationCancelled("Gemini LLM call cancelled before execution.")

        runtime_candidates = []
        if api_keys and api_keys.get("gemini"):
            user_key = api_keys["gemini"].strip()
            if user_key:
                # Use official Gemini OpenAI-compatible endpoint for genuine AI Studio keys
                b_url = "https://generativelanguage.googleapis.com/v1beta/openai/" if user_key.startswith("AIza") else self.base_url
                runtime_candidates.append({"name": "User Gemini Key", "key": user_key, "base_url": b_url})

        # Reload server keys in case environment changed
        server_candidates = self._load_server_keys() or self.candidates
        all_candidates = runtime_candidates + server_candidates

        if not all_candidates:
            raise LLMProviderError(
                "Gemini Web2API not configured. Set GEMINI_WEB2API_BASE_URL and "
                "GEMINI_WEB2API_API_KEY_1..5 in .env.",
                provider="Gemini",
            )

        target_model = self._validate_model(model)
        total_keys = len(all_candidates)
        start_idx = self._active_key_index % total_keys
        ordered_candidates = all_candidates[start_idx:] + all_candidates[:start_idx]

        last_error = None
        last_status_code = None

        for attempt, creds in enumerate(ordered_candidates):
            if cancel_token and cancel_token.is_cancelled():
                raise LLMOperationCancelled("Gemini LLM call cancelled.")

            current_slot = (start_idx + attempt) % total_keys
            client_base_url = creds.get("base_url") or self.base_url
            start_time = time.time()
            logger.info(f"Gemini Request → Key: {creds['name']} (slot {current_slot + 1}/{total_keys}) | Model: {target_model} | Base URL: {client_base_url}")

            try:
                client = self._get_client_for_key(creds["key"], client_base_url)

                extra_body = {}
                if web_search or os.getenv("GEMINI_WEB_SEARCH", "false").lower() in ("true", "1", "yes"):
                    if web_search:
                        extra_body["web_search"] = True

                kwargs: Dict[str, Any] = {
                    "model": target_model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": True,
                }
                if extra_body:
                    kwargs["extra_body"] = extra_body

                content = ""
                actual_model = target_model
                finish_reason = "stop"
                usage = {}

                try:
                    if cancel_token and cancel_token.is_cancelled():
                        raise LLMOperationCancelled("Gemini LLM call cancelled.")

                    stream_response = client.chat.completions.create(**kwargs)
                    if cancel_token:
                        cancel_token.register_resource(stream_response)

                    collected_chunks = []
                    collected_reasoning = []
                    try:
                        for chunk in stream_response:
                            if cancel_token and cancel_token.is_cancelled():
                                try:
                                    stream_response.close()
                                except Exception:
                                    pass
                                raise LLMOperationCancelled("Gemini LLM call aborted by user.")

                            if hasattr(chunk, "model") and chunk.model:
                                actual_model = chunk.model
                            if chunk.choices:
                                choice = chunk.choices[0]
                                if hasattr(choice, "delta") and choice.delta:
                                    if getattr(choice.delta, "content", None):
                                        collected_chunks.append(choice.delta.content)
                                    if getattr(choice.delta, "reasoning_content", None):
                                        collected_reasoning.append(choice.delta.reasoning_content)
                                if hasattr(choice, "finish_reason") and choice.finish_reason:
                                    finish_reason = choice.finish_reason
                            if hasattr(chunk, "usage") and chunk.usage:
                                usage = {
                                    "prompt_tokens": getattr(chunk.usage, "prompt_tokens", 0),
                                    "completion_tokens": getattr(chunk.usage, "completion_tokens", 0),
                                    "total_tokens": getattr(chunk.usage, "total_tokens", 0),
                                }
                    finally:
                        if cancel_token:
                            cancel_token.unregister_resource(stream_response)

                    content = "".join(collected_chunks)
                    if not content and collected_reasoning:
                        reasoning_text = "".join(collected_reasoning)
                        if "{" in reasoning_text or "```" in reasoning_text or "\\" in reasoning_text:
                            content = reasoning_text
                except LLMOperationCancelled:
                    raise
                except Exception as stream_err:
                    if cancel_token and cancel_token.is_cancelled():
                        raise LLMOperationCancelled("Gemini LLM call cancelled.")
                    logger.warning(f"Gemini call failed or interrupted ({stream_err}), immediately switching to fallback...")
                    raise stream_err

                duration = round((time.time() - start_time) * 1000, 2)

                if not content:
                    raise LLMProviderError(
                        "Gemini Web2API returned empty response.",
                        provider="Gemini",
                    )

                # Refusal detection: Gemini Web2API sometimes emits canned refusal prose
                is_refusal = any(kw in content.lower() for kw in [
                    "hard time fulfilling",
                    "cannot fulfill this request",
                    "can't fulfill this request",
                    "unable to fulfill this request",
                    "against my safety guidelines",
                    "help you with something else instead",
                ])
                if is_refusal:
                    logger.warning(f"Gemini returned refusal message: '{content[:120]}'")
                    raise LLMProviderError(
                        f"Gemini Web2API refusal: '{content[:120]}'",
                        provider="Gemini"
                    )

                # Update active key index to this successful slot
                self._active_key_index = current_slot

                logger.info(
                    f"Gemini Response OK | Key: {creds['name']} | Model: {actual_model} | Duration: {duration}ms | "
                    f"Tokens: {usage.get('completion_tokens', len(content)//4)}"
                )

                return {
                    "content": content,
                    "model_used": actual_model,
                    "finish_reason": finish_reason,
                    "usage": usage,
                    "is_fallback": False,
                    "provider_name": "Gemini Web2API",
                }

            except LLMOperationCancelled:
                raise
            except Exception as e:
                duration = round((time.time() - start_time) * 1000, 2)
                error_msg = str(e)
                status_code = getattr(e, "status_code", None)
                last_error = error_msg
                last_status_code = status_code

                is_rate_limit = (
                    status_code in (429, 402, 403, 503)
                    or "rate limit" in error_msg.lower()
                    or "resource_exhausted" in error_msg.lower()
                    or "quota" in error_msg.lower()
                    or "429" in error_msg
                )

                is_timeout = (
                    status_code in (504, 408, 502)
                    or "timeout" in error_msg.lower()
                    or "timed out" in error_msg.lower()
                    or "gateway timeout" in error_msg.lower()
                )

                if is_rate_limit:
                    next_slot = (current_slot + 1) % total_keys
                    logger.warning(
                        f"Gemini Web2API {creds['name']} hit rate limit / quota ({error_msg[:120]}). "
                        f"Automatically switching to next key (slot {next_slot + 1}/{total_keys})..."
                    )
                    self._active_key_index = next_slot
                    continue

                if is_timeout:
                    next_slot = (current_slot + 1) % total_keys
                    logger.warning(
                        f"Gemini Web2API {creds['name']} timed out ({error_msg[:120]}). "
                        f"Trying next key slot {next_slot + 1} or triggering MiniMax M3 fallback..."
                    )
                    self._active_key_index = next_slot
                    continue

                logger.error(
                    f"Gemini Web2API error on {creds['name']}: {error_msg} | Duration: {duration}ms | "
                    f"Status: {status_code}"
                )
                next_slot = (current_slot + 1) % total_keys
                self._active_key_index = next_slot

        # Classified, so the router can tell a rate limit / outage / delay (fall back to
        # OpenRouter MiniMax M3) from a malformed request.
        kind, retry_after = classify(last_status_code, str(last_error or ""))
        err_lower = str(last_error or "").lower()
        if "timeout" in err_lower or "timed out" in err_lower or "deadline" in err_lower:
            kind = FailureKind.TIMEOUT
        elif "rate limit" in err_lower or "quota" in err_lower or "429" in err_lower:
            kind = FailureKind.RATE_LIMIT
        elif kind == FailureKind.BAD_REQUEST:
            kind = FailureKind.UNAVAILABLE

        raise LLMProviderError(
            f"All {total_keys} Gemini keys failed or delayed. Last error: {last_error}",
            status_code=last_status_code,
            provider="Gemini",
            kind=kind,
            retry_after=retry_after,
        )
