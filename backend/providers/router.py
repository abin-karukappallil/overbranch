"""
router.py — Provider Router by Task Type

Routes tasks and model names to the appropriate LLM provider:
  - Task classification (§2.1) → Fast tier (Groq GPT-OSS-120B / Gemini 3.7 Flash)
  - Query rewriting → Fast tier
  - Node-scoped editing → Mid-size strong instruction following (Gemini 3.7 Flash)
  - Document-wide restructuring → Strongest available reasoning (Gemini 3.7 Flash / MiniMax-M3)
  - PDF section synthesis → Strong long-context tier
  - Fidelity-diff vision check → Vision-capable tier (Gemini / MiniMax-M3)

Includes JSON schema validation and reject-retry-fail-loud error handling.
"""

from __future__ import annotations

import json
import logging
import re
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple, Callable

from .base_provider import LLMProvider, LLMProviderError
from .groq_provider import GroqProvider
from .gemini_provider import GeminiProvider, ALLOWED_MODEL_IDS as GEMINI_MODEL_IDS
from .openrouter_provider import OpenRouterProvider

logger = logging.getLogger("provider_router")

DEFAULT_MODEL = "gemini-3.7-flash"


class TaskType(str, Enum):
    TASK_CLASSIFICATION = "task_classification"
    QUERY_REWRITING = "query_rewriting"
    NODE_EDITING = "node_editing"
    DOC_RESTRUCTURING = "doc_restructuring"
    PDF_SYNTHESIS = "pdf_synthesis"
    VISION_DIFF = "vision_diff"


# Task type to recommended model class mapping
TASK_ROUTING_TABLE: Dict[TaskType, str] = {
    TaskType.TASK_CLASSIFICATION: "openai/gpt-oss-120b",
    TaskType.QUERY_REWRITING: "openai/gpt-oss-120b",
    TaskType.NODE_EDITING: "gemini-3.7-flash",
    TaskType.DOC_RESTRUCTURING: "gemini-3.7-flash",
    TaskType.PDF_SYNTHESIS: "gemini-3.7-flash",
    TaskType.VISION_DIFF: "minimax/minimax-01",
}


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
        self.openrouter = OpenRouterProvider()
        self._providers: Dict[str, LLMProvider] = {
            "groq": self.groq,
            "gemini": self.gemini,
            "openrouter": self.openrouter,
        }

    def route(self, model: str) -> LLMProvider:
        """Determines which provider handles a given model name."""
        if not model:
            return self.gemini

        clean_model = model.strip().lower()

        if clean_model.startswith("gemini-") or clean_model in GEMINI_MODEL_IDS or "gemini" in clean_model:
            return self.gemini

        if clean_model.startswith("groq/") or clean_model.startswith("groq:") or "gpt-oss-120b" in clean_model:
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
        return "minimax/minimax-01"

    def get_fast_model(self) -> str:
        return "openai/gpt-oss-120b"

    def get_strong_model(self) -> str:
        return DEFAULT_MODEL

    def get_available_models(self) -> Dict[str, Any]:
        providers_list = []

        gemini_models = self.gemini.get_available_models()
        if gemini_models:
            providers_list.append({
                "name": "Gemini Web2API",
                "models": gemini_models,
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

    def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        api_keys: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        provider = self.route(model)
        logger.info(f"Routing model '{model}' → {provider.get_provider_name()}")
        return provider.chat(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            api_keys=api_keys,
        )

    def chat_fast_tier(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.1,
        max_tokens: int = 2048,
        api_keys: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        try:
            return self.groq.chat(
                messages=messages,
                model="openai/gpt-oss-120b",
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
