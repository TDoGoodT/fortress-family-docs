from __future__ import annotations

import httpx
import pytest

from src.services import bedrock_client as bedrock_module
from src.services.bedrock_client import BedrockClient


def test_non_ascii_api_key_uses_aws_sigv4(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bedrock_module, "BEDROCK_API_KEY", "המפתח_שלך")
    monkeypatch.setattr(bedrock_module, "AWS_ACCESS_KEY_ID", "AKIATESTKEY")
    monkeypatch.setattr(bedrock_module, "AWS_SECRET_ACCESS_KEY", "secret-test-key")
    monkeypatch.setattr(bedrock_module, "AWS_REGION", "us-east-1")

    client = BedrockClient()

    assert client._auth.mode == "aws_sigv4"
    url, canonical_path, _, headers = client._make_request(
        "anthropic.claude-3-haiku-20240307-v1:0",
        {"messages": [{"role": "user", "content": [{"text": "שלום"}]}]},
    )
    assert "%3A0" in url
    assert "%253A0" in canonical_path
    assert headers["Authorization"].startswith("AWS4-HMAC-SHA256 ")
    assert "המפתח_שלך" not in headers["Authorization"]


@pytest.mark.asyncio
async def test_is_available_returns_first_working_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bedrock_module, "BEDROCK_API_KEY", "המפתח_שלך")
    monkeypatch.setattr(bedrock_module, "AWS_ACCESS_KEY_ID", "AKIATESTKEY")
    monkeypatch.setattr(bedrock_module, "AWS_SECRET_ACCESS_KEY", "secret-test-key")
    monkeypatch.setattr(bedrock_module, "AWS_REGION", "us-east-1")

    client = BedrockClient()

    async def fake_post_converse(model_id: str, payload: dict, timeout: float) -> httpx.Response:
        assert payload["messages"][0]["content"][0]["text"] == "hi"
        assert timeout == 10.0
        return httpx.Response(200, json={"output": {"message": {"content": [{"text": "ok"}]}}})

    monkeypatch.setattr(client, "_post_converse", fake_post_converse)

    assert await client.is_available() == (True, "economy")
