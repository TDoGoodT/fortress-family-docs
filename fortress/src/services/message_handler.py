from __future__ import annotations
"""Fortress message handler — auth → agent loop → respond."""

import logging

from sqlalchemy.orm import Session

from src.models.schema import Conversation
from src.prompts.personality import TEMPLATES as PERSONALITY_TEMPLATES
from src.services.auth import get_family_member_by_phone
from src.engine.command_parser import parse_command
from src.engine.executor import execute
from src.engine.response_formatter import format_response
from src.services.intent_detector import should_fallback_to_chat
from src.services.pii_guard import strip_pii
from src.skills.registry import registry
from src.config import AGENT_ENABLED

logger = logging.getLogger(__name__)


def _sanitize_response(response: str) -> str:
    """Never return raw JSON to user."""
    stripped = response.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        logger.error("Raw JSON in response: %s", stripped[:200])
        return PERSONALITY_TEMPLATES["error_fallback"]
    return response


async def _run_regex_path(db: Session, member, message_text: str, pii_stripped: bool) -> tuple[str, str]:
    """Execute the regex command parser path. Returns (response, intent).

    Uses module-level imports so tests can mock parse_command/execute/format_response.
    """
    command = parse_command(message_text, registry)
    if command is not None:
        command.params["_original_message"] = message_text
        command.params["_pii_stripped"] = pii_stripped
        result = execute(db, member, command)
        response = format_response(result)
        intent = f"{command.skill}.{command.action}"
        return response, intent

    if should_fallback_to_chat(message_text):
        chat_skill = registry.get("chat")
        if chat_skill is not None:
            response = await chat_skill.respond(db, member, message_text)
            return response, "chat.llm"

    return PERSONALITY_TEMPLATES["cant_understand"], "strict.unknown"


def _structured_command_available(message_text: str) -> bool:
    """Return True when the deterministic parser can handle this message."""
    return parse_command(message_text, registry) is not None


def _should_prefer_structured_path(message_text: str) -> bool:
    """Return True when we should bypass the agent and execute deterministically.

    Task flows are fully deterministic and stateful, so routing them through the
    agent can produce free-text claims or fragmented tool calls that diverge
    from the underlying DB operation.
    """
    command = parse_command(message_text, registry)
    if command is None:
        return False
    return command.skill in {"task", "system", "fact", "deploy"}


def _is_deterministic_command(message_text: str) -> bool:
    """Return True only for commands where deterministic execution is critical.

    Document queries and search fallbacks should NOT override the agent —
    the agent's document_query tool produces better results than regex matching.
    """
    command = parse_command(message_text, registry)
    if command is None:
        return False
    # Only task/system/fact/deploy are truly deterministic and should override agent
    if command.skill in {"task", "system", "fact", "deploy"}:
        return True
    # Document save is deterministic, but queries/search should go through agent
    if command.skill == "document" and command.action == "save":
        return True
    return False


async def handle_incoming_message(
    db: Session,
    phone: str,
    message_text: str | None,
    message_id: str,
    *,
    has_media: bool = False,
    media_file_path: str | None = None,
) -> str:
    """Authenticate sender and process via Agent Loop or regex fallback."""
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
        # Determine PII status for audit logging
        try:
            _, pii_records = strip_pii(message_text)
            pii_stripped = len(pii_records) > 0
        except Exception:
            logger.exception("strip_pii failed in message handler")
            pii_stripped = False

        # Media messages → deterministic document save (bypass agent loop)
        if has_media:
            command = parse_command(
                message_text, registry, has_media=True, media_file_path=media_file_path
            )
            if command is not None:
                command.params["_original_message"] = message_text
                command.params["_pii_stripped"] = pii_stripped
                result = execute(db, member, command)
                response = format_response(result)
                intent = f"{command.skill}.{command.action}"
            else:
                response = PERSONALITY_TEMPLATES["error_fallback"]
                intent = "media.unknown"
            _save_conversation(db, member.id, message_text, response, intent)
            return _sanitize_response(response)

        # Text messages → Agent Loop (or regex fallback if disabled)

        # --- Model upgrade trigger / confirmation handling ---
        from src.services.model_selector import (
            detect_upgrade_trigger,
            is_upgrade_confirmation,
            is_upgrade_decline,
            get_session_tier,
            set_session_tier,
            clear_session_tier,
            increment_normal_count,
            reset_normal_count,
            should_auto_downgrade,
            MODEL_REGISTRY,
        )
        from src.services.conversation_state import resolve_pending, set_pending_confirmation

        # Check if user is responding to a pending model upgrade offer
        pending = resolve_pending(db, member.id)
        if pending and pending.get("type") == "model_upgrade":
            if is_upgrade_confirmation(message_text):
                tier = pending["data"]["tier"]
                original_msg = pending["data"]["original_message"]
                set_session_tier(db, member.id, tier)
                logger.info("message_handler: model_upgrade_accepted member=%s tier=%s", member.name, tier)
                # Re-run the original message with the upgraded model
                message_text = original_msg
                # Fall through to agent path below
            elif is_upgrade_decline(message_text):
                clear_session_tier(db, member.id)
                response = "👍 נשאר עם המודל הרגיל. מה תרצה לעשות?"
                _save_conversation(db, member.id, message_text, response, "model_upgrade.declined")
                return response
            # If neither confirm nor decline, treat as a new message (fall through)

        # Check if this message should trigger an upgrade suggestion
        if not pending:
            trigger_name, suggested_tier, upgrade_msg = detect_upgrade_trigger(message_text)
            current_tier = get_session_tier(db, member.id)
            if trigger_name and suggested_tier:
                current_cost = MODEL_REGISTRY[current_tier].cost_tier if current_tier and current_tier in MODEL_REGISTRY else 0
                suggested_cost = MODEL_REGISTRY[suggested_tier].cost_tier if suggested_tier in MODEL_REGISTRY else 0
                if current_cost < suggested_cost:
                    set_pending_confirmation(
                        db, member.id,
                        action_type="model_upgrade",
                        action_data={"tier": suggested_tier, "trigger": trigger_name, "original_message": message_text},
                    )
                    _save_conversation(db, member.id, message_text, upgrade_msg, f"model_upgrade.suggest.{trigger_name}")
                    return upgrade_msg

        # --- Auto-downgrade: track consecutive normal messages ---
        session_tier = get_session_tier(db, member.id)
        if session_tier:
            trigger_name_check, _, _ = detect_upgrade_trigger(message_text)
            if trigger_name_check:
                reset_normal_count(db, member.id)
            else:
                increment_normal_count(db, member.id)
                if should_auto_downgrade(db, member.id):
                    clear_session_tier(db, member.id)
                    reset_normal_count(db, member.id)
                    logger.info("message_handler: auto_downgrade member=%s", member.name)

        if _should_prefer_structured_path(message_text):
            response, intent = await _run_regex_path(db, member, message_text, pii_stripped)
            logger.info(
                "message_handler: preferred_structured_path member=%s skill_message=%s",
                member.name,
                message_text[:120],
            )
        elif AGENT_ENABLED:
            from src.services.agent_loop import run as agent_run
            agent_result = await agent_run(db, member, message_text)

            if agent_result.fallback_used:
                # Agent fell back to regex — re-run regex path using module-level mocks
                response, intent = await _run_regex_path(db, member, message_text, pii_stripped)
                logger.info(
                    "message_handler: regex_fallback_used member=%s", member.name,
                )
            else:
                tool = agent_result.tool_name
                if tool is None and _is_deterministic_command(message_text):
                    # If the LLM answered in free text for a command we can handle
                    # deterministically, prefer the structured path so actions are
                    # actually executed instead of only described.
                    response, intent = await _run_regex_path(db, member, message_text, pii_stripped)
                    logger.warning(
                        "message_handler: forced_structured_fallback member=%s text=%s",
                        member.name,
                        message_text[:120],
                    )
                else:
                    response = agent_result.response or ""
                    intent = f"agent.{tool}" if tool else "agent.chat"
                    logger.info(
                        "message_handler: agent_response member=%s intent=%s iterations=%d",
                        member.name, intent, agent_result.iterations,
                    )
                    # Warn when agent returns free text for a documents intent
                    if tool is None:
                        try:
                            from src.engine.tool_router import classify
                            detected_intent, _ = classify(message_text)
                            if detected_intent == "documents":
                                logger.warning(
                                    "message_handler: agent_returned_free_text_for_documents member=%s text=%s",
                                    member.name, message_text[:100],
                                )
                        except Exception:
                            pass
        else:
            # AGENT_ENABLED=false — use regex path directly
            logger.info("message_handler: agent_disabled using regex fallback member=%s", member.name)
            response, intent = await _run_regex_path(db, member, message_text, pii_stripped)

        # Guard against empty/None responses
        if not response or not response.strip():
            logger.error("Empty response for: %s", message_text[:100])
            response = PERSONALITY_TEMPLATES["error_fallback"]

        response = _sanitize_response(response)
        logger.info(
            "message_handler: response_ready member_id=%s intent=%s response_len=%d",
            member.id, intent, len(response),
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
