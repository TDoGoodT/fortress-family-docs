"""Unit tests for the verification_node in the workflow engine."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.prompts.personality import TEMPLATES as PERSONALITY_TEMPLATES
from src.services.workflow_engine import WorkflowState, verification_node


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


# ── create_task verification ─────────────────────────────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.get_task")
async def test_verification_passes_created_task_exists(mock_get_task) -> None:
    """Verification should pass when created task exists in DB."""
    task_id = uuid4()
    mock_task = MagicMock()
    mock_task.id = task_id
    mock_get_task.return_value = mock_task

    state = _make_state(intent="create_task", created_task_id=task_id)
    result = await verification_node(state)

    assert result == {}  # no error → pass


@pytest.mark.asyncio
@patch("src.services.workflow_engine.get_task")
async def test_verification_fails_created_task_not_found(mock_get_task) -> None:
    """Verification should fail when created task not found in DB."""
    task_id = uuid4()
    mock_get_task.return_value = None

    state = _make_state(intent="create_task", created_task_id=task_id)
    result = await verification_node(state)

    assert result["response"] == PERSONALITY_TEMPLATES["verification_failed"]


# ── delete_task verification ─────────────────────────────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.get_task")
async def test_verification_passes_deleted_task_archived(mock_get_task) -> None:
    """Verification should pass when deleted task has status='archived'."""
    task_id = uuid4()
    mock_task = MagicMock()
    mock_task.id = task_id
    mock_task.status = "archived"
    mock_get_task.return_value = mock_task

    state = _make_state(intent="delete_task", deleted_task_id=task_id)
    result = await verification_node(state)

    assert result == {}  # no error → pass


@pytest.mark.asyncio
@patch("src.services.workflow_engine.get_task")
async def test_verification_fails_deleted_task_not_archived(mock_get_task) -> None:
    """Verification should fail when deleted task status is not 'archived'."""
    task_id = uuid4()
    mock_task = MagicMock()
    mock_task.id = task_id
    mock_task.status = "open"
    mock_get_task.return_value = mock_task

    state = _make_state(intent="delete_task", deleted_task_id=task_id)
    result = await verification_node(state)

    assert result["response"] == PERSONALITY_TEMPLATES["verification_failed"]


# ── no task ID in state (no-op) ──────────────────────────────────


@pytest.mark.asyncio
async def test_verification_passes_no_task_id() -> None:
    """Verification should pass (no-op) when no task ID is in state."""
    state = _make_state(intent="create_task", created_task_id=None)
    result = await verification_node(state)

    assert result == {}


@pytest.mark.asyncio
async def test_verification_passes_greeting_intent() -> None:
    """Verification should pass (no-op) for non-action intents like greeting."""
    state = _make_state(intent="greeting")
    result = await verification_node(state)

    assert result == {}
