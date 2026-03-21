"""Unit tests for OpenRouterClient."""

import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.openrouter_client import HEBREW_FALLBACK, OpenRouterClient


def _mock_response(content: str = "שלום!") -> MagicMock:
    """Build a mock httpx.Response with valid OpenAI-format JSON."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "choices": [{"message": {"content": content}}],
    }
    resp.raise_for_status = MagicMock()
    return resp


@pytest.mark.asyncio
async def test_generate_success():
    """Successful generation returns the response text."""
    client = OpenRouterClient(api_key="test-key", model="test-model")
    mock_resp = _mock_response("שלום!")

    with patch("src.services.openrouter_client.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_http

        result = await client.generate("hello", "system prompt")
        assert result == "שלום!"


@pytest.mark.asyncio
async def test_generate_custom_model():
    """Custom model is used when explicitly provided."""
    client = OpenRouterClient(api_key="test-key", model="default-model")
    mock_resp = _mock_response("response")

    with patch("src.services.openrouter_client.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_http

        await client.generate("hello", model="custom-model")
        call_kwargs = mock_http.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["model"] == "custom-model"


@pytest.mark.asyncio
async def test_generate_default_model():
    """Default model is used when none specified."""
    client = OpenRouterClient(api_key="test-key", model="my-default")
    mock_resp = _mock_response("response")

    with patch("src.services.openrouter_client.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_http

        await client.generate("hello")
        call_kwargs = mock_http.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["model"] == "my-default"


@pytest.mark.asyncio
async def test_generate_timeout_returns_fallback():
    """Timeout returns Hebrew fallback."""
    client = OpenRouterClient(api_key="test-key")

    with patch("src.services.openrouter_client.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_http

        result = await client.generate("hello")
        assert result == HEBREW_FALLBACK


@pytest.mark.asyncio
async def test_generate_connection_error_returns_fallback():
    """Connection error returns Hebrew fallback."""
    client = OpenRouterClient(api_key="test-key")

    with patch("src.services.openrouter_client.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_http

        result = await client.generate("hello")
        assert result == HEBREW_FALLBACK


@pytest.mark.asyncio
async def test_generate_http_error_returns_fallback():
    """HTTP 500 error returns Hebrew fallback."""
    client = OpenRouterClient(api_key="test-key")

    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500", request=MagicMock(), response=mock_resp,
    )

    with patch("src.services.openrouter_client.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_http

        result = await client.generate("hello")
        assert result == HEBREW_FALLBACK


@pytest.mark.asyncio
async def test_generate_empty_api_key_returns_fallback():
    """Empty API key returns fallback without making HTTP call."""
    client = OpenRouterClient(api_key="")

    with patch("src.services.openrouter_client.httpx.AsyncClient") as mock_cls:
        result = await client.generate("hello")
        assert result == HEBREW_FALLBACK
        mock_cls.assert_not_called()


@pytest.mark.asyncio
async def test_generate_sends_correct_headers():
    """Request includes Authorization, HTTP-Referer, and X-Title headers."""
    client = OpenRouterClient(api_key="my-secret-key", model="test-model")
    mock_resp = _mock_response("ok")

    with patch("src.services.openrouter_client.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_http

        await client.generate("hello", "sys")
        call_kwargs = mock_http.post.call_args
        headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers")
        assert headers["Authorization"] == "Bearer my-secret-key"
        assert "HTTP-Referer" in headers
        assert headers["X-Title"] == "Fortress"


@pytest.mark.asyncio
async def test_is_available_with_valid_key():
    """is_available returns (True, model_name) when API is reachable."""
    client = OpenRouterClient(api_key="test-key", model="test-model")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()

    with patch("src.services.openrouter_client.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_resp)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_http

        ok, model = await client.is_available()
        assert ok is True
        assert model == "test-model"


@pytest.mark.asyncio
async def test_is_available_with_empty_key():
    """is_available returns (False, None) without HTTP call when no API key."""
    client = OpenRouterClient(api_key="")

    with patch("src.services.openrouter_client.httpx.AsyncClient") as mock_cls:
        ok, model = await client.is_available()
        assert ok is False
        assert model is None
        mock_cls.assert_not_called()
