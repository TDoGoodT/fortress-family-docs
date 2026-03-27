"""Tests for WAHA NOWEB webhook compatibility in whatsapp router."""

from unittest.mock import AsyncMock, patch


def test_webhook_extracts_text_and_phone_from_noweb_lid_payload(client, mock_db) -> None:
    body = {
        "event": "message",
        "payload": {
            "id": "false_4639135154355@lid_abc",
            "from": "227440160956630@lid",
            "fromMe": False,
            "body": None,
            "hasMedia": False,
            "_data": {
                "key": {
                    "remoteJid": "227440160956630@lid",
                    "remoteJidAlt": "972542364393@s.whatsapp.net",
                },
                "message": {
                    "extendedTextMessage": {
                        "text": "שלום",
                    }
                },
            },
        },
    }

    with patch(
        "src.routers.whatsapp.handle_incoming_message",
        new=AsyncMock(return_value="היי שגב"),
    ) as mock_handle, patch(
        "src.routers.whatsapp.send_text_message",
        new=AsyncMock(return_value=True),
    ) as mock_send:
        response = client.post("/webhook/whatsapp", json=body)

    assert response.status_code == 200
    assert response.json() == {"status": "processed"}
    mock_handle.assert_awaited_once_with(
        mock_db,
        "972542364393",
        "שלום",
        "false_4639135154355@lid_abc",
        has_media=False,
        media_file_path=None,
    )
    mock_send.assert_awaited_once_with("972542364393", "היי שגב")


def test_webhook_ignores_empty_non_text_noweb_event(client) -> None:
    body = {
        "event": "message",
        "payload": {
            "id": "msg-empty",
            "from": "972542364393@c.us",
            "fromMe": False,
            "body": None,
            "hasMedia": False,
            "_data": {"message": {"protocolMessage": {"type": "HISTORY_SYNC"}}},
        },
    }

    with patch(
        "src.routers.whatsapp.handle_incoming_message",
        new=AsyncMock(),
    ) as mock_handle, patch(
        "src.routers.whatsapp.send_text_message",
        new=AsyncMock(),
    ) as mock_send:
        response = client.post("/webhook/whatsapp", json=body)

    assert response.status_code == 200
    assert response.json() == {"status": "ignored", "reason": "non-text message"}
    mock_handle.assert_not_awaited()
    mock_send.assert_not_awaited()
