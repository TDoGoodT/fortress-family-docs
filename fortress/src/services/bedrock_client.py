"""Fortress Bedrock client — AWS Bedrock Converse API via API key auth."""

import logging
import time
from typing import Optional, Tuple

import httpx

from src.config import (
    BEDROCK_API_KEY,
    BEDROCK_API_BASE_URL,
    BEDROCK_MICRO_MODEL,
    BEDROCK_LITE_MODEL,
    BEDROCK_HAIKU_MODEL,
    BEDROCK_SONNET_MODEL,
)

logger = logging.getLogger(__name__)

HEBREW_FALLBACK: str = "מצטער, לא הצלחתי לעבד את הבקשה. נסה שוב."

# Model selector → actual model ID (cheapest first)
MODEL_MAP: dict = {
    "micro": BEDROCK_MICRO_MODEL,    # intent detection, classification
    "lite": BEDROCK_LITE_MODEL,      # everyday chat, Hebrew responses
    "haiku": BEDROCK_HAIKU_MODEL,    # complex Hebrew, memory extraction
    "sonnet": BEDROCK_SONNET_MODEL,  # reasoning, code, deep analysis
}


class BedrockClient:
    """Async client for AWS Bedrock Converse API using API key auth."""

    def __init__(self) -> None:
        self._base_url = BEDROCK_API_BASE_URL.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {BEDROCK_API_KEY}",
            "Content-Type": "application/json",
        }

    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        model: str = "lite",
    ) -> str:
        """Generate a response using the Bedrock Converse API.

        model: "micro" | "lite" | "haiku" | "sonnet"
        Returns HEBREW_FALLBACK on any error.
        """
        model_id = MODEL_MAP.get(model, BEDROCK_LITE_MODEL)
        payload: dict = {
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": {"maxTokens": 1024},
        }
        if system_prompt:
            payload["system"] = [{"text": system_prompt}]

        url = f"{self._base_url}/model/{model_id}/converse"
        start = time.monotonic()
        try:
            logger.info("Bedrock request: model=%s prompt_len=%d", model_id, len(prompt))
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, headers=self._headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                result = data["output"]["message"]["content"][0]["text"]
                elapsed = time.monotonic() - start
                logger.info("Bedrock response: len=%d time=%.1fs", len(result), elapsed)
                return result
        except httpx.HTTPStatusError as exc:
            elapsed = time.monotonic() - start
            logger.error("Bedrock HTTP error: status=%s model=%s time=%.1fs body=%s",
                         exc.response.status_code, model_id, elapsed, exc.response.text[:200])
            return HEBREW_FALLBACK
        except Exception:
            elapsed = time.monotonic() - start
            logger.exception("Bedrock unexpected error: model=%s time=%.1fs", model_id, elapsed)
            return HEBREW_FALLBACK

    async def is_available(self) -> Tuple[bool, Optional[str]]:
        """Check connectivity with a minimal request.

        Returns (True, "lite") on success, (False, None) on failure.
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self._base_url}/model/{BEDROCK_LITE_MODEL}/converse",
                    headers=self._headers,
                    json={
                        "messages": [{"role": "user", "content": [{"text": "hi"}]}],
                        "inferenceConfig": {"maxTokens": 5},
                    },
                )
                if resp.status_code == 200:
                    logger.info("Bedrock available: model=%s", BEDROCK_LITE_MODEL)
                    return True, "lite"
                logger.warning("Bedrock check failed: status=%s", resp.status_code)
                return False, None
        except Exception as exc:
            logger.error("Bedrock availability check failed: %s: %s", type(exc).__name__, exc)
            return False, None
