"""Unit tests for bulk operations (Sprint 2 — Req 9.4).

Validates:
- bulk_delete_tasks/bulk_delete_range keyword detection
- bulk_delete_node with bulk_delete_tasks — lists tasks, sets pending
- bulk_delete_node with bulk_delete_range — parses range, validates bounds
- confirmation_check_node handles type="bulk_delete" — archives correct tasks
- Empty task list returns task_list_empty
- Invalid range returns task_not_found
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.prompts.personality import TEMPLATES as PERSONALITY_TEMPLATES
from src.services.intent_detector import VALID_INTENTS, detect_intent
from src.services.workflow_engine import (
    WorkflowState,
    bulk_delete_node,
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
        "intent": "bulk_delete_tasks",
        "permission_granted": True,
        "memories": [],
        "response": "",
        "error": None,
        "task_data": None,
        "from_unified": False,
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


def _make_task(title="משימה"):
    t = MagicMock()
    t.id = uuid4()
    t.title = title
    t.status = "open"
    return t


# ── Keyword detection ────────────────────────────────────────────


def test_bulk_delete_tasks_in_valid_intents() -> None:
    assert "bulk_delete_tasks" in VALID_INTENTS


def test_bulk_delete_range_in_valid_intents() -> None:
    assert "bulk_delete_range" in VALID_INTENTS


def test_detect_bulk_delete_all() -> None:
    assert detect_intent("מחק הכל", has_media=False) == "bulk_delete_tasks"


def test_detect_bulk_delete_range() -> None:
    assert detect_intent("מחק 1-5", has_media=False) == "bulk_delete_range"


# ── bulk_delete_node: bulk_delete_tasks ──────────────────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.set_pending_confirmation")
@patch("src.services.workflow_engine.list_tasks")
async def test_bulk_delete_tasks_lists_and_sets_pending(mock_list, mock_set_pending) -> None:
    """bulk_delete_tasks should list all tasks and set pending confirmation."""
    tasks = [_make_task("משימה 1"), _make_task("משימה 2")]
    mock_list.return_value = tasks

    state = _make_state(intent="bulk_delete_tasks", message_text="מחק הכל")
    result = await bulk_delete_node(state)

    mock_set_pending.assert_called_once()
    call_args = mock_set_pending.call_args
    assert call_args[0][2] == "bulk_delete"
    assert len(call_args[0][3]["task_ids"]) == 2
    assert "משימה 1" in result["response"]
    assert "משימה 2" in result["response"]


# ── bulk_delete_node: bulk_delete_range ──────────────────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.set_pending_confirmation")
@patch("src.services.workflow_engine.list_tasks")
async def test_bulk_delete_range_parses_and_sets_pending(mock_list, mock_set_pending) -> None:
    """bulk_delete_range should parse range and set pending for selected tasks."""
    tasks = [_make_task(f"משימה {i}") for i in range(1, 6)]
    mock_list.return_value = tasks

    state = _make_state(intent="bulk_delete_range", message_text="מחק 2-4")
    result = await bulk_delete_node(state)

    mock_set_pending.assert_called_once()
    call_args = mock_set_pending.call_args
    assert len(call_args[0][3]["task_ids"]) == 3  # tasks 2, 3, 4


# ── confirmation_check_node: bulk_delete confirmation ────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.archive_task")
@patch("src.services.workflow_engine.resolve_pending")
@patch("src.services.workflow_engine.get_state")
async def test_bulk_delete_confirmation_archives_tasks(
    mock_get_state, mock_resolve, mock_archive
) -> None:
    """Confirming bulk_delete should archive all listed tasks."""
    task_ids = [str(uuid4()), str(uuid4()), str(uuid4())]
    conv_state = _make_conv_state(pending=True)
    mock_get_state.return_value = conv_state
    mock_resolve.return_value = {
        "type": "bulk_delete",
        "data": {"task_ids": task_ids},
    }
    mock_archive.return_value = True

    state = _make_state(message_text="כן")
    result = await confirmation_check_node(state)

    assert mock_archive.call_count == 3
    assert "3" in result["response"]  # "3 משימות נמחקו"


# ── Empty task list returns task_list_empty ───────────────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.list_tasks")
async def test_bulk_delete_empty_task_list(mock_list) -> None:
    """No open tasks should return task_list_empty template."""
    mock_list.return_value = []
    state = _make_state(intent="bulk_delete_tasks", message_text="מחק הכל")
    result = await bulk_delete_node(state)
    assert result["response"] == PERSONALITY_TEMPLATES["task_list_empty"]


# ── Invalid range returns task_not_found ─────────────────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.list_tasks")
async def test_bulk_delete_invalid_range(mock_list) -> None:
    """Range exceeding task count should return task_not_found."""
    tasks = [_make_task("משימה 1"), _make_task("משימה 2")]
    mock_list.return_value = tasks

    state = _make_state(intent="bulk_delete_range", message_text="מחק 1-10")
    result = await bulk_delete_node(state)
    assert result["response"] == PERSONALITY_TEMPLATES["task_not_found"]
