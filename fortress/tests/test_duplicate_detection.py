"""Unit tests for smarter duplicate detection (Sprint 2 — Req 9.6).

Validates:
- Exact duplicate (case-insensitive) → rejected with task_duplicate
- Substring similarity → confirmation with task_similar_exists
- Normalized (prefix-stripped ל/ה) similarity → confirmation
- No match → task created successfully
- confirmation_check_node handles type="create_task_similar" — creates on "כן"
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.prompts.personality import TEMPLATES as PERSONALITY_TEMPLATES
from src.services.workflow_engine import (
    WorkflowState,
    task_create_node,
    confirmation_check_node,
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
        "conv_state": None,
        "time_context": "",
        "state_context": "",
        "created_task_id": None,
        "deleted_task_id": None,
        "listed_tasks": [],
        "created_recurring_id": None,
    }
    state.update(overrides)
    return state


def _make_conv_state(pending=False, pending_action=None, last_intent=None):
    cs = MagicMock()
    cs.pending_confirmation = pending
    cs.pending_action = pending_action
    cs.last_intent = last_intent
    cs.last_entity_type = None
    cs.last_action = None
    cs.context = {}
    return cs


def _mock_db_with_open_tasks(tasks):
    """Return a mock DB that returns given tasks for open task query."""
    db = MagicMock()
    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.first.return_value = None  # name resolution returns None
    mock_query.all.return_value = tasks
    db.query.return_value = mock_query
    return db


def _make_task(title):
    t = MagicMock()
    t.id = uuid4()
    t.title = title
    t.status = "open"
    return t


# ── Exact duplicate (case-insensitive) → rejected ────────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.create_task")
async def test_exact_duplicate_rejected(mock_create) -> None:
    """Exact title match (case-insensitive) should reject with task_duplicate."""
    existing = _make_task("לקנות חלב")
    db = _mock_db_with_open_tasks([existing])

    state = _make_state(
        db=db,
        task_data={"title": "לקנות חלב", "priority": "normal"},
    )
    result = await task_create_node(state)

    mock_create.assert_not_called()
    assert result["response"] == PERSONALITY_TEMPLATES["task_duplicate"]


@pytest.mark.asyncio
@patch("src.services.workflow_engine.create_task")
async def test_exact_duplicate_case_insensitive(mock_create) -> None:
    """Case difference should still be detected as exact duplicate."""
    existing = _make_task("Buy Milk")
    db = _mock_db_with_open_tasks([existing])

    state = _make_state(
        db=db,
        task_data={"title": "buy milk", "priority": "normal"},
    )
    result = await task_create_node(state)

    mock_create.assert_not_called()
    assert result["response"] == PERSONALITY_TEMPLATES["task_duplicate"]


# ── Substring similarity → confirmation ──────────────────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.set_pending_confirmation")
@patch("src.services.workflow_engine.create_task")
async def test_substring_similarity_asks_confirmation(mock_create, mock_set_pending) -> None:
    """Substring match should ask for confirmation with task_similar_exists."""
    existing = _make_task("לקנות חלב ולחם")
    db = _mock_db_with_open_tasks([existing])

    state = _make_state(
        db=db,
        task_data={"title": "לקנות חלב", "priority": "normal"},
    )
    result = await task_create_node(state)

    mock_create.assert_not_called()
    mock_set_pending.assert_called_once()
    assert "לקנות חלב ולחם" in result["response"]
    assert "לקנות חלב" in result["response"]


# ── Normalized (prefix-stripped) similarity → confirmation ────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.set_pending_confirmation")
@patch("src.services.workflow_engine.create_task")
async def test_normalized_prefix_stripped_similarity(mock_create, mock_set_pending) -> None:
    """Stripping Hebrew prefixes ל/ה should detect similarity."""
    # "הקניות" normalizes to "קניות", "לקניות" normalizes to "קניות"
    # Neither is a substring of the other, so only normalized check catches it
    existing = _make_task("הקניות")
    db = _mock_db_with_open_tasks([existing])

    state = _make_state(
        db=db,
        task_data={"title": "לקניות", "priority": "normal"},
    )
    result = await task_create_node(state)

    mock_create.assert_not_called()
    mock_set_pending.assert_called_once()
    assert "task_similar_exists" in PERSONALITY_TEMPLATES
    assert result["response"] != PERSONALITY_TEMPLATES["task_duplicate"]


# ── No match → task created successfully ─────────────────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.create_task")
async def test_no_match_creates_task(mock_create) -> None:
    """No duplicate match should create the task."""
    db = _mock_db_with_open_tasks([])
    mock_task = MagicMock()
    mock_task.id = uuid4()
    mock_create.return_value = mock_task

    state = _make_state(
        db=db,
        task_data={"title": "משימה חדשה לגמרי", "priority": "normal"},
    )
    result = await task_create_node(state)

    mock_create.assert_called_once()
    assert result.get("created_task_id") == mock_task.id


# ── confirmation_check_node: create_task_similar on "כן" ─────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.create_task")
@patch("src.services.workflow_engine.resolve_pending")
@patch("src.services.workflow_engine.get_state")
async def test_create_task_similar_confirmation(
    mock_get_state, mock_resolve, mock_create
) -> None:
    """Confirming similar task creation should create the task."""
    member_id = uuid4()
    conv_state = _make_conv_state(pending=True)
    mock_get_state.return_value = conv_state
    mock_resolve.return_value = {
        "type": "create_task_similar",
        "data": {
            "title": "לקנות חלב",
            "similar_title": "לקנות חלב ולחם",
            "assigned_to": str(member_id),
            "due_date": None,
            "category": None,
            "priority": "normal",
        },
    }
    mock_task = MagicMock()
    mock_task.id = uuid4()
    mock_create.return_value = mock_task

    member = MagicMock()
    member.id = member_id
    member.name = "TestUser"

    state = _make_state(member=member, message_text="כן")
    result = await confirmation_check_node(state)

    mock_create.assert_called_once()
    assert "לקנות חלב" in result["response"]
    assert result.get("created_task_id") == mock_task.id
