"""Fortress 2.0 Memory Service — save, load, filter, and expire memories."""

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from src.models.schema import Memory, MemoryExclusion
from src.prompts.system_prompts import MEMORY_EXTRACTOR

logger = logging.getLogger(__name__)

# Expiration offsets by memory type
EXPIRATION_DAYS: dict[str, int | None] = {
    "short": 7,
    "medium": 90,
    "long": 365,
    "permanent": None,
}


def check_exclusion(
    db: Session,
    content: str,
    family_member_id: UUID | None = None,
) -> bool:
    """Check if content matches any active exclusion pattern.

    Returns True if the content should be EXCLUDED (not saved).
    """
    # Fetch global exclusions (family_member_id IS NULL) plus member-specific ones
    filters = [
        MemoryExclusion.is_active == True,  # noqa: E712
    ]
    if family_member_id is not None:
        filters.append(
            or_(
                MemoryExclusion.family_member_id.is_(None),
                MemoryExclusion.family_member_id == family_member_id,
            )
        )
    else:
        filters.append(MemoryExclusion.family_member_id.is_(None))

    exclusions = db.query(MemoryExclusion).filter(and_(*filters)).all()

    for exc in exclusions:
        if exc.exclusion_type == "keyword":
            if exc.pattern.lower() in content.lower():
                return True
        elif exc.exclusion_type == "regex":
            try:
                if re.search(exc.pattern, content):
                    return True
            except re.error:
                logger.warning("Invalid regex pattern in exclusion %s: %s", exc.id, exc.pattern)
        # "category" type: skip (not used for content matching)

    return False


async def save_memory(
    db: Session,
    family_member_id: UUID,
    content: str,
    category: str,
    memory_type: str,
    source: str = "conversation",
    confidence: float = 1.0,
    metadata: dict | None = None,
) -> Memory | None:
    """Create a Memory record after passing exclusion checks.

    Returns the Memory object, or None if the content is excluded.
    """
    if check_exclusion(db, content, family_member_id):
        logger.info("Memory excluded for member %s: %s", family_member_id, content[:50])
        return None

    # Calculate expiration
    days = EXPIRATION_DAYS.get(memory_type)
    expires_at = (
        datetime.now(timezone.utc) + timedelta(days=days) if days is not None else None
    )

    memory = Memory(
        family_member_id=family_member_id,
        content=content,
        category=category,
        memory_type=memory_type,
        expires_at=expires_at,
        source=source,
        confidence=confidence,
        memory_metadata=metadata or {},
    )
    db.add(memory)
    db.flush()
    return memory


def load_memories(
    db: Session,
    family_member_id: UUID,
    limit: int = 20,
) -> list[Memory]:
    """Return active, non-expired memories for a family member.

    Orders by last_accessed_at DESC NULLS LAST, then created_at DESC.
    Updates last_accessed_at and increments access_count for returned memories.
    """
    now = datetime.now(timezone.utc)

    memories = (
        db.query(Memory)
        .filter(
            Memory.family_member_id == family_member_id,
            Memory.is_active == True,  # noqa: E712
            or_(Memory.expires_at.is_(None), Memory.expires_at > now),
        )
        .order_by(
            Memory.last_accessed_at.desc().nulls_last(),
            Memory.created_at.desc(),
        )
        .limit(limit)
        .all()
    )

    # Update access tracking
    for mem in memories:
        mem.last_accessed_at = now
        mem.access_count = (mem.access_count or 0) + 1
    db.flush()

    return memories


def cleanup_expired(db: Session) -> int:
    """Delete memories whose expires_at is in the past.

    Returns the count of deleted records.
    """
    now = datetime.now(timezone.utc)
    count = (
        db.query(Memory)
        .filter(Memory.expires_at.isnot(None), Memory.expires_at <= now)
        .delete(synchronize_session="fetch")
    )
    db.flush()
    return count


async def extract_memories_from_message(
    db: Session,
    family_member_id: UUID,
    message_in: str,
    message_out: str,
    bedrock: "BedrockClient",
) -> list[Memory]:
    """Use Bedrock to extract facts from a conversation exchange and save them.

    Returns a list of saved Memory objects (may be empty).
    """
    from src.services.bedrock_client import BedrockClient  # noqa: F811

    prompt = (
        f"User message: {message_in}\n"
        f"Assistant response: {message_out}"
    )
    raw = await bedrock.generate(prompt=prompt, system_prompt=MEMORY_EXTRACTOR)

    try:
        facts = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Memory extraction returned invalid JSON: %s", raw[:200])
        return []

    if not isinstance(facts, list):
        logger.warning("Memory extraction did not return a list: %s", type(facts).__name__)
        return []

    saved: list[Memory] = []
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        content = fact.get("content", "").strip()
        if not content:
            continue

        memory = await save_memory(
            db,
            family_member_id=family_member_id,
            content=content,
            category=fact.get("category", "context"),
            memory_type=fact.get("memory_type", "short"),
            source="conversation",
            confidence=float(fact.get("confidence", 1.0)),
        )
        if memory is not None:
            saved.append(memory)

    return saved
