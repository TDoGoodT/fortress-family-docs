"""Fortress 2.0 WhatsApp router — WAHA webhook handler."""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from src.config import WAHA_API_KEY
from src.database import get_db
from src.services.message_handler import handle_incoming_message
from src.services.whatsapp_client import send_text_message
from src.utils.media import download_media, save_media
from src.utils.phone import is_valid_israeli_phone, normalize_phone
from src.utils.rate_limit import is_rate_limited

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_nested_value(data: dict, *path: str) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _iter_text_candidates(value: Any) -> list:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        candidates = []
        for key in ("body", "text", "caption", "conversation", "contentText", "selectedDisplayText"):
            item = value.get(key)
            if isinstance(item, str):
                candidates.append(item)
        for nested in value.values():
            if isinstance(nested, (dict, list)):
                candidates.extend(_iter_text_candidates(nested))
        return candidates
    if isinstance(value, list):
        candidates = []
        for item in value:
            if isinstance(item, (dict, list, str)):
                candidates.extend(_iter_text_candidates(item))
        return candidates
    return []


def _extract_message_text(payload: dict) -> Optional[str]:
    for candidate in _iter_text_candidates(payload.get("body")):
        text = candidate.strip()
        if text:
            return text

    for key in ("caption", "text"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    for candidate in _iter_text_candidates(_get_nested_value(payload, "_data", "message")):
        text = candidate.strip()
        if text:
            return text

    return None


def _extract_sender_phone(payload: dict) -> str:
    candidates = [
        _get_nested_value(payload, "_data", "key", "remoteJidAlt"),
        _get_nested_value(payload, "_data", "participantPn"),
        _get_nested_value(payload, "_data", "key", "participantPn"),
        payload.get("from"),
        payload.get("participant"),
        payload.get("author"),
        _get_nested_value(payload, "_data", "key", "remoteJid"),
        _get_nested_value(payload, "_data", "key", "participant"),
    ]

    fallback = ""
    for raw in candidates:
        if not isinstance(raw, str) or not raw:
            continue
        phone = normalize_phone(raw)
        if not phone:
            continue
        if is_valid_israeli_phone(phone):
            return phone
        if not fallback:
            fallback = phone
    return fallback


@router.post("/webhook/whatsapp")
async def whatsapp_webhook(
    body: dict,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(default=None, alias="X-Api-Key"),
) -> dict:
    """Handle incoming WAHA webhook events.

    Always returns 200 — WAHA retries on non-200 responses.
    Validates X-Api-Key header when WAHA_API_KEY is configured.
    """
    if WAHA_API_KEY and x_api_key is not None and x_api_key != WAHA_API_KEY:
        logger.warning("Webhook rejected: invalid X-Api-Key")
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        event = body.get("event", "")
        if event != "message":
            return {"status": "ignored", "reason": "non-message event"}

        payload = body.get("payload", {})

        if payload.get("fromMe", False):
            return {"status": "ignored", "reason": "echo"}

        phone = _extract_sender_phone(payload)
        if not phone:
            logger.info("Ignoring message without resolvable sender: %s", payload.get("id"))
            return {"status": "ignored", "reason": "missing sender"}

        if is_rate_limited(phone):
            logger.warning("Rate limit exceeded for %s", phone)
            return {"status": "ignored", "reason": "rate_limited"}

        message_id = payload.get("id", "")
        message_text = _extract_message_text(payload)
        has_media = payload.get("hasMedia", False)

        if not message_text and not has_media:
            logger.info("Ignoring non-text message from %s: %s", phone, message_id)
            return {"status": "ignored", "reason": "non-text message"}

        logger.info("Incoming message from %s: %s", phone, message_text)

        media_file_path: Optional[str] = None
        if has_media and message_id:
            logger.info(
                "Media received: type=%s mimetype=%s filename=%s",
                payload.get("type", "unknown"),
                payload.get("mimetype", "unknown"),
                payload.get("filename", "unknown"),
            )
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
        if response_text:
            await send_text_message(phone, response_text)
        return {"status": "processed"}

    except Exception:
        logger.exception("Error processing webhook")
        return {"status": "error", "detail": "internal processing error"}
