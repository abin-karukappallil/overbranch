import os
import time
import json
import logging
import requests
from typing import List, Dict, Any, Optional

from .base_provider import LLMProvider, LLMProviderError
from cancellation import LLMOperationCancelled

logger = logging.getLogger("openrouter_provider")

OPENROUTER_API_BASE = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_FALLBACK_MODEL = "minimax/minimax-01"


class OpenRouterProvider(LLMProvider):
    """
    OpenRouter LLM Provider with 5-Key Server-Side Rotation.
    
    When a key encounters rate limits (HTTP 429) or quota errors (HTTP 402),
    it automatically switches to the next available server-side key.
    """

    def __init__(self):
        self.default_model = os.getenv("OPENROUTER_FALLBACK_MODEL", DEFAULT_FALLBACK_MODEL)
        self._active_key_index = 0
        self.candidates = self._load_server_keys()

    def _load_server_keys(self) -> List[Dict[str, str]]:
        """Loads up to 5 server-side OpenRouter keys from environment variables."""
        keys: List[Dict[str, str]] = []
        seen_keys = set()

        # Check numbered keys 1 through 5
        for i in range(1, 6):
            env_vars = [
                f"OPENROUTER_API_KEY_{i}",
                f"OPENROUTER_{i}",
                f"OPENROUTER_KEY_{i}",
            ]
            for var in env_vars:
                val = os.getenv(var, "").strip()
                if val and val not in seen_keys:
                    keys.append({"name": f"OpenRouter Key {i}", "key": val})
                    seen_keys.add(val)
                    break

        # Check single or comma-separated keys
        general_keys = os.getenv("OPENROUTER_API_KEYS", "") or os.getenv("OPENROUTER_API_KEY", "")
        if general_keys and len(keys) < 5:
            for piece in general_keys.split(","):
                k = piece.strip()
                if k and k not in seen_keys:
                    idx = len(keys) + 1
                    keys.append({"name": f"OpenRouter Key {idx}", "key": k})
                    seen_keys.add(k)
                    if len(keys) >= 5:
                        break

        logger.info(f"OpenRouter provider initialized with {len(keys)} server-side key(s)")
        return keys

    def get_provider_name(self) -> str:
        return "OpenRouter"

    def get_available_models(self) -> List[Dict[str, Any]]:
        return [
            {"id": "meta-llama/llama-3.3-70b-instruct", "label": "Llama 3.3 70B (Fast)", "default": False},
            {"id": "openai/gpt-4o-mini", "label": "GPT-4o Mini (Fast)", "default": False},
            {"id": "qwen/qwen-2.5-72b-instruct", "label": "Qwen 2.5 72B", "default": False},
            {"id": "minimax/minimax-01", "label": "MiniMax M3 (Text-01)", "default": True},
            {"id": "minimax/minimax-m3:free", "label": "MiniMax 3 Free", "default": False},
            {"id": "nvidia/nemotron-3-ultra-550b-a55b:free", "label": "Nemotron 3 Ultra Free", "default": False},
            {"id": "deepseek/deepseek-v4-flash:free", "label": "DeepSeek V4 Flash Free", "default": False},
        ]

    def _normalize_model_name(self, model: str) -> str:
        clean = (model or "").strip().lower()
        if clean in ("minimax m3", "minimax-m3", "minimax", "minimax/minimax-m3"):
            return "minimax/minimax-01"
        return model or self.default_model

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

        runtime_candidates = []
        if api_keys and api_keys.get("openrouter"):
            user_k = api_keys["openrouter"].strip()
            if user_k:
                runtime_candidates.append({"name": "User OpenRouter API", "key": user_k})

        # Reload keys in case .env changed at runtime
        server_candidates = self._load_server_keys() or self.candidates
        all_candidates = runtime_candidates + server_candidates

        if not all_candidates:
            raise LLMProviderError(
                "No OpenRouter API keys configured. Set OPENROUTER_API_KEY_1..5 in .env.",
                provider="OpenRouter",
            )

        target_model = self._normalize_model_name(model)
        last_error = None
        total_keys = len(all_candidates)

        # Start from the currently active key index
        start_idx = self._active_key_index % total_keys
        ordered_candidates = all_candidates[start_idx:] + all_candidates[:start_idx]

        for attempt, creds in enumerate(ordered_candidates):
            if cancel_token and cancel_token.is_cancelled():
                raise LLMOperationCancelled("OpenRouter LLM call cancelled.")

            start_time = time.time()
            current_slot = (start_idx + attempt) % total_keys
            logger.info(f"OpenRouter Request → Key: {creds['name']} (slot {current_slot + 1}/{total_keys}) | Model: {target_model}")

            try:
                headers = {
                    "Authorization": f"Bearer {creds['key']}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://overbranch.com",
                    "X-Title": "OverBranch IDE",
                }
                payload = {
                    "model": target_model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }

                resp = requests.post(OPENROUTER_API_BASE, headers=headers, json=payload, stream=True, timeout=90)
                if cancel_token:
                    cancel_token.register_resource(resp)

                try:
                    if cancel_token and cancel_token.is_cancelled():
                        resp.close()
                        raise LLMOperationCancelled("OpenRouter LLM call aborted by user.")

                    body_bytes = b""
                    if hasattr(resp, "iter_content") and callable(resp.iter_content):
                        try:
                            raw_chunks = []
                            for chunk in resp.iter_content(chunk_size=4096):
                                if cancel_token and cancel_token.is_cancelled():
                                    resp.close()
                                    raise LLMOperationCancelled("OpenRouter LLM call aborted by user.")
                                if chunk and isinstance(chunk, (bytes, bytearray)):
                                    raw_chunks.append(chunk)
                            if raw_chunks:
                                body_bytes = b"".join(raw_chunks)
                        except LLMOperationCancelled:
                            raise
                        except Exception:
                            pass

                    if not body_bytes and hasattr(resp, "text") and isinstance(resp.text, str):
                        body_bytes = resp.text.encode("utf-8")
                    elif not body_bytes and hasattr(resp, "content") and isinstance(resp.content, (bytes, bytearray)):
                        body_bytes = resp.content
                finally:
                    if cancel_token:
                        cancel_token.unregister_resource(resp)

                duration = round((time.time() - start_time) * 1000, 2)

                if resp.status_code == 200:
                    data = None
                    if body_bytes:
                        try:
                            data = json.loads(body_bytes.decode("utf-8", errors="replace"))
                        except Exception:
                            pass
                    if not data and hasattr(resp, "json") and callable(resp.json):
                        try:
                            data = resp.json()
                        except Exception:
                            pass
                    if not data or not isinstance(data, dict):
                        data = {}
                    choices = data.get("choices", [])
                    if not choices:
                        raise ValueError("No choices returned from OpenRouter API")

                    generated_text = choices[0].get("message", {}).get("content", "")
                    finish_reason = choices[0].get("finish_reason", "unknown")
                    usage = data.get("usage", {})
                    actual_model_used = data.get("model", target_model)

                    # Update active key index to this successful key slot
                    self._active_key_index = current_slot

                    logger.info(f"OpenRouter Success ({duration}ms) with {creds['name']} — Tokens: {usage.get('total_tokens', 'N/A')}")
                    return {
                        "content": generated_text,
                        "model_used": actual_model_used,
                        "finish_reason": finish_reason,
                        "usage": usage,
                        "is_fallback": True,
                        "provider_name": "OpenRouter (MiniMax M3)",
                    }

                # Rate limit or quota error -> switch to next key immediately
                elif resp.status_code in (429, 402, 403, 503) or b"rate limit" in body_bytes.lower():
                    next_slot = (current_slot + 1) % total_keys
                    logger.warning(
                        f"OpenRouter {creds['name']} hit status {resp.status_code} (Rate Limit / Quota). "
                        f"Automatically switching to next key (slot {next_slot + 1})..."
                    )
                    self._active_key_index = next_slot
                    err_snippet = body_bytes.decode("utf-8", errors="replace")[:120]
                    last_error = f"HTTP {resp.status_code}: {err_snippet}"
                    continue

                else:
                    err_text = body_bytes.decode("utf-8", errors="replace")
                    logger.warning(f"OpenRouter returned {resp.status_code}: {err_text[:120]}")
                    last_error = f"HTTP {resp.status_code}: {err_text[:120]}"

            except LLMOperationCancelled:
                raise
            except Exception as e:
                if cancel_token and cancel_token.is_cancelled():
                    raise LLMOperationCancelled("OpenRouter LLM call stopped by user.")
                next_slot = (current_slot + 1) % total_keys
                logger.warning(f"OpenRouter exception on {creds['name']}: {e}. Switching to next key...")
                self._active_key_index = next_slot
                last_error = str(e)

        raise LLMProviderError(
            f"All {total_keys} OpenRouter keys failed. Last error: {last_error}",
            provider="OpenRouter",
        )
