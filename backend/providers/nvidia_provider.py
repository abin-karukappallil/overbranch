"""
nvidia_provider.py — NVIDIA NIM API Provider using OpenAI Python SDK.

Connects to NVIDIA NIM endpoints at https://integrate.api.nvidia.com/v1
using NVIDIA_API_KEY (with rotation across NVIDIA_API_KEY_1..5).
Defaults to deepseek-ai/deepseek-v4.1-flash.
Text only: image input goes to Gemini / Gemini (secondary), which the router
cycles for any request carrying image parts.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from openai import APIError, APITimeoutError, AuthenticationError, OpenAI, RateLimitError

from cancellation import LLMOperationCancelled
from .base_provider import LLMProvider, LLMProviderError
from .errors import KEY_ROTATION_KINDS, FailureKind, classify
from .key_pool import KeyPool

logger = logging.getLogger("nvidia_provider")

DEFAULT_NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_NVIDIA_MODEL = "deepseek-ai/deepseek-v4.1-flash"
MAX_KEYS = 5

NVIDIA_MODEL_ALIASES = {
    "deepseek-ai/deepseek-v4.1-flash": "deepseek-ai/deepseek-v4.1-flash",
    "deepseek-v4.1-flash": "deepseek-ai/deepseek-v4.1-flash",
    "deepseek": "deepseek-ai/deepseek-v4.1-flash",
    "deepseek-flash": "deepseek-ai/deepseek-v4.1-flash",
    "nvidia/deepseek-ai/deepseek-v4.1-flash": "deepseek-ai/deepseek-v4.1-flash",
    "nvidia/deepseek-v4.1-flash": "deepseek-ai/deepseek-v4.1-flash",
    "nvidia:deepseek-ai/deepseek-v4.1-flash": "deepseek-ai/deepseek-v4.1-flash",
    "nvidia:deepseek-v4.1-flash": "deepseek-ai/deepseek-v4.1-flash",
    "z-ai/glm-5.3": "z-ai/glm-5.3",
    "glm-5.3": "z-ai/glm-5.3",
    "glm5.3": "z-ai/glm-5.3",
    "glm": "z-ai/glm-5.3",
    "nvidia/z-ai/glm-5.3": "z-ai/glm-5.3",
    "nvidia:z-ai/glm-5.3": "z-ai/glm-5.3",
    "nvidia/nemotron-3-super-120b-a12b": "nvidia/nemotron-3-super-120b-a12b",
    "nemotron-3-super-120b-a12b": "nvidia/nemotron-3-super-120b-a12b",
}


def load_nvidia_keys() -> List[str]:
    """Loads up to five server-side NVIDIA API keys from environment."""
    root_env = Path(__file__).resolve().parent.parent.parent / ".env"
    backend_env = Path(__file__).resolve().parent.parent / ".env"
    if root_env.exists():
        load_dotenv(dotenv_path=root_env, override=False)
    if backend_env.exists():
        load_dotenv(dotenv_path=backend_env, override=False)

    keys: List[str] = []
    # Primary key first
    primary = os.getenv("NVIDIA_API_KEY", "").strip()
    if primary:
        keys.append(primary)

    # Numbered keys
    for i in range(1, MAX_KEYS + 1):
        for var in (f"NVIDIA_API_KEY_{i}", f"NVIDIA_KEY_{i}", f"NVIDIA_{i}"):
            val = os.getenv(var, "").strip()
            if val and val not in keys:
                keys.append(val)
                break

    general = os.getenv("NVIDIA_API_KEYS", "")
    for piece in general.split(","):
        k = piece.strip()
        if k and k not in keys and len(keys) < MAX_KEYS:
            keys.append(k)

    return keys[:MAX_KEYS]


class NvidiaProvider(LLMProvider):
    """
    NVIDIA NIM API provider with key pool rotation and an OpenAI-compatible client.

    Text only (``supports_images = False``): the vision model it used to carry is gone,
    and the router keeps image requests on the Gemini endpoints.
    """

    supports_images = False

    def __init__(self, pool: Optional[KeyPool] = None):
        self.base_url = os.getenv("NVIDIA_BASE_URL", DEFAULT_NVIDIA_BASE_URL).rstrip("/")
        self.default_model = os.getenv("NVIDIA_LLM_MODEL") or DEFAULT_NVIDIA_MODEL
        self.timeout = float(os.getenv("NVIDIA_TIMEOUT", "45.0"))
        self.pool = pool or KeyPool("nvidia", load_nvidia_keys())
        self._clients: Dict[str, OpenAI] = {}
        logger.info(f"NvidiaProvider initialized with {len(self.pool)} key(s), default model={self.default_model}")

    def reload_keys(self) -> None:
        """Reloads keys from environment into the pool."""
        self.pool.set_keys(load_nvidia_keys())

    @property
    def candidates(self) -> List[Dict[str, str]]:
        """Compatible with router's _is_configured check."""
        return [{"key_id": lease.key_id} for lease in self.pool.candidates()]

    def _get_client(self, api_key: str) -> OpenAI:
        cache_key = f"{self.base_url}::{api_key}"
        client = self._clients.get(cache_key)
        if client is None:
            client = OpenAI(
                base_url=self.base_url,
                api_key=api_key,
                timeout=self.timeout,
            )
            self._clients[cache_key] = client
        return client

    def get_provider_name(self) -> str:
        return "NVIDIA NIM"

    def normalize_model_name(self, model: str) -> str:
        if not model:
            return self.default_model
        clean = model.strip().lower()
        if clean.startswith("nvidia/"):
            clean = clean[7:]
        elif clean.startswith("nvidia:"):
            clean = clean[7:]
        return NVIDIA_MODEL_ALIASES.get(clean, NVIDIA_MODEL_ALIASES.get(model.strip().lower(), model.strip()))

    def get_available_models(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": "deepseek-ai/deepseek-v4.1-flash",
                "label": "DeepSeek-V4.1-Flash (NVIDIA NIM)",
                "default": True,
            },
            {
                "id": "z-ai/glm-5.3",
                "label": "GLM-5.3 (NVIDIA NIM)",
                "default": False,
            },
            {
                "id": "nvidia/nemotron-3-super-120b-a12b",
                "label": "Nemotron 3 Super 120B (NVIDIA NIM)",
                "default": False,
            },
        ]

    def _classify_error(self, exc: Exception) -> Tuple[FailureKind, Optional[int], Optional[float]]:
        if isinstance(exc, APITimeoutError):
            return FailureKind.TIMEOUT, 504, 5.0
        if isinstance(exc, AuthenticationError):
            return FailureKind.AUTH, getattr(exc, "status_code", 401), None
        if isinstance(exc, RateLimitError):
            return FailureKind.RATE_LIMIT, getattr(exc, "status_code", 429), 30.0
        if isinstance(exc, APIError):
            code = getattr(exc, "status_code", None)
            kind, retry_after = classify(code, str(exc))
            return kind, code, retry_after
        kind, retry_after = classify(None, str(exc))
        return kind, None, retry_after

    def _call_client(
        self,
        client: OpenAI,
        model: str,
        messages: List[Dict[str, Any]],
        temperature: float,
        max_tokens: int,
        stream: bool,
        key_id: str,
        cancel_token: Optional[Any] = None,
    ) -> Dict[str, Any]:
        if stream:
            stream_resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            if cancel_token:
                cancel_token.register_resource(stream_resp)
            collected = []
            actual_model = model
            finish_reason = "stop"
            usage = {}
            try:
                for chunk in stream_resp:
                    if cancel_token and cancel_token.is_cancelled():
                        try:
                            stream_resp.close()
                        except Exception:
                            pass
                        raise LLMOperationCancelled("NVIDIA NIM stream cancelled by user.")
                    if hasattr(chunk, "model") and chunk.model:
                        actual_model = chunk.model
                    if chunk.choices:
                        delta = chunk.choices[0].delta
                        if getattr(delta, "content", None):
                            collected.append(delta.content)
                        if hasattr(chunk.choices[0], "finish_reason") and chunk.choices[0].finish_reason:
                            finish_reason = chunk.choices[0].finish_reason
                    if hasattr(chunk, "usage") and chunk.usage:
                        usage = {
                            "prompt_tokens": getattr(chunk.usage, "prompt_tokens", 0),
                            "completion_tokens": getattr(chunk.usage, "completion_tokens", 0),
                            "total_tokens": getattr(chunk.usage, "total_tokens", 0),
                        }
            finally:
                if cancel_token:
                    cancel_token.unregister_resource(stream_resp)
            content = "".join(collected)
        else:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            choices = resp.choices or []
            content = choices[0].message.content if choices and choices[0].message else ""
            actual_model = resp.model or model
            finish_reason = choices[0].finish_reason if choices else "stop"
            usage = {
                "prompt_tokens": getattr(resp.usage, "prompt_tokens", 0) if resp.usage else 0,
                "completion_tokens": getattr(resp.usage, "completion_tokens", 0) if resp.usage else 0,
                "total_tokens": getattr(resp.usage, "total_tokens", 0) if resp.usage else 0,
            }

        return {
            "content": content,
            "model_used": actual_model,
            "finish_reason": finish_reason or "stop",
            "usage": usage,
            "is_fallback": False,
            "provider_name": f"NVIDIA NIM ({key_id})",
        }

    def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        api_keys: Optional[Dict[str, str]] = None,
        cancel_token: Optional[Any] = None,
        stream: bool = False,
    ) -> Dict[str, Any]:
        if cancel_token and cancel_token.is_cancelled():
            raise LLMOperationCancelled("NVIDIA NIM LLM call cancelled before execution.")

        target_model = self.normalize_model_name(model or self.default_model)

        self.reload_keys()
        leases = [(lease.key_id, lease.secret, True) for lease in self.pool.candidates()]
        user_key = ((api_keys or {}).get("nvidia") or "").strip()
        if user_key:
            leases.insert(0, ("nvidia#user", user_key, False))

        if not leases:
            raise LLMProviderError(
                "No NVIDIA API keys configured. Set NVIDIA_API_KEY in .env or provide one in settings.",
                provider="nvidia",
                kind=FailureKind.AUTH,
            )

        last: Optional[LLMProviderError] = None

        for key_id, secret, pooled in leases:
            if cancel_token and cancel_token.is_cancelled():
                raise LLMOperationCancelled("NVIDIA NIM LLM call cancelled.")

            client = self._get_client(secret)
            t0 = time.time()
            logger.info(f"NVIDIA Request → {key_id} | Model: {target_model} | Base URL: {self.base_url}")

            try:
                result = self._call_client(
                    client,
                    target_model,
                    messages,
                    temperature,
                    max_tokens,
                    stream=stream,
                    key_id=key_id,
                    cancel_token=cancel_token,
                )
            except LLMOperationCancelled:
                raise
            except LLMProviderError as err:
                last = err
                if pooled:
                    self.pool.report_failure(key_id, err.kind, err.retry_after)
            except Exception as exc:
                if cancel_token and cancel_token.is_cancelled():
                    raise LLMOperationCancelled("NVIDIA NIM LLM call stopped by user.")
                duration = round((time.time() - t0) * 1000, 2)
                kind, status_code, retry_after = self._classify_error(exc)
                logger.warning(
                    f"NVIDIA call failed on {key_id} ({kind.value}, {status_code}): {exc} | {duration}ms"
                )
                if pooled:
                    self.pool.report_failure(key_id, kind, retry_after)
                last = LLMProviderError(
                    f"NVIDIA request failed: {exc}",
                    status_code=status_code,
                    provider="nvidia",
                    kind=kind,
                    retry_after=retry_after,
                )
            else:
                if pooled:
                    self.pool.report_success(key_id)
                duration = round((time.time() - t0) * 1000, 2)
                logger.info(f"NVIDIA Response OK | Key: {key_id} | Model: {result['model_used']} | {duration}ms")
                return result

            # If error is not a key rotation kind, don't keep trying other keys
            if last and last.kind not in KEY_ROTATION_KINDS:
                raise last

        raise last or LLMProviderError(
            "All NVIDIA API keys exhausted.",
            provider="nvidia",
            kind=FailureKind.QUOTA,
        )
