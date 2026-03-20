"""Fortress 2.0 WhatsApp router — WAHA webhook handler."""

import logging

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.database import get_db
from src.services.message_handler import handle_incoming_message
from src.services.whatsapp_client import send_text_message
from src.utils.media import download_media, save_media
from src.utils.phone import normalize_phone

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/webhook/whatsapp")
async def whatsapp_webhook(
    body: dict[str, Any],
    db: Session = Depends(get_db),
) -> dict:
    """Handle incoming WAHA webhook events.

    Always returns 200 — WAHA retries on non-200 responses.
    """
    try:
        event = body.get("event", "")
        if event != "message":
            return {"status": "ignored", "reason": "non-message event"}

        payload = body.get("payload", {})
        from_raw = payload.get("from", "")
        phone = normalize_phone(from_raw)

        # Echo prevention: ignore messages sent by the bot itself
        if payload.get("fromMe", False):
            return {"status": "ignored", "reason": "echo"}

        message_id = payload.get("id", "")
        message_text = payload.get("body", "")
        has_media = payload.get("hasMedia", False)
        logger.info("Incoming message from %s: %s", phone, message_text)

        media_file_path: str | None = None
        if has_media and message_id:
            media_result = await download_media(message_id)
            if media_result:
                file_bytes, mimetype = media_result
                filename = payload.get("filename", "attachment")
                media_file_path = save_media(file_bytes, filename, mimetype)

        response_text = await handle_incoming_message(
            db,
            phone,
            message_text,
            message_id,
            has_media=has_media,
            media_file_path=media_file_path,
        )
        logger.info("Response: %s", response_text)
        await send_text_message(phone, response_text)
        return {"status": "processed"}

    except Exception:
        logger.exception("Error processing webhook")
        return {"status": "error", "detail": "internal processing error"}
