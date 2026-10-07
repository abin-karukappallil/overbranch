"""
base_provider.py — Abstract LLM Provider Interface

All LLM providers (Groq, Gemini, etc.) implement this interface
to ensure a unified chat completion contract across the backend.
"""

import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

logger = logging.getLogger("llm_provider")


class LLMProviderError(Exception):
    """
    Base exception for all LLM provider errors.

    ``kind`` (a providers.errors.FailureKind) decides whether the ProviderRouter
    may fall back to another provider; it is derived from ``status_code`` and the
    message when the raiser does not set it.
    """
    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        provider: str = "unknown",
        kind: Optional[Any] = None,
        retry_after: Optional[float] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.provider = provider
        if kind is None:
            from .errors import classify
            kind, parsed_retry = classify(status_code, message)
            retry_after = retry_after if retry_after is not None else parsed_retry
        self.kind = kind
        self.retry_after = retry_after


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.

    Every provider must implement `chat()` returning a standardized dict:
    {
        "content": str,          # The generated text
        "model_used": str,       # Actual model that responded
        "finish_reason": str,    # "stop", "length", etc.
        "usage": dict,           # Token usage stats
        "is_fallback": bool,     # Whether a fallback key/model was used
    }
    """

    @abstractmethod
    def get_provider_name(self) -> str:
        """Returns a human-readable provider name (e.g. 'Groq', 'Gemini')."""
        ...

    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        api_keys: Optional[Dict[str, str]] = None,
        cancel_token: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Sends a chat completion request and returns a standardized response dict.

        Args:
            messages: OpenAI-format messages list [{"role": ..., "content": ...}]
            model: Model identifier string
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate

        Returns:
            Dict with keys: content, model_used, finish_reason, usage, is_fallback
        """
        ...

    @abstractmethod
    def get_available_models(self) -> List[Dict[str, Any]]:
        """
        Returns a list of model descriptors available from this provider.
        Each item: {"id": "model-id", "label": "Display Name", "default": bool}
        """
        ...
