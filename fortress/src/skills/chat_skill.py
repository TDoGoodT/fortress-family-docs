"""Fortress Skills Engine — ChatSkill: greetings and free-form LLM conversation."""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from sqlalchemy.orm import Session

from src.models.schema import FamilyMember
from src.prompts.personality import TEMPLATES, get_greeting
from src.prompts.system_prompts import UNIFIED_CLASSIFY_AND_RESPOND

CHAT_SYSTEM_PROMPT = (
    "אתה פורטרס, עוזר משפחתי חכם וחם. אתה מדבר עברית בלבד.\n"
    "ענה בצורה קצרה, חמה וטבעית — זה וואטסאפ, לא מייל.\n"
    "השתמש באימוג'י במידה. פנה למשתמש בשמו הפרטי.\n"
    "אל תמציא מידע שאין לך. אם אתה לא יודע — תגיד בכנות.\n"
    "החזר טקסט רגיל בלבד — ללא JSON, ללא markdown."
)
from src.services.bedrock_client import HEBREW_FALLBACK, BedrockClient
from src.services.llm_client import OllamaClient
from src.services.memory_service import load_memories
from src.services.pii_guard import restore_pii, strip_pii
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
        Uses Bedrock (Nova Lite for chat, Haiku for complex questions), Ollama as fallback.
        Returns the response string, or error_fallback template if all LLM calls fail.
        """
        try:
            try:
                cleaned_text, pii_records = strip_pii(message_text)
            except Exception:
                logger.exception("strip_pii failed, using original text")
                cleaned_text, pii_records = message_text, []

            memories = load_memories(db, member.id)

            memory_context = ""
            if memories:
                memory_lines = [f"- {m.content}" for m in memories]
                memory_context = "\nזיכרונות רלוונטיים:\n" + "\n".join(memory_lines) + "\n"

            time_context = format_time_for_prompt()

            prompt = (
                f"{time_context}\n\n"
                f"שם המשתמש: {member.name}\n"
                f"{memory_context}\n"
                f"הודעת המשתמש: {cleaned_text}\n\n"
                f"חשוב: ענה בעברית בצורה חמה וקצרה. זה וואטסאפ."
            )

            raw = await self._dispatch_llm(
                prompt=prompt,
                system_prompt=CHAT_SYSTEM_PROMPT,
                intent="needs_llm",
            )

            if not raw or raw == HEBREW_FALLBACK:
                return TEMPLATES["error_fallback"]

            if pii_records:
                raw = restore_pii(raw, pii_records)

            return raw

        except Exception:
            logger.exception("ChatSkill.respond failed for member %s", member.name)
            return TEMPLATES["error_fallback"]

    # ------------------------------------------------------------------
    # LLM dispatch — Bedrock primary, Ollama fallback
    # ------------------------------------------------------------------

    async def _dispatch_llm(
        self,
        prompt: str,
        system_prompt: str,
        intent: str,
        context: dict[str, Any] | None = None,
        session_tier: str | None = None,
    ) -> str:
        """Try Bedrock first, fall back to Ollama if unavailable."""
        start = time.monotonic()
        from src.services.model_selector import select_model
        model = select_model(intent, session_tier=session_tier)

        # Primary: Bedrock
        try:
            bedrock = BedrockClient()
            result = await bedrock.generate(prompt, system_prompt, model=model)
            if self._is_valid_response(result):
                elapsed = time.monotonic() - start
                logger.info("Dispatch: intent=%s provider=bedrock model=%s time=%.1fs",
                            intent, model, elapsed)
                return result
            logger.warning("Dispatch: intent=%s bedrock returned fallback, trying ollama", intent)
        except Exception as exc:
            logger.error("Dispatch: intent=%s bedrock error=%s: %s",
                         intent, type(exc).__name__, exc)

        # Fallback: Ollama (local, offline)
        try:
            ollama = OllamaClient()
            result = await ollama.generate(prompt, system_prompt)
            if self._is_valid_response(result):
                elapsed = time.monotonic() - start
                logger.info("Dispatch: intent=%s provider=ollama time=%.1fs", intent, elapsed)
                return result
        except Exception as exc:
            logger.error("Dispatch: intent=%s ollama error=%s: %s",
                         intent, type(exc).__name__, exc)

        elapsed = time.monotonic() - start
        logger.error("Dispatch: intent=%s all providers failed time=%.1fs", intent, elapsed)
        return HEBREW_FALLBACK

    @staticmethod
    def _is_valid_response(result: str) -> bool:
        if not result or not result.strip():
            return False
        if result == HEBREW_FALLBACK:
            return False
        if len(result.strip()) < 2:
            return False
        return True
