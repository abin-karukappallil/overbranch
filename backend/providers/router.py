"""
router.py — Provider Router

Routes model names to the correct LLM provider instance.
Centralizes model→provider mapping so the agent layer
and API endpoints don't need provider-specific logic.
"""

import logging
from typing import Dict, Any, List, Optional

from .base_provider import LLMProvider, LLMProviderError
from .freellm_provider import FreeLLMProvider
from .groq_provider import GroqProvider
from .gemini_provider import GeminiProvider, ALLOWED_MODEL_IDS as GEMINI_MODEL_IDS
from .openrouter_provider import OpenRouterProvider

logger = logging.getLogger("provider_router")

DEFAULT_MODEL = "gemini-3.7-flash"


class ProviderRouter:
    """
    Routes model names to provider instances and provides
    the available models list for the frontend /api/models endpoint.
    """

    def __init__(self):
        self.freellm = FreeLLMProvider()
        self.groq = GroqProvider()
        self.gemini = GeminiProvider()
        self.openrouter = OpenRouterProvider()
        self._providers: Dict[str, LLMProvider] = {
            "freellm": self.freellm,
            "groq": self.groq,
            "gemini": self.gemini,
            "openrouter": self.openrouter,
        }

    def route(self, model: str) -> LLMProvider:
        """
        Determines which provider handles a given model name.

        Routing rules:
          - Default or 'gemini-*' → GeminiProvider (Pure Gemini Web2API at overapi.abinthomas.dev)
          - 'groq:*' or 'groq/*' → GroqProvider
          - Everything else ('auto', 'auto:smart', 'auto:fast', 'gpt-oss-*') → FreeLLMProvider
        """
        if not model:
            return self.gemini

        clean_model = model.strip().lower()

        # Pure Gemini Web2API provider
        if clean_model.startswith("gemini-") or clean_model in GEMINI_MODEL_IDS or "gemini" in clean_model:
            return self.gemini

        # Groq specific
        if clean_model.startswith("groq/") or clean_model.startswith("groq:"):
            return self.groq

        # OpenRouter specific
        if clean_model.startswith("nvidia/") or clean_model.startswith("minimax/") or clean_model.startswith("openrouter/"):
            return self.openrouter

        # FreeLLM Provider for all other models (has built-in Groq fallback)
        return self.freellm

    def get_default_model(self) -> str:
        """Returns the default model ID for new chats."""
        return DEFAULT_MODEL

    def get_available_models(self) -> Dict[str, Any]:
        """
        Returns the full model catalog grouped by provider,
        putting Gemini Web2API first as the default provider.
        """
        providers_list = []

        # 1. Gemini Web2API FIRST (Default provider)
        gemini_models = self.gemini.get_available_models()
        if gemini_models:
            providers_list.append({
                "name": "Gemini Web2API",
                "models": gemini_models,
            })

        # 2. FreeLLM API second
        freellm_models = self.freellm.get_available_models()
        if freellm_models:
            providers_list.append({
                "name": self.freellm.get_provider_name(),
                "models": freellm_models,
            })

        # 3. OpenRouter API third
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
        """
        Convenience method: routes to the correct provider and calls chat().
        """
        provider = self.route(model)
        logger.info(f"Routing model '{model}' → {provider.get_provider_name()}")
        return provider.chat(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            api_keys=api_keys,
        )


# Singleton instance — import this in agent.py
provider_router = ProviderRouter()
