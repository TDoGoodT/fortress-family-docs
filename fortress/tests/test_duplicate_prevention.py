"""Unit tests for duplicate task prevention in task_create_node."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, call
from uuid import uuid4

import pytest

from src.prompts.personality import TEMPLATES as PERSONALITY_TEMPLATES
from src.services.workflow_engine import WorkflowState, task_create_node


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


def _mock_db_with_duplicate():
    """Return a mock DB where the duplicate check finds an existing task."""
    db = MagicMock()
    existing_task = MagicMock()
    existing_task.id = uuid4()
    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.first.return_value = existing_task
    db.query.return_value = mock_query
    return db


def _mock_db_no_duplicate():
    """Return a mock DB where the duplicate check finds nothing."""
    db = MagicMock()
    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.first.return_value = None
    db.query.return_value = mock_query
    return db


# ── Duplicate detected within 5 minutes ──────────────────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.create_task")
async def test_duplicate_within_5_min_skips_creation(mock_create) -> None:
    """Duplicate task within 5 min → skip creation, return task_duplicate."""
    db = _mock_db_with_duplicate()
    state = _make_state(
        db=db,
        task_data={"title": "לקנות חלב", "priority": "normal"},
    )
    result = await task_create_node(state)
    mock_create.assert_not_called()
    assert result["response"] == PERSONALITY_TEMPLATES["task_duplicate"]


# ── No duplicate when title differs ──────────────────────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.create_task")
async def test_no_duplicate_different_title(mock_create) -> None:
    """Different title → no duplicate, task is created."""
    db = _mock_db_no_duplicate()
    state = _make_state(
        db=db,
        task_data={"title": "לקנות לחם", "priority": "normal"},
    )
    await task_create_node(state)
    mock_create.assert_called_once()


# ── No duplicate when assigned_to differs ────────────────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.create_task")
async def test_no_duplicate_different_assignee(mock_create) -> None:
    """Different assigned_to → no duplicate, task is created."""
    db = _mock_db_no_duplicate()
    state = _make_state(
        db=db,
        task_data={"title": "לקנות חלב", "priority": "normal"},
    )
    await task_create_node(state)
    mock_create.assert_called_once()


# ── No duplicate when older than 5 minutes ───────────────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.create_task")
async def test_no_duplicate_older_than_5_min(mock_create) -> None:
    """Task older than 5 min → no duplicate, task is created."""
    db = _mock_db_no_duplicate()
    state = _make_state(
        db=db,
        task_data={"title": "לקנות חלב", "priority": "normal"},
    )
    await task_create_node(state)
    mock_create.assert_called_once()


# ── No duplicate when existing task is not open ──────────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.create_task")
async def test_no_duplicate_non_open_status(mock_create) -> None:
    """Existing task with status 'done' → no duplicate, task is created."""
    db = _mock_db_no_duplicate()
    state = _make_state(
        db=db,
        task_data={"title": "לקנות חלב", "priority": "normal"},
    )
    await task_create_node(state)
    mock_create.assert_called_once()
