"""Fortress 2.0 message handler — thin auth layer delegating to workflow engine."""

import logging

from sqlalchemy.orm import Session

from src.models.schema import Conversation
from src.prompts.personality import TEMPLATES as PERSONALITY_TEMPLATES
from src.services.auth import get_family_member_by_phone
from src.services.workflow_engine import run_workflow

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
    """Authenticate sender and delegate to workflow engine."""
    member = get_family_member_by_phone(db, phone)

    if member is None:
        response = PERSONALITY_TEMPLATES["unknown_member"]
        _save_conversation(db, None, message_text, response, "unknown_sender")
        return response

    if not member.is_active:
        response = PERSONALITY_TEMPLATES["inactive_member"]
        _save_conversation(db, member.id, message_text, response, "inactive_member")
        return response

    return await run_workflow(
        db,
        member,
        phone,
        message_text,
        has_media=has_media,
        media_file_path=media_file_path,
    )


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
