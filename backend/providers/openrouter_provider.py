"""
openrouter_provider.py — OpenRouter provider with health-tracked key rotation.

Up to five server-side keys (OPENROUTER_API_KEY_1..5) are managed by a KeyPool:
the key that last worked keeps being used, a key that hits a rate limit / quota /
auth error is put on a cooldown and the next healthy key is tried, and a cooled
down key rejoins the rotation automatically. Keys never leave the server; callers
and logs only ever see a ``key_id`` such as ``openrouter#2``.

The fallback model (MiniMax M3) comes from OPENROUTER_FALLBACK_MODEL.
"""

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

import requests

from .base_provider import LLMProvider, LLMProviderError
from .errors import KEY_ROTATION_KINDS, FailureKind, classify
from .key_pool import KeyPool
from cancellation import LLMOperationCancelled

logger = logging.getLogger("openrouter_provider")

OPENROUTER_API_BASE = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_FALLBACK_MODEL = "minimax/minimax-m3"
MAX_KEYS = 5

_MINIMAX_M3_ALIASES = {
    "minimax m3", "minimax-m3", "minimax", "minimax/minimax-m3", "minimax/m3", "m3",
}


def load_openrouter_keys() -> List[str]:
    """Up to five server-side OpenRouter keys, numbered first, then any comma list."""
    keys: List[str] = []
    for i in range(1, MAX_KEYS + 1):
        for var in (f"OPENROUTER_API_KEY_{i}", f"OPENROUTER_{i}", f"OPENROUTER_KEY_{i}",
                    f"MINIMAX_API_KEY_{i}", f"MINIMAX_KEY_{i}", f"MINIMAX_{i}"):
            val = os.getenv(var, "").strip()
            if val:
                if val not in keys:
                    keys.append(val)
                break
    general = (os.getenv("OPENROUTER_API_KEYS", "") or os.getenv("OPENROUTER_API_KEY", "")
               or os.getenv("MINIMAX_API_KEYS", "") or os.getenv("MINIMAX_API_KEY", ""))
    for piece in general.split(","):
        k = piece.strip()
        if k and k not in keys and len(keys) < MAX_KEYS:
            keys.append(k)
    return keys[:MAX_KEYS]


class OpenRouterProvider(LLMProvider):
    """OpenRouter LLM provider with five-key server-side rotation and per-key health."""

    def __init__(self, pool: Optional[KeyPool] = None):
        self.default_model = os.getenv("OPENROUTER_FALLBACK_MODEL", DEFAULT_FALLBACK_MODEL)
        self.timeout = float(os.getenv("OPENROUTER_TIMEOUT", "90"))
        self.pool = pool or KeyPool("openrouter", load_openrouter_keys())
        logger.info(f"OpenRouter provider initialized with {len(self.pool)} server-side key(s)")

    @property
    def candidates(self) -> List[Dict[str, str]]:
        """Backward-compatible view (truthy when keys are configured). No secrets."""
        return [{"name": s["key_id"]} for s in self.pool.snapshot()]

    def reload_keys(self) -> None:
        """Picks up keys added to the environment at runtime, keeping key health."""
        keys = load_openrouter_keys()
        if keys:
            self.pool.set_keys(keys)

    def get_provider_name(self) -> str:
        return "OpenRouter"

    def get_available_models(self) -> List[Dict[str, Any]]:
        return [
            {"id": "minimax/minimax-m3", "label": "MiniMax M3", "default": True},
            {"id": "meta-llama/llama-3.3-70b-instruct", "label": "Llama 3.3 70B (Fast)", "default": False},
            {"id": "openai/gpt-4o-mini", "label": "GPT-4o Mini (Fast)", "default": False},
            {"id": "qwen/qwen-2.5-72b-instruct", "label": "Qwen 2.5 72B", "default": False},
            {"id": "minimax/minimax-01", "label": "MiniMax Text-01", "default": False},
            {"id": "minimax/minimax-m3:free", "label": "MiniMax M3 Free", "default": False},
            {"id": "nvidia/nemotron-3-ultra-550b-a55b:free", "label": "Nemotron 3 Ultra Free", "default": False},
            {"id": "deepseek/deepseek-v4-flash:free", "label": "DeepSeek V4 Flash Free", "default": False},
        ]

    def _normalize_model_name(self, model: str) -> str:
        clean = (model or "").strip().lower()
        if not clean:
            return self.default_model
        if clean in ("minimax m3 free", "minimax/minimax-m3:free"):
            return "minimax/minimax-m3:free"
        if clean in _MINIMAX_M3_ALIASES:
            return self.default_model if "m3" in self.default_model.lower() else DEFAULT_FALLBACK_MODEL
        if clean in ("minimax-01", "text-01", "minimax/minimax-01", "minimax text-01"):
            return "minimax/minimax-01"
        return model

    # ------------------------------------------------------------------
    def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        api_keys: Optional[Dict[str, str]] = None,
        cancel_token: Optional[Any] = None,
    ) -> Dict[str, Any]:
        if cancel_token and cancel_token.is_cancelled():
            raise LLMOperationCancelled("OpenRouter LLM call cancelled before execution.")

        self.reload_keys()
        leases = [(lease.key_id, lease.secret, True) for lease in self.pool.candidates()]
        user_key = ((api_keys or {}).get("openrouter") or "").strip()
        if user_key:
            leases.insert(0, ("openrouter#user", user_key, False))
        if not leases:
            raise LLMProviderError(
                "No OpenRouter API keys configured. Set OPENROUTER_API_KEY_1..5 in .env.",
                provider="OpenRouter", kind=FailureKind.AUTH,
            )

        target_model = self._normalize_model_name(model)
        last: Optional[LLMProviderError] = None

        for key_id, secret, pooled in leases:
            if cancel_token and cancel_token.is_cancelled():
                raise LLMOperationCancelled("OpenRouter LLM call cancelled.")
            t0 = time.time()
            logger.info(f"OpenRouter request → {key_id} | model {target_model}")
            try:
                result = self._post(secret, target_model, messages, temperature, max_tokens, cancel_token)
            except LLMOperationCancelled:
                raise
            except LLMProviderError as err:
                last = err
            except Exception as exc:  # network errors, malformed bodies
                if cancel_token and cancel_token.is_cancelled():
                    raise LLMOperationCancelled("OpenRouter LLM call stopped by user.")
                kind, retry_after = classify(None, str(exc))
                last = LLMProviderError(f"OpenRouter request failed: {exc}", provider="OpenRouter",
                                        kind=kind, retry_after=retry_after)
            else:
                if pooled:
                    self.pool.report_success(key_id)
                duration = round((time.time() - t0) * 1000, 1)
                logger.info(f"OpenRouter OK ({duration}ms) {key_id} tokens={result['usage'].get('total_tokens', 'n/a')}")
                result["key_id"] = key_id
                return result

            cooldown = self.pool.report_failure(key_id, last.kind, last.retry_after) if pooled else 0.0
            logger.warning(f"OpenRouter {key_id} failed ({last.kind.value}, HTTP {last.status_code}); "
                           f"cooldown {cooldown:.0f}s")
            if last.kind not in KEY_ROTATION_KINDS:
                break  # a bad request or a missing model fails the same way on every key

        assert last is not None
        raise LLMProviderError(
            f"OpenRouter failed on {len(leases)} key(s). Last error: {last}",
            status_code=last.status_code, provider="OpenRouter", kind=last.kind, retry_after=last.retry_after,
        )

    def _post(self, secret: str, model: str, messages: List[Dict[str, Any]], temperature: float,
              max_tokens: int, cancel_token: Optional[Any]) -> Dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {secret}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://overbranch.com",
            "X-Title": "OverBranch IDE",
        }
        payload = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        resp = requests.post(OPENROUTER_API_BASE, headers=headers, json=payload, stream=True, timeout=self.timeout)
        if cancel_token:
            cancel_token.register_resource(resp)
        try:
            body = self._read_body(resp, cancel_token)
        finally:
            if cancel_token:
                cancel_token.unregister_resource(resp)

        text = body.decode("utf-8", errors="replace")
        if resp.status_code != 200:
            retry_header = None
            try:
                retry_header = float(resp.headers.get("Retry-After")) if resp.headers.get("Retry-After") else None
            except (TypeError, ValueError, AttributeError):
                retry_header = None
            kind, retry_after = classify(resp.status_code, text)
            raise LLMProviderError(f"HTTP {resp.status_code}: {text[:160]}", status_code=resp.status_code,
                                   provider="OpenRouter", kind=kind, retry_after=retry_header or retry_after)

        data: Dict[str, Any] = {}
        try:
            data = json.loads(text) if text else {}
        except ValueError:
            if hasattr(resp, "json") and callable(resp.json):
                try:
                    data = resp.json()
                except Exception:
                    data = {}
        if not isinstance(data, dict):
            data = {}
        if data.get("error"):
            err = data["error"]
            msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            code = err.get("code") if isinstance(err, dict) and isinstance(err.get("code"), int) else None
            kind, retry_after = classify(code, msg)
            raise LLMProviderError(f"OpenRouter error: {msg[:160]}", status_code=code, provider="OpenRouter",
                                   kind=kind, retry_after=retry_after)
        choices = data.get("choices") or []
        if not choices:
            raise LLMProviderError("No choices returned from OpenRouter API", provider="OpenRouter",
                                   kind=FailureKind.UNAVAILABLE)
        content = choices[0].get("message", {}).get("content", "") or ""
        if not content.strip():
            raise LLMProviderError("OpenRouter returned an empty response", provider="OpenRouter",
                                   kind=FailureKind.UNAVAILABLE)
        return {
            "content": content,
            "model_used": data.get("model", model),
            "finish_reason": choices[0].get("finish_reason", "unknown"),
            "usage": data.get("usage", {}) or {},
            "is_fallback": False,
            "provider_name": "OpenRouter",
        }

    @staticmethod
    def _read_body(resp: Any, cancel_token: Optional[Any]) -> bytes:
        if cancel_token and cancel_token.is_cancelled():
            resp.close()
            raise LLMOperationCancelled("OpenRouter LLM call aborted by user.")
        chunks: List[bytes] = []
        if hasattr(resp, "iter_content") and callable(resp.iter_content):
            try:
                for chunk in resp.iter_content(chunk_size=4096):
                    if cancel_token and cancel_token.is_cancelled():
                        resp.close()
                        raise LLMOperationCancelled("OpenRouter LLM call aborted by user.")
                    if chunk and isinstance(chunk, (bytes, bytearray)):
                        chunks.append(bytes(chunk))
            except LLMOperationCancelled:
                raise
            except Exception:
                pass
        if chunks:
            return b"".join(chunks)
        if isinstance(getattr(resp, "text", None), str):
            return resp.text.encode("utf-8")
        if isinstance(getattr(resp, "content", None), (bytes, bytearray)):
            return bytes(resp.content)
        return b""
