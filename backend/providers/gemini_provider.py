"""
gemini_provider.py — Gemini Web2API LLM Provider

Uses the OpenAI Python SDK pointed at an OpenAI-compatible Gemini endpoint.
Only text-based chat completions are supported (no native multimodal parts);
PDF/image content should be pre-extracted to text before sending.
"""

import os
import time
import logging
from typing import List, Dict, Any, Optional

from .base_provider import LLMProvider, LLMProviderError

logger = logging.getLogger("gemini_provider")

# Only these models are exposed to users
ALLOWED_GEMINI_MODELS = [
    {"id": "gemini-3.7-flash", "label": "Gemini 3.7 Flash", "default": True},
    {"id": "gemini-3.6-flash", "label": "Gemini 3.6 Flash", "default": False},
    {"id": "gemini-3.5-flash", "label": "Gemini 3.5 Flash", "default": False},
    {"id": "gemini-3.5-flash-thinking", "label": "Gemini 3.5 Flash Thinking", "default": False},
    {"id": "gemini-3.5-flash-thinking-lite", "label": "Gemini 3.5 Flash Thinking Lite", "default": False},
]

ALLOWED_MODEL_IDS = {m["id"] for m in ALLOWED_GEMINI_MODELS}


class GeminiProvider(LLMProvider):
    """
    Gemini Web2API Provider using the OpenAI Python SDK.

    Connects to an OpenAI-compatible endpoint at GEMINI_WEB2API_BASE_URL
    with Bearer token authentication via GEMINI_WEB2API_API_KEY.
    """

    def __init__(self):
        self.base_url = os.getenv("GEMINI_WEB2API_BASE_URL", "").rstrip("/")
        self.api_key = os.getenv("GEMINI_WEB2API_API_KEY", "")
        self._client = None

    def _get_client(self):
        """Lazy-initializes the OpenAI client pointed at Gemini Web2API."""
        if self._client is None:
            if not self.base_url or not self.api_key:
                raise LLMProviderError(
                    "Gemini Web2API not configured. Set GEMINI_WEB2API_BASE_URL and "
                    "GEMINI_WEB2API_API_KEY in .env.",
                    provider="Gemini",
                )
            try:
                from openai import OpenAI
                self._client = OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    timeout=120.0,
                )
            except ImportError:
                raise LLMProviderError(
                    "openai package is not installed. Run: pip install openai",
                    provider="Gemini",
                )
        return self._client

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
    ) -> Dict[str, Any]:
        client = self._get_client()
        target_model = self._validate_model(model)

        start_time = time.time()
        logger.info(f"Gemini Request → Model: {target_model} | Base URL: {self.base_url}")

        try:
            extra_body = {}
            if os.getenv("GEMINI_WEB_SEARCH", "true").lower() in ("true", "1", "yes"):
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
                stream_response = client.chat.completions.create(**kwargs)
                collected_chunks = []

                for chunk in stream_response:
                    if hasattr(chunk, "model") and chunk.model:
                        actual_model = chunk.model
                    if chunk.choices:
                        choice = chunk.choices[0]
                        if hasattr(choice, "delta") and choice.delta and getattr(choice.delta, "content", None):
                            collected_chunks.append(choice.delta.content)
                        if hasattr(choice, "finish_reason") and choice.finish_reason:
                            finish_reason = choice.finish_reason
                    if hasattr(chunk, "usage") and chunk.usage:
                        usage = {
                            "prompt_tokens": getattr(chunk.usage, "prompt_tokens", 0),
                            "completion_tokens": getattr(chunk.usage, "completion_tokens", 0),
                            "total_tokens": getattr(chunk.usage, "total_tokens", 0),
                        }

                content = "".join(collected_chunks)
            except Exception as stream_err:
                logger.warning(f"Gemini streaming failed ({stream_err}), trying non-streaming fallback...")
                kwargs.pop("stream", None)
                response = client.chat.completions.create(**kwargs)
                if response.choices:
                    content = response.choices[0].message.content or ""
                    finish_reason = response.choices[0].finish_reason or "stop"
                    actual_model = response.model or target_model
                    if response.usage:
                        usage = {
                            "prompt_tokens": response.usage.prompt_tokens,
                            "completion_tokens": response.usage.completion_tokens,
                            "total_tokens": response.usage.total_tokens,
                        }

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

            logger.info(
                f"Gemini Response OK | Model: {actual_model} | Duration: {duration}ms | "
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

        except LLMProviderError:
            raise
        except Exception as e:
            duration = round((time.time() - start_time) * 1000, 2)
            error_msg = str(e)

            # Parse common HTTP errors from OpenAI SDK
            status_code = None
            if hasattr(e, "status_code"):
                status_code = e.status_code

            logger.error(
                f"Gemini Web2API error: {error_msg} | Duration: {duration}ms | "
                f"Status: {status_code}"
            )
            raise LLMProviderError(
                f"Gemini Web2API error: {error_msg}",
                status_code=status_code,
                provider="Gemini",
            )
