"""Unit tests for the LLM client (OllamaClient)."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.services.llm_client import HEBREW_FALLBACK, OllamaClient


# ── generate() tests ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_sends_correct_payload() -> None:
    """generate() should POST correct payload to /api/generate."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"response": "שלום!", "done": True}
    mock_response.raise_for_status = MagicMock()

    with patch("src.services.llm_client.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client

        client = OllamaClient(base_url="http://test:11434", model="test-model")
        result = await client.generate("hello", system_prompt="be nice")

        assert result == "שלום!"
        mock_client.post.assert_called_once_with(
            "http://test:11434/api/generate",
            json={
                "model": "test-model",
                "prompt": "hello",
                "system": "be nice",
                "stream": False,
            },
        )


@pytest.mark.asyncio
async def test_generate_timeout_returns_fallback() -> None:
    """generate() should return Hebrew fallback on timeout."""
    with patch("src.services.llm_client.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.TimeoutException("timeout")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client

        client = OllamaClient()
        result = await client.generate("test")
        assert result == HEBREW_FALLBACK


@pytest.mark.asyncio
async def test_generate_connection_error_returns_fallback() -> None:
    """generate() should return Hebrew fallback on connection error."""
    with patch("src.services.llm_client.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.ConnectError("refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client

        client = OllamaClient()
        result = await client.generate("test")
        assert result == HEBREW_FALLBACK


# ── is_available() tests ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_is_available_true_when_model_present() -> None:
    """is_available() should return True when model is in tags list."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "models": [{"name": "llama3.1:8b", "size": 1234}]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("src.services.llm_client.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client

        client = OllamaClient(model="llama3.1:8b")
        available, model_name = await client.is_available()
        assert available is True
        assert model_name == "llama3.1:8b"


@pytest.mark.asyncio
async def test_is_available_false_when_model_missing() -> None:
    """is_available() should return False when model is not in tags list."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "models": [{"name": "other-model:7b", "size": 1234}]
    }
    mock_response.raise_for_status = MagicMock()

    with patch("src.services.llm_client.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client

        client = OllamaClient(model="llama3.1:8b")
        available, model_name = await client.is_available()
        assert available is False
        assert model_name is None


@pytest.mark.asyncio
async def test_is_available_false_on_connection_error() -> None:
    """is_available() should return False on connection error."""
    with patch("src.services.llm_client.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.get.side_effect = httpx.ConnectError("refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client

        client = OllamaClient()
        available, model_name = await client.is_available()
        assert available is False
        assert model_name is None
