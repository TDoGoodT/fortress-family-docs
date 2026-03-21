"""Fortress 2.0 Bedrock client — async AWS Bedrock runtime communication."""

import asyncio
import json
import logging
import time
from typing import Any

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import (
    ClientError,
    EndpointConnectionError,
    NoCredentialsError,
    ReadTimeoutError,
)

from src.config import (
    AWS_REGION,
    BEDROCK_HAIKU_MODEL,
    BEDROCK_HAIKU_PROFILE_ARN,
    BEDROCK_SONNET_MODEL,
)

logger = logging.getLogger(__name__)

HEBREW_FALLBACK: str = "מצטער, לא הצלחתי לעבד את הבקשה. נסה שוב."

MODEL_MAP: dict[str, str] = {
    "haiku": BEDROCK_HAIKU_PROFILE_ARN or BEDROCK_HAIKU_MODEL,
    "sonnet": BEDROCK_SONNET_MODEL,
}


class BedrockClient:
    """Async client for AWS Bedrock runtime (Claude models)."""

    def __init__(self, region: str | None = None) -> None:
        self.region: str = region or AWS_REGION
        boto_config = BotoConfig(
            read_timeout=30,
            connect_timeout=10,
            retries={"max_attempts": 2},
        )
        # Use default credential chain (ENV vars → instance profile → config files)
        self.session = boto3.Session(region_name=self.region)
        self._runtime_client: Any = self.session.client(
            "bedrock-runtime",
            config=boto_config,
        )
        self._management_client: Any = self.session.client(
            "bedrock",
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

        start = time.monotonic()
        try:
            logger.info("Bedrock request: model=%s | prompt_len=%d", model_id, len(prompt))
            response = await asyncio.to_thread(
                self._runtime_client.invoke_model,
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
        except (ClientError, ReadTimeoutError, EndpointConnectionError,
                NoCredentialsError) as exc:
            elapsed = time.monotonic() - start
            logger.error(
                "Bedrock error: model=%s type=%s error=%s time=%.1fs",
                model, type(exc).__name__, exc, elapsed,
            )
            return HEBREW_FALLBACK
        except Exception as exc:
            elapsed = time.monotonic() - start
            logger.exception(
                "Bedrock unexpected error: model=%s time=%.1fs", model, elapsed,
            )
            return HEBREW_FALLBACK

    async def is_available(self) -> tuple[bool, str | None]:
        """Check if Bedrock is reachable.

        Returns (True, "haiku") on success, (False, None) on failure.
        """
        try:
            response = await asyncio.to_thread(
                self._management_client.list_foundation_models,
                byProvider="Anthropic",
            )
            models = [
                m["modelId"]
                for m in response.get("modelSummaries", [])
            ]
            claude_models = [m for m in models if "claude" in m.lower()]

            if claude_models:
                logger.info("Bedrock available: %d Claude models", len(claude_models))
                return True, "haiku"

            logger.warning("Bedrock reachable but no Claude models found")
            return False, None
        except Exception as exc:
            logger.error(
                "Bedrock availability check failed: %s: %s",
                type(exc).__name__, exc,
            )
            return False, None
