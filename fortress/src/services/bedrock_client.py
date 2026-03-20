"""Fortress 2.0 Bedrock client — async AWS Bedrock runtime communication."""

import asyncio
import json
import logging
import time
from typing import Any

import boto3
from botocore.config import Config as BotoConfig

from src.config import (
    AWS_PROFILE,
    AWS_REGION,
    BEDROCK_HAIKU_MODEL,
    BEDROCK_SONNET_MODEL,
)

logger = logging.getLogger(__name__)

HEBREW_FALLBACK: str = "מצטער, לא הצלחתי לעבד את הבקשה. נסה שוב."

MODEL_MAP: dict[str, str] = {
    "haiku": BEDROCK_HAIKU_MODEL,
    "sonnet": BEDROCK_SONNET_MODEL,
}


class BedrockClient:
    """Async client for AWS Bedrock runtime (Claude models)."""

    def __init__(
        self,
        region: str | None = None,
        profile: str | None = None,
    ) -> None:
        self.region: str = region or AWS_REGION
        self.profile: str = profile or AWS_PROFILE
        session = boto3.Session(profile_name=self.profile)
        boto_config = BotoConfig(read_timeout=30, connect_timeout=5)
        self.client: Any = session.client(
            "bedrock-runtime",
            region_name=self.region,
            config=boto_config,
        )

    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        model: str = "haiku",
    ) -> str:
        """Invoke a Claude model on Bedrock and return the response text.

        Returns a Hebrew fallback message on any error.
        """
        model_id = MODEL_MAP.get(model, BEDROCK_HAIKU_MODEL)
        body: dict[str, Any] = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            body["system"] = system_prompt

        try:
            logger.info("Bedrock request: model=%s | prompt_len=%d", model_id, len(prompt))
            start = time.monotonic()
            response = await asyncio.to_thread(
                self.client.invoke_model,
                modelId=model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(body),
            )
            response_body = json.loads(response["body"].read())
            result = response_body["content"][0]["text"]
            elapsed = time.monotonic() - start
            logger.info("Bedrock response: len=%d | time=%.1fs", len(result), elapsed)
            return result
        except Exception as exc:
            logger.error("Bedrock error: %s: %s", type(exc).__name__, exc)
            return HEBREW_FALLBACK

    async def is_available(self) -> tuple[bool, str | None]:
        """Check if Bedrock is reachable.

        Returns (True, "haiku") on success, (False, None) on failure.
        """
        try:
            session = boto3.Session(profile_name=self.profile)
            bedrock = session.client("bedrock", region_name=self.region)
            await asyncio.to_thread(
                bedrock.list_foundation_models,
                byProvider="Anthropic",
                maxResults=1,
            )
            return True, "haiku"
        except Exception:
            logger.exception("Bedrock availability check failed")
            return False, None
