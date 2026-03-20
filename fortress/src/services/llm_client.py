"""Fortress 2.0 LLM client — async Ollama REST API communication."""

import logging
import time

import httpx

from src.config import OLLAMA_API_URL, OLLAMA_MODEL

logger = logging.getLogger(__name__)

HEBREW_FALLBACK: str = "מצטער, לא הצלחתי לעבד את הבקשה. נסה שוב."


class OllamaClient:
    """Async client for Ollama REST API communication."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self.base_url: str = base_url or OLLAMA_API_URL
        self.model: str = model or OLLAMA_MODEL

    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
    ) -> str:
        """Send a generation request to Ollama and return the response text.

        Returns a Hebrew fallback message on any error.
        """
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system_prompt,
            "stream": False,
        }
        try:
            logger.info("Ollama request: model=%s | prompt_len=%d", self.model, len(prompt))
            start = time.monotonic()
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                result = data.get("response", HEBREW_FALLBACK)
                elapsed = time.monotonic() - start
                logger.info("Ollama response: len=%d | time=%.1fs", len(result), elapsed)
                return result
        except httpx.TimeoutException:
            logger.error("Ollama request timed out after 30s: %s", self.base_url)
            return HEBREW_FALLBACK
        except httpx.ConnectError:
            logger.error("Ollama error: ConnectError: cannot connect to %s", self.base_url)
            return HEBREW_FALLBACK
        except httpx.HTTPStatusError as exc:
            logger.error("Ollama error: HTTPStatusError: %s %s", exc.response.status_code, exc)
            return HEBREW_FALLBACK
        except Exception as e:
            logger.error("Ollama error: %s: %s", type(e).__name__, e)
            return HEBREW_FALLBACK

    async def is_available(self) -> tuple[bool, str | None]:
        """Check if Ollama is reachable and the configured model is loaded.

        Returns (True, model_name) or (False, None).
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                data = response.json()
                models = data.get("models", [])
                for m in models:
                    name = m.get("name", "")
                    if self.model in name:
                        return True, name
                return False, None
        except Exception:
            logger.exception("Ollama availability check failed")
            return False, None
