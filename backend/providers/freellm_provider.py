
import os
import time
import logging
import requests
from typing import List, Dict, Any, Optional

from .base_provider import LLMProvider, LLMProviderError

logger = logging.getLogger("freellm_provider")

DEFAULT_FREELLM_MODEL = "auto:smart"


class FreeLLMProvider(LLMProvider):

    def __init__(self):
        base_url_env = (os.getenv("FREELLM_BASE_URL") or "").rstrip("/")
        if not base_url_env:
            self.base_url = ""
            self.chat_url = ""
        elif not base_url_env.endswith("/v1"):
            self.base_url = base_url_env
            self.chat_url = f"{base_url_env}/v1/chat/completions"
        else:
            self.base_url = base_url_env
            self.chat_url = f"{base_url_env}/chat/completions"
            
        self.default_model = os.getenv("FREELLM_MODEL") or DEFAULT_FREELLM_MODEL
        self._build_candidates()

    def _build_candidates(self):
        """Builds ordered list of candidate credentials starting with self-hosted FreeLLM API."""
        self.candidates = []

        # 1. Primary: Self-Hosted FreeLLM API (read exclusively from env)
        freellm_key = os.getenv("FREELLM_API_KEY")
        if freellm_key and freellm_key.strip() and self.chat_url:
            self.candidates.append({
                "name": "FreeLLM API Router",
                "key": freellm_key.strip(),
                "url": self.chat_url,
                "model": self.default_model,
            })

        # 2. Fallbacks: Groq API Keys
        groq_keys = [
            ("GROQ_API_KEY", "Groq Primary Fallback"),
            ("GROQ_API_KEY_2", "Groq API 2 Fallback"),
            ("GROQ_API_KEY_3", "Groq API 3 Fallback"),
        ]
        for env_var, label in groq_keys:
            key = os.getenv(env_var)
            if key and key.strip():
                self.candidates.append({
                    "name": label,
                    "key": key.strip(),
                    "url": "https://api.groq.com/openai/v1/chat/completions",
                    "model": os.getenv("GROQ_LLM_MODEL", "openai/gpt-oss-120b"),
                })

    def get_provider_name(self) -> str:
        return "FreeLLM API"

    def get_available_models(self) -> List[Dict[str, Any]]:
        return [
            {"id": "auto:smart", "label": "FreeLLM Auto Smart", "default": True},
            {"id": "auto", "label": "FreeLLM Auto Router", "default": False},
            {"id": "auto:fast", "label": "FreeLLM Auto Fast", "default": False},
            {"id": "openai/gpt-oss-120b", "label": "GPT-OSS-120B", "default": False},
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
                "No FreeLLM or Groq API keys configured.",
                provider="FreeLLM",
            )

        raw_target = model.strip() if model and model.strip() else self.default_model
        if " (via " in raw_target:
            raw_target = raw_target.split(" (via ", 1)[0].strip()
        if raw_target.lower().startswith("via "):
            raw_target = self.default_model
        target_model = raw_target if raw_target else self.default_model

        last_error = None

        # Calculate approximate token count for dynamic token budgeting
        total_prompt_chars = sum(len(str(m.get("content", ""))) for m in messages)
        approx_tokens = total_prompt_chars // 4
        
        adjusted_max_tokens = max_tokens
        if approx_tokens > 4500:
            adjusted_max_tokens = min(max_tokens, 2048)
        if approx_tokens > 6500:
            adjusted_max_tokens = min(max_tokens, 1500)

        for idx, creds in enumerate(self.candidates):
            start_time = time.time()
            req_model = target_model if creds["name"] == "FreeLLM API Router" else creds["model"]
            logger.info(f"FreeLLM Provider → Key: {creds['name']} | Endpoint: {creds['url']} | Model: {req_model}")

            try:
                headers = {
                    "Authorization": f"Bearer {creds['key']}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": req_model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": adjusted_max_tokens,
                }

                resp = requests.post(creds["url"], headers=headers, json=payload, timeout=90)
                duration = round((time.time() - start_time) * 1000, 2)

                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if not choices:
                        logger.warning(f"{creds['name']} returned empty choices. Trying next fallback...")
                        last_error = f"{creds['name']} returned empty choices"
                        continue

                    content = choices[0].get("message", {}).get("content", "")
                    routed_via = resp.headers.get("x-routed-via") or resp.headers.get("X-Routed-Via")
                    actual_model = data.get("model", req_model)
                    if routed_via:
                        actual_model = f"{actual_model} (via {routed_via})"

                    usage = data.get("usage", {})
                    finish_reason = choices[0].get("finish_reason", "stop")

                    logger.info(
                        f"FreeLLM Response OK | Key: {creds['name']} | Model: {actual_model} | "
                        f"Routed-Via: {routed_via or 'N/A'} | Duration: {duration}ms"
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
                        f"{resp.text[:200]} | Duration: {duration}ms. Trying next fallback..."
                    )
                    last_error = f"{creds['name']} HTTP {resp.status_code}: {resp.text[:100]}"

            except requests.Timeout:
                duration = round((time.time() - start_time) * 1000, 2)
                logger.warning(f"{creds['name']} timed out after {duration}ms. Trying next fallback...")
                last_error = f"{creds['name']} timeout"
            except Exception as err:
                logger.warning(f"{creds['name']} call failed: {err}. Trying next fallback...")
                last_error = f"{creds['name']} error: {err}"

        raise LLMProviderError(
            f"All FreeLLM and fallback API keys exhausted. Last error: {last_error}",
            provider="FreeLLM",
        )
