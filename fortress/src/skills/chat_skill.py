"""Fortress Skills Engine — ChatSkill: greetings and free-form LLM conversation."""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from sqlalchemy.orm import Session

from src.config import OPENROUTER_API_KEY
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
from src.services.openrouter_client import OpenRouterClient
from src.services.pii_guard import restore_pii, strip_pii
from src.skills.base_skill import BaseSkill, Command, Result
from src.utils.time_context import format_time_for_prompt, get_time_context

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sensitivity / routing (inlined from routing_policy.py)
# ---------------------------------------------------------------------------

_SENSITIVITY_MAP: dict[str, str] = {
    "greeting": "low",
    "needs_llm": "medium",
    "ask_question": "high",
    "unknown": "medium",
}

_ROUTE_MAP: dict[str, list[str]] = {
    "low": ["openrouter", "bedrock", "ollama"],
    "medium": ["openrouter", "bedrock", "ollama"],
    "high": ["bedrock", "ollama"],
}


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
        Uses inlined dispatch (Bedrock primary, OpenRouter fallback, Ollama last).
        Returns the response string, or error_fallback template if all LLM calls fail.
        """
        try:
            # Strip PII before building the LLM prompt
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

            # Restore PII in the LLM response
            if pii_records:
                raw = restore_pii(raw, pii_records)

            return raw

        except Exception:
            logger.exception("ChatSkill.respond failed for member %s", member.name)
            return TEMPLATES["error_fallback"]

    # ------------------------------------------------------------------
    # LLM dispatch — inlined from model_dispatch.py + routing_policy.py
    # ------------------------------------------------------------------

    async def _dispatch_llm(
        self,
        prompt: str,
        system_prompt: str,
        intent: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Try providers in routing order until one succeeds.

        Returns HEBREW_FALLBACK if all fail.
        """
        route = self._get_provider_order(intent)
        start = time.monotonic()

        bedrock = BedrockClient()
        openrouter = OpenRouterClient()
        ollama = OllamaClient()

        for provider in route:
            try:
                result = await self._try_provider(
                    provider, prompt, system_prompt, intent,
                    bedrock=bedrock, openrouter=openrouter, ollama=ollama,
                )
                if self._is_valid_response(result):
                    elapsed = time.monotonic() - start
                    logger.info(
                        "Dispatch: intent=%s provider=%s time=%.1fs",
                        intent, provider, elapsed,
                    )
                    return result
                logger.warning(
                    "Dispatch: intent=%s provider=%s returned fallback, trying next",
                    intent, provider,
                )
            except Exception as exc:
                logger.error(
                    "Dispatch: intent=%s provider=%s error=%s: %s",
                    intent, provider, type(exc).__name__, exc,
                )

        elapsed = time.monotonic() - start
        logger.error(
            "Dispatch: intent=%s all providers failed time=%.1fs",
            intent, elapsed,
        )
        return HEBREW_FALLBACK

    @staticmethod
    def _get_provider_order(intent: str) -> list[str]:
        """Return ordered provider list based on intent sensitivity."""
        sensitivity = _SENSITIVITY_MAP.get(intent, "high")
        return list(_ROUTE_MAP[sensitivity])

    @staticmethod
    def _is_valid_response(result: str) -> bool:
        """Check if LLM response is usable."""
        if not result or not result.strip():
            return False
        if result == HEBREW_FALLBACK:
            return False
        if len(result.strip()) < 2:
            return False
        return True

    async def _try_provider(
        self,
        provider: str,
        prompt: str,
        system_prompt: str,
        intent: str,
        *,
        bedrock: BedrockClient,
        openrouter: OpenRouterClient,
        ollama: OllamaClient,
    ) -> str:
        """Attempt generation with a single provider."""
        if provider == "openrouter":
            if not OPENROUTER_API_KEY:
                logger.info("Dispatch: skipping openrouter (no API key)")
                return HEBREW_FALLBACK
            return await openrouter.generate(prompt, system_prompt)

        if provider == "bedrock":
            model = "sonnet" if intent == "ask_question" else "haiku"
            return await bedrock.generate(prompt, system_prompt, model=model)

        if provider == "ollama":
            return await ollama.generate(prompt, system_prompt)

        logger.error("Dispatch: unknown provider=%s", provider)
        return HEBREW_FALLBACK
