"""Fortress Bedrock client with API-key or AWS SigV4 auth."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Tuple
from urllib.parse import quote, urlparse

import httpx

from src.config import (
    AWS_ACCESS_KEY_ID,
    AWS_REGION,
    AWS_SECRET_ACCESS_KEY,
    AWS_SESSION_TOKEN,
    BEDROCK_API_KEY,
    BEDROCK_API_BASE_URL,
    BEDROCK_HAIKU_MODEL,
    BEDROCK_LITE_MODEL,
    BEDROCK_MICRO_MODEL,
    BEDROCK_SONNET_MODEL,
)

logger = logging.getLogger(__name__)

HEBREW_FALLBACK: str = "מצטער, לא הצלחתי לעבד את הבקשה. נסה שוב."

# Model selector -> actual model ID (cheapest first)
MODEL_MAP: dict[str, str] = {
    "micro": BEDROCK_MICRO_MODEL,
    "lite": BEDROCK_LITE_MODEL,
    "haiku": BEDROCK_HAIKU_MODEL,
    "sonnet": BEDROCK_SONNET_MODEL,
}


def _safe_exception_text(exc: Exception) -> str:
    """Keep log rendering ASCII-safe even when bad config contains Unicode."""
    return str(exc).encode("ascii", "backslashreplace").decode("ascii")


def _is_ascii(value: str) -> bool:
    try:
        value.encode("ascii")
    except UnicodeEncodeError:
        return False
    return True


@dataclass
class ToolCall:
    """A single tool invocation returned by the LLM."""
    tool_use_id: str
    name: str
    arguments: dict


@dataclass
class ConverseResponse:
    """Parsed response from the Bedrock Converse API."""
    text: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"  # "end_turn" | "tool_use" | "max_tokens"


class BedrockError(Exception):
    """Raised by converse() on HTTP errors, timeouts, or malformed responses."""
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class _AuthConfig:
    mode: str
    base_url: str
    static_headers: dict[str, str]
    service: str = "bedrock"


class BedrockClient:
    """Async client for AWS Bedrock Converse API."""

    def __init__(self) -> None:
        self._auth = self._build_auth_config()

    def _build_auth_config(self) -> _AuthConfig:
        api_key = BEDROCK_API_KEY.strip()
        if api_key:
            if _is_ascii(api_key):
                return _AuthConfig(
                    mode="api_key",
                    base_url=BEDROCK_API_BASE_URL.rstrip("/"),
                    static_headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json; charset=utf-8",
                    },
                )

            logger.warning(
                "Ignoring non-ASCII BEDROCK_API_KEY placeholder; using AWS credentials if available"
            )

        if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
            return _AuthConfig(
                mode="aws_sigv4",
                base_url=f"https://bedrock-runtime.{AWS_REGION}.amazonaws.com",
                static_headers={"Content-Type": "application/json; charset=utf-8"},
                service="bedrock",
            )

        raise ValueError(
            "Bedrock is not configured: set an ASCII BEDROCK_API_KEY or AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY"
        )

    @staticmethod
    def _json_bytes(payload: dict) -> bytes:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    def _signing_headers(self, *, canonical_path: str, body: bytes) -> dict[str, str]:
        timestamp = datetime.now(timezone.utc)
        amz_date = timestamp.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = timestamp.strftime("%Y%m%d")
        parsed = urlparse(self._auth.base_url)
        host = parsed.netloc
        payload_hash = hashlib.sha256(body).hexdigest()

        canonical_headers = (
            f"content-type:{self._auth.static_headers['Content-Type']}\n"
            f"host:{host}\n"
            f"x-amz-content-sha256:{payload_hash}\n"
            f"x-amz-date:{amz_date}\n"
        )
        signed_headers = "content-type;host;x-amz-content-sha256;x-amz-date"

        if AWS_SESSION_TOKEN:
            canonical_headers += f"x-amz-security-token:{AWS_SESSION_TOKEN}\n"
            signed_headers += ";x-amz-security-token"

        canonical_request = "\n".join(
            [
                "POST",
                canonical_path,
                "",
                canonical_headers,
                signed_headers,
                payload_hash,
            ]
        )
        credential_scope = f"{date_stamp}/{AWS_REGION}/{self._auth.service}/aws4_request"
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                credential_scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )

        signing_key = self._get_signature_key(AWS_SECRET_ACCESS_KEY, date_stamp, AWS_REGION, self._auth.service)
        signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

        headers = {
            "Content-Type": self._auth.static_headers["Content-Type"],
            "X-Amz-Date": amz_date,
            "X-Amz-Content-Sha256": payload_hash,
            "Authorization": (
                "AWS4-HMAC-SHA256 "
                f"Credential={AWS_ACCESS_KEY_ID}/{credential_scope}, "
                f"SignedHeaders={signed_headers}, "
                f"Signature={signature}"
            ),
        }
        if AWS_SESSION_TOKEN:
            headers["X-Amz-Security-Token"] = AWS_SESSION_TOKEN
        return headers

    @staticmethod
    def _sign(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    @classmethod
    def _get_signature_key(cls, key: str, date_stamp: str, region_name: str, service_name: str) -> bytes:
        k_date = cls._sign(("AWS4" + key).encode("utf-8"), date_stamp)
        k_region = cls._sign(k_date, region_name)
        k_service = cls._sign(k_region, service_name)
        return cls._sign(k_service, "aws4_request")

    def _make_request(self, model_id: str, payload: dict) -> tuple[str, str, bytes, dict[str, str]]:
        encoded_model_id = quote(model_id, safe="-_.~")
        path = f"/model/{encoded_model_id}/converse"
        canonical_path = quote(path, safe="/-_.~")
        body = self._json_bytes(payload)

        if self._auth.mode == "api_key":
            return f"{self._auth.base_url}{path}", canonical_path, body, dict(self._auth.static_headers)

        return (
            f"{self._auth.base_url}{path}",
            canonical_path,
            body,
            self._signing_headers(canonical_path=canonical_path, body=body),
        )

    async def _post_converse(self, model_id: str, payload: dict, timeout: float) -> httpx.Response:
        url, _, body, headers = self._make_request(model_id, payload)
        async with httpx.AsyncClient(timeout=timeout) as client:
            return await client.post(url, headers=headers, content=body)

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

        start = time.monotonic()
        try:
            logger.info("Bedrock request: model=%s prompt_len=%d auth=%s", model_id, len(prompt), self._auth.mode)
            resp = await self._post_converse(model_id, payload, timeout=30.0)
            resp.raise_for_status()
            data = resp.json()
            result = data["output"]["message"]["content"][0]["text"]
            elapsed = time.monotonic() - start
            logger.info("Bedrock response: len=%d time=%.1fs", len(result), elapsed)
            return result
        except httpx.HTTPStatusError as exc:
            elapsed = time.monotonic() - start
            logger.error(
                "Bedrock HTTP error: status=%s model=%s time=%.1fs body=%s",
                exc.response.status_code,
                model_id,
                elapsed,
                exc.response.text[:200],
            )
            return HEBREW_FALLBACK
        except Exception as exc:
            elapsed = time.monotonic() - start
            logger.error(
                "Bedrock unexpected error: model=%s time=%.1fs error=%s: %s",
                model_id,
                elapsed,
                type(exc).__name__,
                _safe_exception_text(exc),
            )
            return HEBREW_FALLBACK

    async def converse(
        self,
        messages: list[dict],
        system_prompt: str = "",
        tools: list[dict] | None = None,
        model: str = "haiku",
        max_tokens: int = 1024,
    ) -> ConverseResponse:
        """Call Bedrock Converse API with optional tool definitions.

        Returns ConverseResponse with either text or tool_calls populated.
        Raises BedrockError on HTTP/network failures or malformed responses.
        """
        model_id = MODEL_MAP.get(model, BEDROCK_HAIKU_MODEL)
        payload: dict = {
            "messages": messages,
            "inferenceConfig": {"maxTokens": max_tokens},
        }
        if system_prompt:
            payload["system"] = [{"text": system_prompt}]
        if tools:
            payload["toolConfig"] = {"tools": tools}

        start = time.monotonic()
        try:
            logger.info(
                "Bedrock converse: model=%s messages=%d tools=%d auth=%s",
                model_id, len(messages), len(tools) if tools else 0, self._auth.mode,
            )
            resp = await self._post_converse(model_id, payload, timeout=30.0)
            resp.raise_for_status()
            data = resp.json()
            elapsed = time.monotonic() - start

            stop_reason = data.get("stopReason", "end_turn")
            content_blocks = data.get("output", {}).get("message", {}).get("content", [])

            tool_calls: list[ToolCall] = []
            text_parts: list[str] = []

            for block in content_blocks:
                if "toolUse" in block:
                    tu = block["toolUse"]
                    tool_calls.append(ToolCall(
                        tool_use_id=tu.get("toolUseId", ""),
                        name=tu.get("name", ""),
                        arguments=tu.get("input", {}),
                    ))
                elif "text" in block:
                    text_parts.append(block["text"])

            text = "\n".join(text_parts) if text_parts else None
            logger.info(
                "Bedrock converse response: stop_reason=%s tool_calls=%d text_len=%d time=%.1fs",
                stop_reason, len(tool_calls), len(text) if text else 0, elapsed,
            )
            return ConverseResponse(text=text, tool_calls=tool_calls, stop_reason=stop_reason)

        except httpx.HTTPStatusError as exc:
            elapsed = time.monotonic() - start
            logger.error(
                "Bedrock converse HTTP error: status=%s model=%s time=%.1fs body=%s",
                exc.response.status_code, model_id, elapsed, exc.response.text[:200],
            )
            raise BedrockError(
                f"HTTP {exc.response.status_code}: {exc.response.text[:100]}",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.TimeoutException as exc:
            elapsed = time.monotonic() - start
            logger.error("Bedrock converse timeout: model=%s time=%.1fs", model_id, elapsed)
            raise BedrockError("Request timed out") from exc
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            elapsed = time.monotonic() - start
            logger.error(
                "Bedrock converse malformed response: model=%s time=%.1fs error=%s",
                model_id, elapsed, _safe_exception_text(exc),
            )
            raise BedrockError(f"Malformed response: {_safe_exception_text(exc)}") from exc
        except BedrockError:
            raise
        except Exception as exc:
            elapsed = time.monotonic() - start
            logger.error(
                "Bedrock converse unexpected error: model=%s time=%.1fs error=%s: %s",
                model_id, elapsed, type(exc).__name__, _safe_exception_text(exc),
            )
            raise BedrockError(f"Unexpected error: {_safe_exception_text(exc)}") from exc

    async def is_available(self) -> Tuple[bool, Optional[str]]:
        """Check connectivity with a minimal request.

        Returns (True, model_alias) on success, (False, None) on failure.
        """
        payload = {
            "messages": [{"role": "user", "content": [{"text": "hi"}]}],
            "inferenceConfig": {"maxTokens": 5},
        }
        models_to_try = ("haiku", "lite", "micro", "sonnet")

        for alias in models_to_try:
            model_id = MODEL_MAP.get(alias)
            if not model_id:
                continue
            try:
                resp = await self._post_converse(model_id, payload, timeout=10.0)
                if resp.status_code == 200:
                    logger.info("Bedrock available: model=%s auth=%s", model_id, self._auth.mode)
                    return True, alias
                logger.warning("Bedrock check failed: model=%s status=%s", model_id, resp.status_code)
            except Exception as exc:
                logger.error(
                    "Bedrock availability check failed: model=%s error=%s: %s",
                    model_id,
                    type(exc).__name__,
                    _safe_exception_text(exc),
                )

        return False, None
