"""Unit tests for the delete_task workflow — confirmation flow, routing, and edge cases."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.prompts.personality import TEMPLATES as PERSONALITY_TEMPLATES
from src.services.workflow_engine import (
    WorkflowState,
    _permission_router,
    delete_task_node,
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
        "intent": "delete_task",
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


def _make_task(title: str = "לקנות חלב", task_id=None):
    t = MagicMock()
    t.id = task_id or uuid4()
    t.title = title
    t.status = "open"
    return t


# ── Delete by task number sets pending confirmation ──────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.set_pending_confirmation")
@patch("src.services.workflow_engine.list_tasks")
async def test_delete_by_number(mock_list, mock_set_pending) -> None:
    """'מחק משימה 2' should set pending confirmation for the 2nd task."""
    tasks = [_make_task("משימה א"), _make_task("משימה ב"), _make_task("משימה ג")]
    mock_list.return_value = tasks
    state = _make_state(message_text="מחק משימה 2")
    result = await delete_task_node(state)
    mock_set_pending.assert_called_once_with(
        state["db"], state["member"].id, "delete_task",
        {"task_id": str(tasks[1].id), "title": tasks[1].title},
    )
    assert "משימה ב" in result["response"]
    assert "כן/לא" in result["response"]


# ── Delete by title match sets pending confirmation ──────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.set_pending_confirmation")
@patch("src.services.workflow_engine.list_tasks")
async def test_delete_by_title(mock_list, mock_set_pending) -> None:
    """'מחק לקנות חלב' should set pending confirmation by title match."""
    task = _make_task("לקנות חלב")
    mock_list.return_value = [task]
    state = _make_state(message_text="מחק לקנות חלב")
    result = await delete_task_node(state)
    mock_set_pending.assert_called_once_with(
        state["db"], state["member"].id, "delete_task",
        {"task_id": str(task.id), "title": task.title},
    )
    assert "לקנות חלב" in result["response"]
    assert "כן/לא" in result["response"]


# ── Ambiguous delete ─────────────────────────────────────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.list_tasks")
async def test_ambiguous_delete_shows_list(mock_list) -> None:
    """No number or title → show task_delete_which with numbered list."""
    tasks = [_make_task("משימה א"), _make_task("משימה ב")]
    mock_list.return_value = tasks
    state = _make_state(message_text="מחק")
    result = await delete_task_node(state)
    assert "איזו משימה למחוק" in result["response"]
    assert "1." in result["response"]
    assert "2." in result["response"]


# ── Task not found ───────────────────────────────────────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.list_tasks")
async def test_task_not_found_empty_list(mock_list) -> None:
    """No open tasks → task_not_found."""
    mock_list.return_value = []
    state = _make_state(message_text="מחק")
    result = await delete_task_node(state)
    assert result["response"] == PERSONALITY_TEMPLATES["task_not_found"]


# ── Task number out of range ─────────────────────────────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.list_tasks")
async def test_task_number_out_of_range(mock_list) -> None:
    """Number exceeding task count → task_not_found."""
    mock_list.return_value = [_make_task("משימה א")]
    state = _make_state(message_text="מחק משימה 5")
    result = await delete_task_node(state)
    assert result["response"] == PERSONALITY_TEMPLATES["task_not_found"]


# ── set_pending_confirmation is used (not direct archive) ────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.set_pending_confirmation")
@patch("src.services.workflow_engine.list_tasks")
async def test_uses_pending_not_direct_archive(mock_list, mock_set_pending) -> None:
    """Deletion sets pending confirmation, not direct archive."""
    task = _make_task("test")
    mock_list.return_value = [task]
    state = _make_state(message_text="מחק משימה 1")
    result = await delete_task_node(state)
    mock_set_pending.assert_called_once()
    # Confirm the response is a confirmation prompt
    assert "כן/לא" in result["response"]


# ── Permission router routes delete_task correctly ───────────────


def test_permission_router_routes_delete_task() -> None:
    """granted + delete_task → delete_task_node."""
    state = _make_state(permission_granted=True, intent="delete_task")
    assert _permission_router(state) == "delete_task_node"
