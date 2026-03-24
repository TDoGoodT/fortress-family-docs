"""Fortress message handler — auth → parse → execute → format."""

import logging

from sqlalchemy.orm import Session

from src.models.schema import Conversation
from src.prompts.personality import TEMPLATES as PERSONALITY_TEMPLATES
from src.services.auth import get_family_member_by_phone
from src.engine.command_parser import parse_command
from src.engine.executor import execute
from src.engine.response_formatter import format_response
from src.services.pii_guard import strip_pii
from src.skills.registry import registry

logger = logging.getLogger(__name__)


async def handle_incoming_message(
    db: Session,
    phone: str,
    message_text: str,
    message_id: str,
    *,
    has_media: bool = False,
    media_file_path: str | None = None,
) -> str:
    """Authenticate sender and process via Skills Engine or LLM fallback."""
    member = get_family_member_by_phone(db, phone)

    if member is None:
        response = PERSONALITY_TEMPLATES["unknown_member"]
        _save_conversation(db, None, message_text, response, "unknown_sender")
        return response

    if not member.is_active:
        response = PERSONALITY_TEMPLATES["inactive_member"]
        _save_conversation(db, member.id, message_text, response, "inactive_member")
        return response

    # Parse — deterministic, zero LLM
    command = parse_command(
        message_text, registry, has_media=has_media, media_file_path=media_file_path
    )

    # Determine PII status for audit logging
    try:
        _, pii_records = strip_pii(message_text)
        pii_stripped = len(pii_records) > 0
    except Exception:
        logger.exception("strip_pii failed in message handler")
        pii_stripped = False

    if command is not None:
        # Skills Engine path — inject PII metadata for executor audit logging
        command.params["_original_message"] = message_text
        command.params["_pii_stripped"] = pii_stripped
        result = execute(db, member, command)
        response = format_response(result)
        intent = f"{command.skill}.{command.action}"
    else:
        # LLM fallback — delegate to ChatSkill
        chat = registry.get("chat")
        response = await chat.respond(db, member, message_text)
        intent = "chat.respond"

    _save_conversation(db, member.id, message_text, response, intent)
    return response


def _save_conversation(
    db: Session,
    member_id,
    message_in: str,
    message_out: str,
    intent: str,
) -> None:
    """Save the conversation exchange to the database."""
    conv = Conversation(
        family_member_id=member_id,
        message_in=message_in,
        message_out=message_out,
        intent=intent,
    )
    db.add(conv)
    db.commit()
