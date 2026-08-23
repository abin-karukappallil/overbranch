"""
openrouter_provider.py — OpenRouter LLM Provider Abstraction

Provides a clean, OpenAI-compatible interface for calling OpenRouter.
All main agent requests route through this provider using openrouter/free.
"""

import os
import time
import json
import logging
import httpx
from typing import List, Dict, Any, Optional, Union

logger = logging.getLogger("openrouter_provider")


class OpenRouterError(Exception):
    """Base exception class for OpenRouter provider errors."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class OpenRouterProvider:
    """
    OpenRouter API Provider Abstraction.
    Communicates with OpenRouter chat completions endpoint (https://openrouter.ai/api/v1/chat/completions).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        default_model: Optional[str] = None,
        timeout: float = 120.0,
    ):
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.base_url = (base_url or os.getenv("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1").rstrip("/")
        self.default_model = default_model or os.getenv("OPENROUTER_MODEL") or "openrouter/free"
        self.timeout = timeout

    def _get_headers(self) -> Dict[str, str]:
        if not self.api_key or not self.api_key.strip():
            raise OpenRouterError(
                "OPENROUTER_API_KEY is not configured in backend environment (.env). "
                "Please set OPENROUTER_API_KEY to enable OpenRouter AI agent capability."
            )
        return {
            "Authorization": f"Bearer {self.api_key.strip()}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://overbranch.dev",
            "X-Title": "OverBranch TeX Engine",
        }

    def generate_chat_completion(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 6144,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Sends a non-streaming chat completion request to OpenRouter.
        Returns a dict containing 'content', 'model_used', 'finish_reason', and 'usage'.
        """
        target_model = model or self.default_model
        endpoint = f"{self.base_url}/chat/completions"
        headers = self._get_headers()

        payload: Dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools

        start_time = time.time()
        logger.info(f"OpenRouter Request → Provider: openrouter | Model: {target_model} | Base URL: {self.base_url}")

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(endpoint, headers=headers, json=payload)
                duration = round((time.time() - start_time) * 1000, 2)

                if response.status_code == 401:
                    logger.error(f"OpenRouter 401 Unauthorized | Duration: {duration}ms")
                    raise OpenRouterError(
                        "OpenRouter authentication failed (HTTP 401). Please verify your OPENROUTER_API_KEY in .env.",
                        status_code=401,
                    )
                elif response.status_code == 402:
                    logger.error(f"OpenRouter 402 Payment Required | Duration: {duration}ms")
                    raise OpenRouterError(
                        "OpenRouter account requires credits or payment for the requested operation (HTTP 402).",
                        status_code=402,
                    )
                elif response.status_code == 429:
                    logger.error(f"OpenRouter 429 Rate Limit | Duration: {duration}ms")
                    raise OpenRouterError(
                        "OpenRouter rate limit exceeded (HTTP 429). Please wait a moment and try again.",
                        status_code=429,
                    )
                elif response.status_code in (500, 502, 503, 504):
                    logger.error(f"OpenRouter HTTP {response.status_code} Server Error | Duration: {duration}ms")
                    raise OpenRouterError(
                        f"OpenRouter service unavailable (HTTP {response.status_code}). Please try again later.",
                        status_code=response.status_code,
                    )
                elif response.status_code != 200:
                    err_msg = response.text[:300]
                    logger.error(f"OpenRouter HTTP {response.status_code} Error: {err_msg} | Duration: {duration}ms")
                    raise OpenRouterError(
                        f"OpenRouter returned HTTP {response.status_code}: {err_msg}",
                        status_code=response.status_code,
                    )

                data = response.json()
                choices = data.get("choices", [])
                if not choices:
                    raise OpenRouterError("OpenRouter returned an empty choices payload in response.")

                first_choice = choices[0]
                message = first_choice.get("message", {})
                content = message.get("content", "")
                finish_reason = first_choice.get("finish_reason", "stop")
                actual_model = data.get("model", target_model)
                usage = data.get("usage", {})

                logger.info(
                    f"OpenRouter Response Success | Model Used: {actual_model} | "
                    f"Duration: {duration}ms | Finish: {finish_reason} | "
                    f"Prompt Tokens: {usage.get('prompt_tokens', 'N/A')} | "
                    f"Completion Tokens: {usage.get('completion_tokens', 'N/A')}"
                )

                return {
                    "content": content or "",
                    "model_used": actual_model,
                    "finish_reason": finish_reason,
                    "usage": usage,
                    "tool_calls": message.get("tool_calls", None),
                }

        except httpx.TimeoutException:
            duration = round((time.time() - start_time) * 1000, 2)
            logger.error(f"OpenRouter Request Timeout after {duration}ms")
            raise OpenRouterError(f"OpenRouter request timed out after {self.timeout} seconds.", status_code=504)
        except httpx.RequestError as req_err:
            duration = round((time.time() - start_time) * 1000, 2)
            logger.error(f"OpenRouter Network Connection Error: {str(req_err)} | Duration: {duration}ms")
            raise OpenRouterError(f"Network error connecting to OpenRouter ({self.base_url}): {str(req_err)}")
        except OpenRouterError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error in OpenRouter provider: {str(e)}", exc_info=True)
            raise OpenRouterError(f"Unexpected OpenRouter error: {str(e)}")
