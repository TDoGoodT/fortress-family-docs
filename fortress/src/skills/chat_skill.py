"""Fortress Skills Engine — ChatSkill: greetings and free-form LLM conversation."""

from __future__ import annotations

import logging
import re

from sqlalchemy.orm import Session

from src.models.schema import FamilyMember
from src.prompts.personality import TEMPLATES, get_greeting
from src.prompts.system_prompts import UNIFIED_CLASSIFY_AND_RESPOND
from src.services.memory_service import load_memories
from src.services.model_dispatch import ModelDispatcher
from src.skills.base_skill import BaseSkill, Command, Result
from src.utils.time_context import format_time_for_prompt, get_time_context

logger = logging.getLogger(__name__)


class ChatSkill(BaseSkill):
    """Skill for greetings (deterministic) and free-form conversation (LLM)."""

    @property
    def name(self) -> str:
        return "chat"

    @property
    def description(self) -> str:
        return "שיחה חופשית וברכות"

    @property
    def commands(self) -> list[tuple[re.Pattern, str]]:
        return [
            (re.compile(r"^(שלום|היי|hello|בוקר טוב|ערב טוב|לילה טוב)$", re.IGNORECASE), "greet"),
        ]

    def execute(self, db: Session, member: FamilyMember, command: Command) -> Result:
        if command.action == "greet":
            return self._greet(member)
        return Result(success=False, message=TEMPLATES["error_fallback"])

    def verify(self, db: Session, result: Result) -> bool:
        return True

    def get_help(self) -> str:
        return "שלום / היי / hello — ברכה\nשיחה חופשית — כתוב מה שבא לך"

    # ------------------------------------------------------------------
    # Greet — deterministic, no LLM
    # ------------------------------------------------------------------

    def _greet(self, member: FamilyMember) -> Result:
        current_hour = get_time_context()["hour"]
        greeting = get_greeting(member.name, current_hour)
        return Result(success=True, message=greeting)

    # ------------------------------------------------------------------
    # Respond — async LLM conversation (called by message_handler)
    # ------------------------------------------------------------------

    async def respond(self, db: Session, member: FamilyMember, message_text: str) -> str:
        """Generate a free-form LLM response with personality, time, and memory context.

        Called directly by message_handler when CommandParser returns None.
        Uses ModelDispatcher (Bedrock primary, OpenRouter fallback).
        Returns the response string, or error_fallback template if all LLM calls fail.
        """
        try:
            # Load memories for context
            memories = load_memories(db, member.id)

            # Build memory context
            memory_context = ""
            if memories:
                memory_lines = [f"- {m.content}" for m in memories]
                memory_context = "\nזיכרונות רלוונטיים:\n" + "\n".join(memory_lines) + "\n"

            # Build time context
            time_context = format_time_for_prompt()

            # Build prompt (same structure as handle_with_llm in unified_handler)
            prompt = (
                f"{time_context}\n\n"
                f"שם המשתמש: {member.name}\n"
                f"{memory_context}\n"
                f"הודעת המשתמש: {message_text}\n\n"
                f"חשוב: ענה בעברית בצורה חמה וקצרה. זה וואטסאפ."
            )

            dispatcher = ModelDispatcher()
            raw = await dispatcher.dispatch(
                prompt=prompt,
                system_prompt=UNIFIED_CLASSIFY_AND_RESPOND,
                intent="needs_llm",
            )

            # If dispatcher returned the Hebrew fallback constant, treat as failure
            from src.services.bedrock_client import HEBREW_FALLBACK
            if not raw or raw == HEBREW_FALLBACK:
                return TEMPLATES["error_fallback"]

            return raw

        except Exception:
            logger.exception("ChatSkill.respond failed for member %s", member.name)
            return TEMPLATES["error_fallback"]
