"""Fortress Agent Loop — LLM-based routing with tool calling.

Replaces the regex command parser with an LLM agent that:
1. Assembles a system prompt (SOUL.md + time + user + memories)
2. Loads recent conversation history
3. Calls Bedrock with tool schemas
4. Executes tool calls in a loop until a text response is returned
5. Falls back to the regex parser on Bedrock errors
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from src.config import (
    AGENT_HISTORY_DEPTH,
    AGENT_MAX_TOOL_ITERATIONS,
    AGENT_MODEL_TIER,
    SOUL_MD_PATH,
)
from src.engine.tool_executor import execute_tool
from src.engine.tool_registry import get_tool_schemas
from src.models.schema import Conversation, FamilyMember
from src.services.bedrock_client import BedrockClient, BedrockError
from src.utils.time_context import format_time_for_prompt

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    """Outcome of an agent loop invocation."""
    response: str
    tool_name: str | None = None   # last tool used (for intent logging)
    iterations: int = 0            # number of LLM calls made
    fallback_used: bool = False    # whether regex fallback was triggered


# ---------------------------------------------------------------------------
# System prompt assembly
# ---------------------------------------------------------------------------

def _load_soul_md() -> str:
    """Load SOUL.md personality file."""
    try:
        with open(SOUL_MD_PATH, encoding="utf-8") as f:
            return f.read().strip()
    except Exception as exc:
        logger.warning("agent_loop: failed to load SOUL.md path=%s error=%s", SOUL_MD_PATH, exc)
        return "אתה פורטרס, עוזר משפחתי. תמיד ענה בעברית."


def _load_memories_text(db: Session, member_id: UUID) -> str:
    """Load active memories for the member as a formatted string."""
    try:
        from src.services.memory_service import load_memories
        memories = load_memories(db, member_id, limit=10)
        if not memories:
            return ""
        lines = ["זיכרונות רלוונטיים:"]
        for mem in memories:
            lines.append(f"- {mem.content}")
        return "\n".join(lines)
    except Exception as exc:
        logger.warning("agent_loop: failed to load memories member=%s error=%s", member_id, exc)
        return ""


def build_system_prompt(db: Session, member: FamilyMember) -> str:
    """Assemble the full system prompt for the agent."""
    soul = _load_soul_md()
    time_ctx = format_time_for_prompt()
    memories = _load_memories_text(db, member.id)

    parts = [soul, "", time_ctx, f"שם המשתמש: {member.name}"]
    if memories:
        parts.append("")
        parts.append(memories)

    parts += [
        "",
        "## הוראות לסוכן",
        "- תמיד ענה בעברית",
        "- השתמש רק בכלים שמוגדרים ברשימת הכלים — אל תמציא שמות כלים חדשים",
        "- כשהמשתמש משתף מידע לשמירה (מתכון, נתון פיננסי, הערה, רשימה) — קרא לכלי save_text",
        "- כשהמשתמש שואל שאלה על מסמך — קרא לכלי document_query",
        "- כשהמשתמש מבקש לראות מתכונים — קרא לכלי document_recipe_list",
        "- כשהמשתמש מבקש עזרה — קרא לכלי system_help",
        "- אל תמציא נתונים — השתמש בכלים כדי לקבל מידע אמיתי מהמערכת",
        "- אל תטען שביצעת פעולה מבלי לקרוא לכלי המתאים",
        "- שמור על תשובות קצרות — זה וואטסאפ, לא אימייל",
    ]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Conversation history loading
# ---------------------------------------------------------------------------

def load_conversation_history(db: Session, member_id: UUID, depth: int = AGENT_HISTORY_DEPTH) -> list[dict]:
    """Load recent conversations as Bedrock-compatible message list.

    Returns alternating user/assistant messages, oldest first.
    """
    try:
        rows = (
            db.query(Conversation)
            .filter(
                Conversation.family_member_id == member_id,
                Conversation.message_in.isnot(None),
                Conversation.message_out.isnot(None),
            )
            .order_by(Conversation.created_at.desc())
            .limit(depth)
            .all()
        )
        messages: list[dict] = []
        for row in reversed(rows):  # oldest first
            msg_in = (row.message_in or "").strip()
            msg_out = (row.message_out or "").strip()
            if msg_in:
                messages.append({"role": "user", "content": [{"text": msg_in}]})
            if msg_out:
                messages.append({"role": "assistant", "content": [{"text": msg_out}]})
        return messages
    except Exception as exc:
        logger.warning("agent_loop: failed to load history member=%s error=%s", member_id, exc)
        return []


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------

async def run(
    db: Session,
    member: FamilyMember,
    message_text: str,
) -> AgentResult:
    """Run the agent loop for a single user message.

    Returns AgentResult with the final response text.
    Falls back to regex path on Bedrock errors.
    """
    total_start = time.monotonic()

    # Build prompt and history
    system_prompt = build_system_prompt(db, member)
    history = load_conversation_history(db, member.id)

    # Append current user message
    messages = history + [{"role": "user", "content": [{"text": message_text}]}]
    tools = get_tool_schemas()

    try:
        bedrock = BedrockClient()
    except (ValueError, Exception) as exc:
        logger.warning(
            "agent_loop: bedrock_not_configured member=%s error=%s — falling back to regex",
            member.name, exc,
        )
        return await _regex_fallback(db, member, message_text)

    last_tool_name: str | None = None
    last_tool_result: str | None = None
    iterations = 0

    try:
        for iteration in range(AGENT_MAX_TOOL_ITERATIONS):
            iter_start = time.monotonic()
            iterations += 1

            response = await bedrock.converse(
                messages=messages,
                system_prompt=system_prompt,
                tools=tools,
                model=AGENT_MODEL_TIER,
                max_tokens=1024,
            )
            iter_elapsed = time.monotonic() - iter_start

            # Text response — we're done
            if response.stop_reason == "end_turn" or (response.text and not response.tool_calls):
                logger.info(
                    "agent_loop: iteration=%d text_response len=%d time=%.1fs",
                    iteration + 1, len(response.text or ""), iter_elapsed,
                )
                total_elapsed = time.monotonic() - total_start
                logger.info(
                    "agent_loop: complete member=%s iterations=%d total_time=%.1fs",
                    member.name, iterations, total_elapsed,
                )
                return AgentResult(
                    response=response.text or "",
                    tool_name=last_tool_name,
                    iterations=iterations,
                    fallback_used=False,
                )

            # Tool calls — execute each one
            if response.tool_calls:
                # Append assistant message with tool use blocks
                assistant_content = []
                if response.text:
                    assistant_content.append({"text": response.text})
                for tc in response.tool_calls:
                    assistant_content.append({
                        "toolUse": {
                            "toolUseId": tc.tool_use_id,
                            "name": tc.name,
                            "input": tc.arguments,
                        }
                    })
                messages.append({"role": "assistant", "content": assistant_content})

                # Execute tools and collect results
                tool_results_content = []
                for tc in response.tool_calls:
                    last_tool_name = tc.name
                    logger.info(
                        "agent_loop: iteration=%d tool=%s args=%s time=%.1fs",
                        iteration + 1, tc.name, tc.arguments, iter_elapsed,
                    )
                    result_text = execute_tool(
                        db, member, tc.name, tc.arguments, message_text
                    )
                    last_tool_result = result_text
                    tool_results_content.append({
                        "toolResult": {
                            "toolUseId": tc.tool_use_id,
                            "content": [{"text": result_text}],
                        }
                    })

                messages.append({"role": "user", "content": tool_results_content})
                continue

            # Unexpected: no text and no tool calls
            logger.warning("agent_loop: iteration=%d empty response stop_reason=%s", iteration + 1, response.stop_reason)
            break

        # Max iterations reached — return last tool result
        total_elapsed = time.monotonic() - total_start
        logger.warning(
            "agent_loop: max_iterations=%d reached member=%s total_time=%.1fs",
            AGENT_MAX_TOOL_ITERATIONS, member.name, total_elapsed,
        )
        return AgentResult(
            response=last_tool_result or "הגעתי למגבלת הפעולות. נסה שוב.",
            tool_name=last_tool_name,
            iterations=iterations,
            fallback_used=False,
        )

    except BedrockError as exc:
        total_elapsed = time.monotonic() - total_start
        logger.error(
            "agent_loop: bedrock_error member=%s error=%s total_time=%.1fs — falling back to regex",
            member.name, exc, total_elapsed,
        )
        return await _regex_fallback(db, member, message_text)

    except Exception as exc:
        total_elapsed = time.monotonic() - total_start
        logger.exception(
            "agent_loop: unexpected_error member=%s error=%s total_time=%.1fs — falling back to regex",
            member.name, type(exc).__name__, total_elapsed,
        )
        return await _regex_fallback(db, member, message_text)


async def _regex_fallback(db: Session, member: FamilyMember, message_text: str) -> AgentResult:
    """Signal that the regex fallback path should be used.

    Returns an AgentResult with fallback_used=True.
    The message_handler will re-run the regex path using its own module-level imports
    (which tests can mock).
    """
    return AgentResult(
        response="",  # message_handler will fill this via _run_regex_path
        tool_name=None,
        iterations=0,
        fallback_used=True,
    )
