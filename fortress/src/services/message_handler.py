from __future__ import annotations
"""Fortress message handler — auth → parse → execute → format."""

import logging
import re

from sqlalchemy.orm import Session

from src.models.schema import Conversation
from src.prompts.personality import TEMPLATES as PERSONALITY_TEMPLATES
from src.services.auth import get_family_member_by_phone
from src.engine.command_parser import parse_command
from src.engine.executor import execute
from src.engine.response_formatter import format_response
from src.services.intent_detector import detect_intent, should_fallback_to_chat
from src.services.pii_guard import strip_pii
from src.services.conversation_state import get_state
from src.skills.base_skill import Command
from src.skills.registry import registry

logger = logging.getLogger(__name__)

# Hebrew question indicators for contextual follow-up detection
_QUESTION_WORDS = re.compile(
    r'(?:מה|מי|כמה|איזה|למה|מתי|האם|איפה|איך|תאריך|סכום|ספק|סיכום)',
    re.IGNORECASE,
)


def _try_contextual_followup(
    db: Session,
    member,
    message_text: str,
) -> Command | None:
    """If the user sent a short question and their last context is a document,
    route it as a contextual document query. Returns Command or None."""
    text = (message_text or "").strip()
    if not text:
        return None

    # Short query heuristic: ≤ 4 words or contains a question mark
    word_count = len(text.split())
    has_question_mark = "?" in text or "?" in text  # ASCII + Hebrew question mark
    has_question_word = bool(_QUESTION_WORDS.search(text))

    if word_count > 4 and not has_question_mark:
        return None

    if not has_question_mark and not has_question_word:
        return None

    # Check conversation state for document context
    try:
        state = get_state(db, member.id)
    except Exception:
        return None

    if state.last_entity_type != "document" or state.last_entity_id is None:
        return None

    logger.info(
        "contextual_followup: routing short query to document.contextual_query doc_id=%s text=%s",
        state.last_entity_id,
        text[:80],
    )
    return Command(
        skill="document",
        action="contextual_query",
        params={
            "question": text,
            "doc_id": str(state.last_entity_id),
        },
        raw_text=text,
    )


def _sanitize_response(response: str) -> str:
    """Never return raw JSON to user."""
    stripped = response.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        logger.error("Raw JSON in response: %s", stripped[:200])
        return PERSONALITY_TEMPLATES["error_fallback"]
    return response


async def handle_incoming_message(
    db: Session,
    phone: str,
    message_text: str | None,
    message_id: str,
    *,
    has_media: bool = False,
    media_file_path: str | None = None,
) -> str:
    """Authenticate sender and process via Skills Engine or deterministic fallback."""
    if not message_text and not has_media:
        return ""
    message_text = message_text or ""
    member = get_family_member_by_phone(db, phone)

    if member is None:
        response = PERSONALITY_TEMPLATES["unknown_member"]
        _save_conversation(db, None, message_text, response, "unknown_sender")
        return response

    if not member.is_active:
        response = PERSONALITY_TEMPLATES["inactive_member"]
        _save_conversation(db, member.id, message_text, response, "inactive_member")
        return response

    try:
        # Parse — deterministic, zero LLM
        command = parse_command(
            message_text, registry, has_media=has_media, media_file_path=media_file_path
        )
        detected_intent = detect_intent(message_text)
        logger.info("intent_detected intent=%s", detected_intent)

        # Determine PII status for audit logging
        try:
            _, pii_records = strip_pii(message_text)
            pii_stripped = len(pii_records) > 0
        except Exception:
            logger.exception("strip_pii failed in message handler")
            pii_stripped = False

        if command is not None:
            logger.info(
                "message_handler: parsed_command skill=%s action=%s has_media=%s media_file_path_present=%s",
                command.skill,
                command.action,
                has_media,
                bool(media_file_path),
            )
            # Skills Engine path — inject PII metadata for executor audit logging
            command.params["_original_message"] = message_text
            command.params["_pii_stripped"] = pii_stripped
            result = execute(db, member, command)
            response = format_response(result)
            intent = f"{command.skill}.{command.action}"
        else:
            # Check for contextual follow-up: short query + last entity is document
            contextual_command = _try_contextual_followup(db, member, message_text)
            if contextual_command is not None:
                logger.info(
                    "message_handler: contextual_followup skill=%s action=%s",
                    contextual_command.skill,
                    contextual_command.action,
                )
                contextual_command.params["_original_message"] = message_text
                contextual_command.params["_pii_stripped"] = pii_stripped
                result = execute(db, member, contextual_command)
                response = format_response(result)
                intent = f"{contextual_command.skill}.{contextual_command.action}"
            elif should_fallback_to_chat(message_text):
                from src.skills.registry import registry as _registry
                chat_skill = _registry.get("chat")
                if chat_skill is not None:
                    response = await chat_skill.respond(db, member, message_text)
                    intent = "chat.llm"
                else:
                    response = PERSONALITY_TEMPLATES["cant_understand"]
                    intent = "strict.unknown"
            else:
                response = PERSONALITY_TEMPLATES["cant_understand"]
                intent = "strict.unknown"

        # Guard against empty/None responses
        if not response or not response.strip():
            logger.error("Empty response for: %s", message_text[:100])
            response = PERSONALITY_TEMPLATES["error_fallback"]

        response = _sanitize_response(response)
        logger.info(
            "message_handler: response_ready member_id=%s intent=%s response_len=%d",
            member.id,
            intent,
            len(response),
        )
        _save_conversation(db, member.id, message_text, response, intent)
        return response

    except Exception:
        logger.exception("Fatal error in message handler")
        response = PERSONALITY_TEMPLATES["error_fallback"]
        try:
            _save_conversation(db, member.id, message_text, response, "error")
        except Exception:
            logger.exception("Failed to save error conversation")
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
