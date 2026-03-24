"""Fortress Memory Nudge — proactive memory extraction after ChatSkill responses.

After ChatSkill handles a free-form conversation, this module runs a
lightweight check to see if any facts from the exchange should be saved
as memories.  Unlike the reactive ``extract_memories_from_message`` in
``memory_service.py``, this is a *proactive* nudge that catches facts
the extraction prompt might miss.
"""

import logging

from sqlalchemy.orm import Session
from uuid import UUID

from src.services.memory_service import save_memory, check_exclusion

logger = logging.getLogger(__name__)

# Simple Hebrew patterns that indicate factual information worth saving.
# These are lightweight heuristics — no LLM call needed.
_FACT_INDICATORS: list[str] = [
    "הקוד הוא",
    "הקוד שלי",
    "הסיסמה היא",
    "המספר הוא",
    "המספר שלי",
    "הכתובת היא",
    "הכתובת שלי",
    "יום הולדת",
    "אלרגי ל",
    "אלרגית ל",
    "אני אוהב",
    "אני אוהבת",
    "אני לא אוהב",
    "אני לא אוהבת",
    "אני צריך",
    "אני צריכה",
    "תזכור ש",
    "תזכרי ש",
    "חשוב לדעת",
    "שים לב ש",
    "the code is",
    "the password is",
    "my number is",
    "remember that",
]


def should_nudge(message_in: str) -> bool:
    """Return True if the user message contains fact-like patterns worth saving.

    This is a cheap heuristic check — no LLM call.
    """
    lower = message_in.strip().lower()
    return any(indicator in message_in or indicator in lower for indicator in _FACT_INDICATORS)


async def maybe_save_nudge(
    db: Session,
    family_member_id: UUID,
    message_in: str,
    message_out: str,
) -> bool:
    """Check if the conversation exchange contains facts worth saving.

    Returns True if a memory was saved, False otherwise.
    Called by message_handler after ChatSkill responds.
    """
    if not should_nudge(message_in):
        return False

    # Don't save if content is excluded by PII/exclusion rules
    if check_exclusion(db, message_in, family_member_id):
        logger.info("Memory nudge: content excluded for member %s", family_member_id)
        return False

    # Save the user's message as a fact memory
    content = message_in.strip()
    if len(content) > 500:
        content = content[:500]

    memory = await save_memory(
        db,
        family_member_id=family_member_id,
        content=content,
        category="fact",
        memory_type="long",
        source="nudge",
        confidence=0.8,
    )

    if memory:
        logger.info("Memory nudge: saved fact for member %s: %s", family_member_id, content[:50])
        return True

    return False
