from __future__ import annotations
"""Fortress 2.0 WhatsApp client - sends messages via WAHA API."""

import logging

import httpx

from src.config import WAHA_API_KEY, WAHA_API_URL

logger = logging.getLogger(__name__)


def _build_headers() -> dict[str, str]:
    """Build request headers, including X-Api-Key only when configured."""
    if WAHA_API_KEY:
        return {"X-Api-Key": WAHA_API_KEY}
    return {}


async def send_text_message(phone: str, text: str) -> bool:
    """Send a text message through WAHA.

    *phone* should be digits only (e.g. "972501234567").
    Returns True on success, False otherwise. Never raises.
    """
    payload = {
        "chatId": f"{phone}@c.us",
        "text": text,
        "session": "default",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{WAHA_API_URL}/api/sendText",
                json=payload,
                headers=_build_headers(),
            )
            if resp.status_code == 200 or resp.status_code == 201:
                logger.info("Sent message to %s: %s", phone, text[:80])
                return True
            logger.error("WAHA send failed: %s %s", resp.status_code, resp.text)
            return False
    except Exception:
        logger.exception("Error sending message to %s", phone)
        return False


async def send_reply(phone: str, text: str, message_id: str) -> bool:
    """Send a reply to a specific message through WAHA.

    Same as send_text_message but includes reply_to reference.
    """
    payload = {
        "chatId": f"{phone}@c.us",
        "text": text,
        "session": "default",
        "reply_to": message_id,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{WAHA_API_URL}/api/sendText",
                json=payload,
                headers=_build_headers(),
            )
            if resp.status_code == 200 or resp.status_code == 201:
                logger.info("Sent reply to %s (re: %s): %s", phone, message_id, text[:80])
                return True
            logger.error("WAHA reply failed: %s %s", resp.status_code, resp.text)
            return False
    except Exception:
        logger.exception("Error sending reply to %s", phone)
        return False
