
import os
import time
import logging
import requests
from typing import List, Dict, Any, Optional

from .base_provider import LLMProvider, LLMProviderError

logger = logging.getLogger("groq_provider")

GROQ_API_BASE = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"


class GroqProvider(LLMProvider):
    """
    Groq API Provider with multi-key fallback.

    Iterates through configured API keys on failure (rate limits, server errors),
    providing automatic resilience without manual intervention.
    """

    def __init__(self):
        self.default_model = os.getenv("GROQ_LLM_MODEL") or DEFAULT_GROQ_MODEL
        self._build_key_candidates()

    def _build_key_candidates(self):
        """Builds the ordered list of API key candidates from environment."""
        self.candidates = []
        key_vars = [
            ("GROQ_API_KEY", "Groq Primary API"),
            ("GROQ_API_KEY_2", "Groq API 2"),
            ("GROQ_API_KEY_3", "Groq API 3"),
        ]
        for env_var, label in key_vars:
            key = os.getenv(env_var)
            if key and key.strip():
                self.candidates.append({"name": label, "key": key.strip()})

    def get_provider_name(self) -> str:
        return "Groq"

    def get_available_models(self) -> List[Dict[str, Any]]:
        return [
            {"id": "openai/gpt-oss-120b", "label": "GPT-OSS-120B", "default": True},
        ]

    def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> Dict[str, Any]:
        if not self.candidates:
            raise LLMProviderError(
                "No Groq API keys configured. Set GROQ_API_KEY in .env.",
                provider="Groq",
            )

        target_model = model or self.default_model
        last_error = None

        # Use full max_tokens (default 4096) to ensure complete presentations without truncation
        adjusted_max_tokens = max_tokens

        for idx, creds in enumerate(self.candidates):
            start_time = time.time()
            logger.info(f"Groq Request → Key: {creds['name']} | Model: {target_model} | Approx Tokens: {approx_tokens}")

            try:
                headers = {
                    "Authorization": f"Bearer {creds['key']}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": target_model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": adjusted_max_tokens,
                }

                resp = requests.post(GROQ_API_BASE, headers=headers, json=payload, timeout=90)
                duration = round((time.time() - start_time) * 1000, 2)

                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if not choices:
                        logger.warning(f"{creds['name']} returned empty choices. Trying next key...")
                        last_error = f"{creds['name']} returned empty choices"
                        continue

                    content = choices[0].get("message", {}).get("content", "")
                    actual_model = data.get("model", target_model)
                    usage = data.get("usage", {})
                    finish_reason = choices[0].get("finish_reason", "stop")

                    logger.info(
                        f"Groq Response OK | Key: {creds['name']} | Model: {actual_model} | "
                        f"Duration: {duration}ms | Tokens: {usage.get('completion_tokens', 'N/A')}"
                    )

                    return {
                        "content": content,
                        "model_used": actual_model,
                        "finish_reason": finish_reason,
                        "usage": usage,
                        "is_fallback": idx > 0,
                        "provider_name": creds["name"],
                    }
                else:
                    logger.warning(
                        f"{creds['name']} returned HTTP {resp.status_code}: "
                        f"{resp.text[:200]} | Duration: {duration}ms. Trying next key..."
                    )
                    last_error = f"{creds['name']} HTTP {resp.status_code}"

            except requests.Timeout:
                duration = round((time.time() - start_time) * 1000, 2)
                logger.warning(f"{creds['name']} timed out after {duration}ms. Trying next key...")
                last_error = f"{creds['name']} timeout"
            except Exception as err:
                logger.warning(f"{creds['name']} call failed: {err}. Trying next key...")
                last_error = f"{creds['name']} error: {err}"

        raise LLMProviderError(
            f"All Groq API keys exhausted. Last error: {last_error}",
            provider="Groq",
        )
