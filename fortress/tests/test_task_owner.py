"""Unit tests for task owner resolution and created_by assignment."""

import logging
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.services.workflow_engine import (
    WorkflowState,
    _resolve_member_by_name,
    task_create_node,
)


def _make_state(**overrides) -> WorkflowState:
    member = MagicMock()
    member.id = uuid4()
    member.name = "TestUser"
    state: WorkflowState = {
        "db": MagicMock(),
        "member": member,
        "phone": "0501234567",
        "message_text": "test message",
        "has_media": False,
        "media_file_path": None,
        "intent": "create_task",
        "permission_granted": True,
        "memories": [],
        "response": "",
        "error": None,
        "task_data": None,
        "from_unified": True,
        "delete_target": None,
    }
    state.update(overrides)
    return state


def _mock_db_no_duplicate():
    """Return a mock DB where query chains return None (no duplicate, no member)."""
    db = MagicMock()
    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.first.return_value = None
    db.query.return_value = mock_query
    return db


# ── _resolve_member_by_name ──────────────────────────────────────


def test_resolve_member_exact_match() -> None:
    """Exact name match returns member ID."""
    db = MagicMock()
    member = MagicMock()
    member.id = uuid4()
    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.first.return_value = member
    db.query.return_value = mock_query
    result = _resolve_member_by_name(db, "שגב")
    assert result == member.id


def test_resolve_member_no_match() -> None:
    """No match returns None."""
    db = _mock_db_no_duplicate()
    result = _resolve_member_by_name(db, "אין כזה")
    assert result is None


def test_resolve_member_case_insensitive() -> None:
    """Case-insensitive match returns member ID."""
    db = MagicMock()
    member = MagicMock()
    member.id = uuid4()
    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.first.return_value = member
    db.query.return_value = mock_query
    result = _resolve_member_by_name(db, "Test")
    assert result == member.id


# ── Fallback to sender ID ───────────────────────────────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.create_task")
async def test_no_match_falls_back_to_sender(mock_create) -> None:
    """When assigned_to name doesn't match, task is assigned to sender."""
    db = _mock_db_no_duplicate()
    state = _make_state(
        db=db,
        task_data={"title": "לקנות חלב", "assigned_to": "אין כזה", "priority": "normal"},
    )
    await task_create_node(state)
    mock_create.assert_called_once()
    call_kwargs = mock_create.call_args
    assert call_kwargs.kwargs["assigned_to"] == state["member"].id


# ── created_by always set to sender ─────────────────────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.create_task")
async def test_created_by_always_sender(mock_create) -> None:
    """created_by is always the sender's member ID."""
    db = _mock_db_no_duplicate()
    state = _make_state(
        db=db,
        task_data={"title": "לקנות חלב", "priority": "normal"},
    )
    await task_create_node(state)
    mock_create.assert_called_once()
    assert mock_create.call_args[0][2] == state["member"].id


# ── assigned_to resolved from task_data ──────────────────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine._resolve_member_by_name")
@patch("src.services.workflow_engine.create_task")
async def test_assigned_to_resolved_from_name(mock_create, mock_resolve) -> None:
    """assigned_to name in task_data is resolved to member UUID."""
    resolved_id = uuid4()
    mock_resolve.return_value = resolved_id
    db = _mock_db_no_duplicate()
    state = _make_state(
        db=db,
        task_data={"title": "לקנות חלב", "assigned_to": "שגב", "priority": "normal"},
    )
    await task_create_node(state)
    mock_create.assert_called_once()
    assert mock_create.call_args.kwargs["assigned_to"] == resolved_id


# ── Warning logged when name doesn't match ───────────────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.create_task")
async def test_warning_logged_on_no_match(mock_create, caplog) -> None:
    """Warning is logged when assigned_to name doesn't match any member."""
    db = _mock_db_no_duplicate()
    state = _make_state(
        db=db,
        task_data={"title": "לקנות חלב", "assigned_to": "אין כזה", "priority": "normal"},
    )
    with caplog.at_level(logging.WARNING, logger="src.services.workflow_engine"):
        await task_create_node(state)
    assert any("not found" in r.message for r in caplog.records)
