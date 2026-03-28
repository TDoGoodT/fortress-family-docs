from __future__ import annotations
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
        messages = []
        if system_prompt.strip():
            merged_prompt = f"{system_prompt}\n\nUser request:\n{prompt}"
            messages.append({"role": "user", "content": merged_prompt})
        else:
            messages.append({"role": "user", "content": prompt})

        payload = {
            "model": chosen_model,
            "messages": messages,
            "max_tokens": 1024,
            "response_format": {"type": "json_object"},
        }

        start = time.monotonic()
        try:
            logger.info(
                "OpenRouter request: model=%s | prompt_len=%d | json_mode=True",
                chosen_model, len(prompt),
            )
            result = await self._send_request(headers, payload)
            elapsed = time.monotonic() - start
            logger.info(
                "OpenRouter response: len=%d | time=%.1fs",
                len(result), elapsed,
            )
            return result
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:500] if hasattr(exc.response, "text") else ""
            # Retry without response_format if model doesn't support it
            if exc.response.status_code == 400 and (
                "response_format" in body.lower() or "json" in body.lower()
            ):
                logger.warning(
                    "OpenRouter: model %s doesn't support json mode, retrying without response_format",
                    chosen_model,
                )
                payload.pop("response_format", None)
                try:
                    result = await self._send_request(headers, payload)
                    elapsed = time.monotonic() - start
                    logger.info(
                        "OpenRouter response (no json mode): len=%d | time=%.1fs",
                        len(result), elapsed,
                    )
                    return result
                except Exception as retry_exc:
                    elapsed = time.monotonic() - start
                    logger.error(
                        "OpenRouter retry failed: %s: %s model=%s time=%.1fs",
                        type(retry_exc).__name__, retry_exc, chosen_model, elapsed,
                    )
                    return HEBREW_FALLBACK
            elapsed = time.monotonic() - start
            logger.error(
                "OpenRouter HTTP error: status=%s model=%s time=%.1fs body=%s",
                exc.response.status_code, chosen_model, elapsed, body,
            )
            return HEBREW_FALLBACK
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
        except Exception as exc:
            elapsed = time.monotonic() - start
            logger.error(
                "OpenRouter unexpected error: %s: %s model=%s time=%.1fs",
                type(exc).__name__, exc, chosen_model, elapsed,
            )
            return HEBREW_FALLBACK

    async def _send_request(self, headers: dict, payload: dict) -> str:
        """Send a single request to OpenRouter and return the content string.

        Raises httpx exceptions on failure (caller handles).
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]

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
