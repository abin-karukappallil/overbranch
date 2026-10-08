from pathlib import Path
from dotenv import load_dotenv

# Ensure .env is loaded from workspace root and backend directory
_root_env = Path(__file__).resolve().parent.parent.parent / ".env"
_backend_env = Path(__file__).resolve().parent.parent / ".env"
if _root_env.exists():
    load_dotenv(dotenv_path=_root_env, override=False)
if _backend_env.exists():
    load_dotenv(dotenv_path=_backend_env, override=False)
load_dotenv(override=False)

from .base_provider import LLMProvider, LLMProviderError
from .groq_provider import GroqProvider
from .gemini_provider import GeminiProvider
from .openrouter_provider import OpenRouterProvider
from .router import ProviderRouter, provider_router
from cancellation import LLMOperationCancelled

__all__ = [
    "LLMProvider",
    "LLMProviderError",
    "LLMOperationCancelled",
    "GroqProvider",
    "GeminiProvider",
    "OpenRouterProvider",
    "ProviderRouter",
    "provider_router",
]
