"""Fortress Skills Engine — response formatter with WhatsApp truncation."""

from __future__ import annotations

from src.skills.base_skill import Result

WHATSAPP_CHAR_LIMIT = 3500
TRUNCATION_INDICATOR = "\n\n... (הודעה קוצרה)"


def format_response(result: Result) -> str:
    """Format a Result into a WhatsApp-safe string. Truncates at ~3500 chars."""
    message = result.message
    if len(message) > WHATSAPP_CHAR_LIMIT:
        return message[:WHATSAPP_CHAR_LIMIT] + TRUNCATION_INDICATOR
    return message
