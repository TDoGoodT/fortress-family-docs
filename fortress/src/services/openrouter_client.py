"""Fortress 2.0 OpenRouter client — async OpenRouter API communication."""

import logging
import time

import httpx

from src.config import OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_FALLBACK_MODEL

logger = logging.getLogger(__name__)

HEBREW_FALLBACK: str = "מצטער, לא הצלחתי לעבד את הבקשה. נסה שוב."

BASE_URL: str = "https://openrouter.ai/api/v1"


class OpenRouterClient:
    """Async client for OpenRouter API (OpenAI-compatible)."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        fallback_model: str | None = None,
    ) -> None:
        self.api_key: str = api_key if api_key is not None else OPENROUTER_API_KEY
        self.model: str = model or OPENROUTER_MODEL
        self.fallback_model: str = fallback_model or OPENROUTER_FALLBACK_MODEL

    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        model: str | None = None,
    ) -> str:
        """Send chat completion request to OpenRouter.

        Returns response text or HEBREW_FALLBACK on any error.
        """
        if not self.api_key:
            return HEBREW_FALLBACK

        chosen_model = model or self.model
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://fortress.local",
            "X-Title": "Fortress",
        }
        payload = {
            "model": chosen_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
        }

        start = time.monotonic()
        try:
            logger.info(
                "OpenRouter request: model=%s | prompt_len=%d",
                chosen_model, len(prompt),
            )
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{BASE_URL}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                result = data["choices"][0]["message"]["content"]
                elapsed = time.monotonic() - start
                logger.info(
                    "OpenRouter response: len=%d | time=%.1fs",
                    len(result), elapsed,
                )
                return result
        except httpx.TimeoutException:
            elapsed = time.monotonic() - start
            logger.error(
                "OpenRouter request timed out after 30s: model=%s time=%.1fs",
                chosen_model, elapsed,
            )
            return HEBREW_FALLBACK
        except httpx.ConnectError:
            elapsed = time.monotonic() - start
            logger.error(
                "OpenRouter connection error: model=%s time=%.1fs",
                chosen_model, elapsed,
            )
            return HEBREW_FALLBACK
        except httpx.HTTPStatusError as exc:
            elapsed = time.monotonic() - start
            logger.error(
                "OpenRouter HTTP error: status=%s model=%s time=%.1fs",
                exc.response.status_code, chosen_model, elapsed,
            )
            return HEBREW_FALLBACK
        except Exception as exc:
            elapsed = time.monotonic() - start
            logger.error(
                "OpenRouter unexpected error: %s: %s model=%s time=%.1fs",
                type(exc).__name__, exc, chosen_model, elapsed,
            )
            return HEBREW_FALLBACK

    async def is_available(self) -> tuple[bool, str | None]:
        """Check if OpenRouter is reachable and API key is configured.

        Returns (True, model_name) on success, (False, None) on failure.
        Returns (False, None) immediately if no API key is set.
        """
        if not self.api_key:
            return False, None

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{BASE_URL}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                response.raise_for_status()
                return True, self.model
        except Exception as exc:
            logger.error(
                "OpenRouter availability check failed: %s: %s",
                type(exc).__name__, exc,
            )
            return False, None
