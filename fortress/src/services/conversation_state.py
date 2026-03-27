"""Fortress 2.0 conversation state service — per-member conversational context."""

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from src.models.schema import ConversationState

logger = logging.getLogger(__name__)


def get_state(db: Session, member_id: UUID) -> ConversationState:
    """Return the conversation state for a member, creating one if it doesn't exist."""
    state = (
        db.query(ConversationState)
        .filter(ConversationState.family_member_id == member_id)
        .first()
    )
    if state is not None:
        return state

    state = ConversationState(family_member_id=member_id)
    db.add(state)
    db.flush()
    return state


def update_state(
    db: Session,
    member_id: UUID,
    intent: str | None = None,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    action: str | None = None,
    pending_confirmation: bool = False,
    pending_action: dict | None = None,
    context: dict | None = None,
) -> ConversationState:
    """Partial update — only set non-None fields. Always bumps updated_at."""
    state = get_state(db, member_id)

    if intent is not None:
        state.last_intent = intent
    if entity_type is not None:
        state.last_entity_type = entity_type
    if entity_id is not None:
        state.last_entity_id = entity_id
    if action is not None:
        state.last_action = action
    if context is not None:
        state.context = context

    # Only update pending_confirmation if explicitly passed as True,
    # or if pending_action is also being set — never silently reset it
    if pending_confirmation or pending_action is not None:
        state.pending_confirmation = pending_confirmation
    if pending_action is not None:
        state.pending_action = pending_action

    state.updated_at = datetime.now(timezone.utc)
    db.flush()
    return state


def clear_state(db: Session, member_id: UUID) -> None:
    """Reset all mutable fields to defaults."""
    state = get_state(db, member_id)
    state.last_intent = None
    state.last_entity_type = None
    state.last_entity_id = None
    state.last_action = None
    state.pending_confirmation = False
    state.pending_action = None
    state.context = {}
    state.updated_at = datetime.now(timezone.utc)
    db.flush()


def set_pending_confirmation(
    db: Session, member_id: UUID, action_type: str, action_data: dict
) -> None:
    """Set pending_confirmation=True and store the action details."""
    logger.info(
        "Setting pending: member=%s type=%s data_keys=%s",
        member_id, action_type, list(action_data.keys()),
    )
    state = get_state(db, member_id)
    state.pending_confirmation = True
    state.pending_action = {"type": action_type, "data": action_data}
    state.updated_at = datetime.now(timezone.utc)
    db.flush()


def resolve_pending(db: Session, member_id: UUID) -> dict | None:
    """Return pending_action and clear pending state, or None if nothing pending."""
    state = get_state(db, member_id)
    logger.info(
        "Resolving pending: member=%s pending=%s type=%s",
        member_id, state.pending_confirmation,
        state.pending_action.get("type") if state.pending_action else None,
    )
    if not state.pending_confirmation:
        return None

    pending = state.pending_action
    state.pending_confirmation = False
    state.pending_action = None
    state.updated_at = datetime.now(timezone.utc)
    db.flush()
    return pending
