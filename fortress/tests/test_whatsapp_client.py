"""Unit tests for the WhatsApp client service."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.whatsapp_client import send_reply, send_text_message


@pytest.mark.asyncio
async def test_send_text_message_payload() -> None:
    """send_text_message should POST correct payload to WAHA."""
    mock_response = MagicMock()
    mock_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("src.services.whatsapp_client.httpx.AsyncClient", return_value=mock_client):
        result = await send_text_message("972501234567", "Hello")

    assert result is True
    mock_client.post.assert_called_once()
    call_kwargs = mock_client.post.call_args
    payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
    assert payload["chatId"] == "972501234567@c.us"
    assert payload["text"] == "Hello"
    assert payload["session"] == "default"


@pytest.mark.asyncio
async def test_send_text_message_failure() -> None:
    """send_text_message should return False on API failure."""
    mock_client = AsyncMock()
    mock_client.post.side_effect = Exception("connection refused")
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("src.services.whatsapp_client.httpx.AsyncClient", return_value=mock_client):
        result = await send_text_message("972501234567", "Hello")

    assert result is False


@pytest.mark.asyncio
async def test_send_reply_includes_reply_to() -> None:
    """send_reply should include reply_to in the payload."""
    mock_response = MagicMock()
    mock_response.status_code = 201

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("src.services.whatsapp_client.httpx.AsyncClient", return_value=mock_client):
        result = await send_reply("972501234567", "Got it", "msg_123")

    assert result is True
    call_kwargs = mock_client.post.call_args
    payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
    assert payload["reply_to"] == "msg_123"
