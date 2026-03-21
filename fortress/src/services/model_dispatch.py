"""Fortress 2.0 Model Dispatcher — unified dispatch with fallback chain."""

import logging
import time
from typing import Any

from src.config import OPENROUTER_API_KEY
from src.services.bedrock_client import BedrockClient
from src.services.bedrock_client import HEBREW_FALLBACK
from src.services.llm_client import OllamaClient
from src.services.openrouter_client import OpenRouterClient
from src.services.routing_policy import get_route, get_sensitivity

logger = logging.getLogger(__name__)


class ModelDispatcher:
    """Unified dispatch service that tries providers in routing order."""

    def __init__(
        self,
        bedrock_client: BedrockClient | None = None,
        openrouter_client: OpenRouterClient | None = None,
        ollama_client: OllamaClient | None = None,
    ) -> None:
        self.bedrock = bedrock_client or BedrockClient()
        self.openrouter = openrouter_client or OpenRouterClient()
        self.ollama = ollama_client or OllamaClient()

    async def dispatch(
        self,
        prompt: str,
        system_prompt: str,
        intent: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Try providers in routing order until one succeeds.

        Returns HEBREW_FALLBACK if all fail.
        """
        sensitivity = get_sensitivity(intent)
        route = get_route(intent)
        start = time.monotonic()

        for provider in route:
            try:
                result = await self._try_provider(provider, prompt, system_prompt, intent)
                if result != HEBREW_FALLBACK:
                    elapsed = time.monotonic() - start
                    logger.info(
                        "Dispatch: intent=%s sensitivity=%s provider=%s "
                        "fallback=False time=%.1fs",
                        intent, sensitivity, provider, elapsed,
                    )
                    return result
                logger.warning(
                    "Dispatch: intent=%s provider=%s returned fallback, trying next",
                    intent, provider,
                )
            except Exception as exc:
                logger.error(
                    "Dispatch: intent=%s provider=%s error=%s: %s",
                    intent, provider, type(exc).__name__, exc,
                )

        elapsed = time.monotonic() - start
        logger.error(
            "Dispatch: intent=%s sensitivity=%s all providers failed "
            "fallback=True time=%.1fs",
            intent, sensitivity, elapsed,
        )
        return HEBREW_FALLBACK

    async def _try_provider(
        self,
        provider: str,
        prompt: str,
        system_prompt: str,
        intent: str,
    ) -> str:
        """Attempt generation with a single provider."""
        if provider == "openrouter":
            if not OPENROUTER_API_KEY:
                logger.info("Dispatch: skipping openrouter (no API key)")
                return HEBREW_FALLBACK
            return await self.openrouter.generate(prompt, system_prompt)

        if provider == "bedrock":
            model = "sonnet" if intent == "ask_question" else "haiku"
            return await self.bedrock.generate(prompt, system_prompt, model=model)

        if provider == "ollama":
            return await self.ollama.generate(prompt, system_prompt)

        logger.error("Dispatch: unknown provider=%s", provider)
        return HEBREW_FALLBACK
