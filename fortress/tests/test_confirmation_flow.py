"""Unit tests for the confirmation flow in the workflow engine."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.prompts.personality import TEMPLATES as PERSONALITY_TEMPLATES
from src.services.workflow_engine import (
    WorkflowState,
    confirmation_check_node,
    delete_task_node,
)


def _make_state(**overrides) -> WorkflowState:
    """Build a minimal WorkflowState dict with sensible defaults."""
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
        "intent": "",
        "permission_granted": False,
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
    """Build a mock ConversationState."""
    cs = MagicMock()
    cs.pending_confirmation = pending
    cs.pending_action = pending_action
    cs.last_intent = last_intent
    cs.last_entity_type = None
    cs.last_action = None
    cs.context = {}
    return cs


# ── confirmation_check_node: pending + "כן" ─────────────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.archive_task")
@patch("src.services.workflow_engine.resolve_pending")
@patch("src.services.workflow_engine.get_state")
async def test_confirm_yes_executes_delete(mock_get_state, mock_resolve, mock_archive) -> None:
    """Pending + 'כן' should execute the delete action."""
    task_id = uuid4()
    conv_state = _make_conv_state(pending=True)
    mock_get_state.return_value = conv_state
    mock_resolve.return_value = {
        "type": "delete_task",
        "data": {"task_id": str(task_id), "title": "לקנות חלב"},
    }
    mock_archive.return_value = True

    state = _make_state(message_text="כן")
    result = await confirmation_check_node(state)

    mock_archive.assert_called_once()
    assert "לקנות חלב" in result["response"]
    assert result.get("deleted_task_id") == task_id


# ── confirmation_check_node: pending + "לא" ─────────────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.clear_state")
@patch("src.services.workflow_engine.resolve_pending")
@patch("src.services.workflow_engine.get_state")
async def test_confirm_no_cancels(mock_get_state, mock_resolve, mock_clear) -> None:
    """Pending + 'לא' should cancel and return action_cancelled template."""
    conv_state = _make_conv_state(pending=True)
    mock_get_state.return_value = conv_state
    mock_resolve.return_value = {"type": "delete_task", "data": {}}

    state = _make_state(message_text="לא")
    result = await confirmation_check_node(state)

    mock_resolve.assert_called_once()
    mock_clear.assert_called_once()
    assert result["response"] == PERSONALITY_TEMPLATES["action_cancelled"]


# ── confirmation_check_node: pending + other message ─────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.get_state")
async def test_confirm_other_clears_pending(mock_get_state) -> None:
    """Pending + unrelated message should clear pending and return no response."""
    conv_state = _make_conv_state(pending=True)
    mock_get_state.return_value = conv_state

    state = _make_state(message_text="מה המשימות")
    result = await confirmation_check_node(state)

    # Pending should be cleared on the conv_state object
    assert conv_state.pending_confirmation is False
    assert conv_state.pending_action is None
    # No response set — falls through to intent_node
    assert "response" not in result or result.get("response", "") == ""


# ── confirmation_check_node: no pending ──────────────────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.get_state")
async def test_no_pending_passes_through(mock_get_state) -> None:
    """No pending confirmation should pass through without setting response."""
    conv_state = _make_conv_state(pending=False)
    mock_get_state.return_value = conv_state

    state = _make_state(message_text="שלום")
    result = await confirmation_check_node(state)

    assert "response" not in result or result.get("response", "") == ""
    assert result["conv_state"] is conv_state


# ── delete_task_node sets pending confirmation ───────────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.set_pending_confirmation")
@patch("src.services.workflow_engine.list_tasks")
async def test_delete_task_sets_pending(mock_list, mock_set_pending) -> None:
    """delete_task_node should set pending confirmation instead of direct delete."""
    task = MagicMock()
    task.id = uuid4()
    task.title = "לקנות חלב"
    task.status = "open"
    mock_list.return_value = [task]

    state = _make_state(message_text="מחק משימה 1")
    result = await delete_task_node(state)

    mock_set_pending.assert_called_once_with(
        state["db"], state["member"].id, "delete_task",
        {"task_id": str(task.id), "title": task.title},
    )
    assert "כן/לא" in result["response"]
