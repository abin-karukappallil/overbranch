import os
import time
import logging
import requests
from typing import List, Dict, Any, Optional

from .base_provider import LLMProvider, LLMProviderError

logger = logging.getLogger("openrouter_provider")

OPENROUTER_API_BASE = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterProvider(LLMProvider):
    """
    OpenRouter LLM Provider.
    """

    def __init__(self):
        self.default_model = "nvidia/nemotron-3-ultra-550b-a55b:free"
        self.candidates = []
        key_vars = [
            ("OPENROUTER_API_KEY", "OpenRouter Primary API"),
        ]
        for env_var, label in key_vars:
            key = os.getenv(env_var)
            if key and key.strip():
                self.candidates.append({"name": label, "key": key.strip()})

    def get_provider_name(self) -> str:
        return "OpenRouter"

    def get_available_models(self) -> List[Dict[str, Any]]:
        return [
            {"id": "nvidia/nemotron-3-ultra-550b-a55b:free", "label": "Nemotron 3 Ultra Free", "default": True},
            {"id": "minimax/minimax-m3:free", "label": "Minimax 3 Free", "default": False},
            {"id": "deepseek/deepseek-v4-flash:free", "label": "DeepSeek V4 Flash Free", "default": False},
        ]

    def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        api_keys: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        runtime_candidates = []
        if api_keys and api_keys.get("openrouter"):
            runtime_candidates.append({"name": "User OpenRouter API", "key": api_keys["openrouter"].strip()})
        
        candidates = runtime_candidates + self.candidates

        if not candidates:
            raise LLMProviderError(
                "No OpenRouter API keys configured. Provide one in settings or set OPENROUTER_API_KEY in .env.",
                provider="OpenRouter",
            )

        target_model = model or self.default_model
        last_error = None
        adjusted_max_tokens = max_tokens

        for idx, creds in enumerate(candidates):
            start_time = time.time()
            logger.info(f"OpenRouter Request → Key: {creds['name']} | Model: {target_model}")

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
                    "max_tokens": adjusted_max_tokens,
                }

                resp = requests.post(OPENROUTER_API_BASE, headers=headers, json=payload, timeout=90)
                duration = round((time.time() - start_time) * 1000, 2)

                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if not choices:
                        raise ValueError("No choices returned from OpenRouter API")

                    generated_text = choices[0].get("message", {}).get("content", "")
                    finish_reason = choices[0].get("finish_reason", "unknown")
                    usage = data.get("usage", {})
                    
                    actual_model_used = data.get("model", target_model)

                    logger.info(f"OpenRouter Success ({duration}ms) — Tokens: {usage.get('total_tokens', 'N/A')}")
                    return {
                        "content": generated_text,
                        "model_used": actual_model_used,
                        "finish_reason": finish_reason,
                        "usage": usage,
                        "is_fallback": idx > 0,
                    }
                else:
                    err_text = resp.text
                    logger.warning(f"OpenRouter failed with {resp.status_code}: {err_text}")
                    last_error = f"HTTP {resp.status_code}: {err_text}"
            except Exception as e:
                logger.warning(f"OpenRouter Request exception on candidate {creds['name']}: {e}")
                last_error = str(e)

        raise LLMProviderError(
            f"All OpenRouter keys failed. Last error: {last_error}",
            provider="OpenRouter",
        )
