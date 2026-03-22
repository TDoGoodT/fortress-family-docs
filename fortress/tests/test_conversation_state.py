"""Unit tests for the conversation_state service."""

from unittest.mock import MagicMock, patch, PropertyMock
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from src.models.schema import ConversationState
from src.services.conversation_state import (
    get_state,
    update_state,
    clear_state,
    set_pending_confirmation,
    resolve_pending,
)


def _make_conv_state(member_id=None, **overrides):
    """Build a mock ConversationState with sensible defaults."""
    cs = MagicMock(spec=ConversationState)
    cs.family_member_id = member_id or uuid4()
    cs.last_intent = None
    cs.last_entity_type = None
    cs.last_entity_id = None
    cs.last_action = None
    cs.pending_confirmation = False
    cs.pending_action = None
    cs.context = {}
    cs.updated_at = None
    cs.created_at = None
    for k, v in overrides.items():
        setattr(cs, k, v)
    return cs


# ── get_state ────────────────────────────────────────────────────


def test_get_state_creates_new_for_new_member() -> None:
    """get_state should create a new row when no existing state found."""
    db = MagicMock(spec=Session)
    member_id = uuid4()

    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.first.return_value = None
    db.query.return_value = mock_query

    with patch("src.services.conversation_state.ConversationState") as MockCS:
        mock_instance = MagicMock()
        MockCS.return_value = mock_instance
        result = get_state(db, member_id)

    db.add.assert_called_once_with(mock_instance)
    db.flush.assert_called_once()
    assert result == mock_instance


def test_get_state_returns_existing() -> None:
    """get_state should return existing state without creating a new one."""
    db = MagicMock(spec=Session)
    member_id = uuid4()
    existing = _make_conv_state(member_id=member_id)

    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.first.return_value = existing
    db.query.return_value = mock_query

    result = get_state(db, member_id)
    assert result is existing
    db.add.assert_not_called()


# ── update_state ─────────────────────────────────────────────────


def test_update_state_partial_update() -> None:
    """update_state should only update non-None fields."""
    db = MagicMock(spec=Session)
    member_id = uuid4()
    existing = _make_conv_state(member_id=member_id)

    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.first.return_value = existing
    db.query.return_value = mock_query

    result = update_state(db, member_id, intent="create_task", action="created")

    assert result.last_intent == "create_task"
    assert result.last_action == "created"
    # entity_type was not passed, so it should remain None (original value)
    db.flush.assert_called()


def test_update_state_does_not_overwrite_unset_fields() -> None:
    """update_state should not overwrite fields that are not provided."""
    db = MagicMock(spec=Session)
    member_id = uuid4()
    existing = _make_conv_state(
        member_id=member_id,
        last_intent="list_tasks",
        last_entity_type="task",
    )

    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.first.return_value = existing
    db.query.return_value = mock_query

    result = update_state(db, member_id, action="listed")

    # last_intent should remain unchanged since we didn't pass intent=
    assert result.last_intent == "list_tasks"
    assert result.last_entity_type == "task"
    assert result.last_action == "listed"


# ── clear_state ──────────────────────────────────────────────────


def test_clear_state_resets_all_fields() -> None:
    """clear_state should reset all mutable fields to defaults."""
    db = MagicMock(spec=Session)
    member_id = uuid4()
    existing = _make_conv_state(
        member_id=member_id,
        last_intent="create_task",
        last_entity_type="task",
        last_entity_id=uuid4(),
        last_action="created",
        pending_confirmation=True,
        pending_action={"type": "delete_task"},
        context={"task_ids": ["abc"]},
    )

    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.first.return_value = existing
    db.query.return_value = mock_query

    clear_state(db, member_id)

    assert existing.last_intent is None
    assert existing.last_entity_type is None
    assert existing.last_entity_id is None
    assert existing.last_action is None
    assert existing.pending_confirmation is False
    assert existing.pending_action is None
    assert existing.context == {}
    db.flush.assert_called()


# ── set_pending_confirmation ─────────────────────────────────────


def test_set_pending_confirmation() -> None:
    """set_pending_confirmation should set pending=True and store action data."""
    db = MagicMock(spec=Session)
    member_id = uuid4()
    existing = _make_conv_state(member_id=member_id)

    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.first.return_value = existing
    db.query.return_value = mock_query

    set_pending_confirmation(
        db, member_id, "delete_task", {"task_id": "abc", "title": "test"}
    )

    assert existing.pending_confirmation is True
    assert existing.pending_action == {
        "type": "delete_task",
        "data": {"task_id": "abc", "title": "test"},
    }
    db.flush.assert_called()


# ── resolve_pending ──────────────────────────────────────────────


def test_resolve_pending_with_pending() -> None:
    """resolve_pending should return pending_action and clear pending state."""
    db = MagicMock(spec=Session)
    member_id = uuid4()
    pending_data = {"type": "delete_task", "data": {"task_id": "abc"}}
    existing = _make_conv_state(
        member_id=member_id,
        pending_confirmation=True,
        pending_action=pending_data,
    )

    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.first.return_value = existing
    db.query.return_value = mock_query

    result = resolve_pending(db, member_id)

    assert result == pending_data
    assert existing.pending_confirmation is False
    assert existing.pending_action is None
    db.flush.assert_called()


def test_resolve_pending_without_pending() -> None:
    """resolve_pending should return None when no pending action exists."""
    db = MagicMock(spec=Session)
    member_id = uuid4()
    existing = _make_conv_state(
        member_id=member_id,
        pending_confirmation=False,
        pending_action=None,
    )

    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.first.return_value = existing
    db.query.return_value = mock_query

    result = resolve_pending(db, member_id)

    assert result is None
