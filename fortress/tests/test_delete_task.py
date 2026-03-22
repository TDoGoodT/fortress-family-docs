"""Unit tests for the delete_task workflow — soft-delete, routing, and edge cases."""

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
    }
    state.update(overrides)
    return state


def _make_task(title: str = "לקנות חלב", task_id=None):
    t = MagicMock()
    t.id = task_id or uuid4()
    t.title = title
    t.status = "open"
    return t


# ── Delete by task number ────────────────────────────────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.archive_task")
@patch("src.services.workflow_engine.list_tasks")
async def test_delete_by_number(mock_list, mock_archive) -> None:
    """'מחק משימה 2' should archive the 2nd task in the list."""
    tasks = [_make_task("משימה א"), _make_task("משימה ב"), _make_task("משימה ג")]
    mock_list.return_value = tasks
    mock_archive.return_value = tasks[1]
    state = _make_state(message_text="מחק משימה 2")
    result = await delete_task_node(state)
    mock_archive.assert_called_once_with(state["db"], tasks[1].id)
    assert "משימה ב" in result["response"]


# ── Delete by title match ────────────────────────────────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.archive_task")
@patch("src.services.workflow_engine.list_tasks")
async def test_delete_by_title(mock_list, mock_archive) -> None:
    """'מחק לקנות חלב' should find and archive by case-insensitive title."""
    task = _make_task("לקנות חלב")
    mock_list.return_value = [task]
    mock_archive.return_value = task
    state = _make_state(message_text="מחק לקנות חלב")
    result = await delete_task_node(state)
    mock_archive.assert_called_once_with(state["db"], task.id)
    assert "לקנות חלב" in result["response"]


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


# ── archive_task is used (not complete_task or DELETE) ───────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.archive_task")
@patch("src.services.workflow_engine.list_tasks")
async def test_uses_archive_not_complete(mock_list, mock_archive) -> None:
    """Deletion uses archive_task, not complete_task."""
    task = _make_task("test")
    mock_list.return_value = [task]
    mock_archive.return_value = task
    state = _make_state(message_text="מחק משימה 1")
    await delete_task_node(state)
    mock_archive.assert_called_once()


# ── Permission router routes delete_task correctly ───────────────


def test_permission_router_routes_delete_task() -> None:
    """granted + delete_task → delete_task_node."""
    state = _make_state(permission_granted=True, intent="delete_task")
    assert _permission_router(state) == "delete_task_node"
