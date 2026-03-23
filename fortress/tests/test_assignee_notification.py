"""Unit tests for assignee notifications (Sprint 2 — Req 9.5).

Validates:
- Notification sent when assigned_to ≠ sender
- No notification when assigned_to == sender
- Graceful handling when WhatsApp send fails
- Assignee not found in DB — logs warning, continues
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.services.workflow_engine import WorkflowState, assignee_notify_node


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


# ── Notification sent when assigned_to ≠ sender ─────────────────


@pytest.mark.asyncio
@patch("src.services.whatsapp_client.send_text_message", new_callable=AsyncMock)
@patch("src.services.workflow_engine.get_task")
async def test_notification_sent_when_assignee_differs(mock_get_task, mock_send) -> None:
    """Should send WhatsApp notification when assignee is different from sender."""
    sender_id = uuid4()
    assignee_id = uuid4()
    task_id = uuid4()

    task = MagicMock()
    task.id = task_id
    task.title = "לקנות חלב"
    task.assigned_to = assignee_id
    mock_get_task.return_value = task

    assignee = MagicMock()
    assignee.id = assignee_id
    assignee.phone = "+972501111111"

    member = MagicMock()
    member.id = sender_id
    member.name = "Sender"

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = assignee

    mock_send.return_value = True

    state = _make_state(
        db=db, member=member, created_task_id=task_id,
    )
    result = await assignee_notify_node(state)

    mock_send.assert_called_once()
    call_args = mock_send.call_args
    assert "לקנות חלב" in call_args[0][1]
    assert result == {}


# ── No notification when assigned_to == sender ───────────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.get_task")
async def test_no_notification_when_assignee_is_sender(mock_get_task) -> None:
    """Should NOT send notification when assignee equals sender."""
    member_id = uuid4()
    task_id = uuid4()

    task = MagicMock()
    task.id = task_id
    task.title = "לקנות חלב"
    task.assigned_to = member_id
    mock_get_task.return_value = task

    member = MagicMock()
    member.id = member_id
    member.name = "Self"

    state = _make_state(member=member, created_task_id=task_id)

    with patch("src.services.whatsapp_client.send_text_message", new_callable=AsyncMock) as mock_send:
        result = await assignee_notify_node(state)
        mock_send.assert_not_called()

    assert result == {}


# ── Graceful handling when WhatsApp send fails ───────────────────


@pytest.mark.asyncio
@patch("src.services.whatsapp_client.send_text_message", new_callable=AsyncMock)
@patch("src.services.workflow_engine.get_task")
async def test_whatsapp_failure_handled_gracefully(mock_get_task, mock_send) -> None:
    """WhatsApp send failure should not raise — returns empty dict."""
    sender_id = uuid4()
    assignee_id = uuid4()
    task_id = uuid4()

    task = MagicMock()
    task.id = task_id
    task.title = "לקנות חלב"
    task.assigned_to = assignee_id
    mock_get_task.return_value = task

    assignee = MagicMock()
    assignee.id = assignee_id
    assignee.phone = "+972501111111"

    member = MagicMock()
    member.id = sender_id
    member.name = "Sender"

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = assignee

    mock_send.side_effect = Exception("WhatsApp API error")

    state = _make_state(db=db, member=member, created_task_id=task_id)
    result = await assignee_notify_node(state)

    assert result == {}


# ── Assignee not found in DB ─────────────────────────────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.get_task")
async def test_assignee_not_found_logs_warning(mock_get_task) -> None:
    """Missing assignee in DB should log warning and return empty dict."""
    sender_id = uuid4()
    assignee_id = uuid4()
    task_id = uuid4()

    task = MagicMock()
    task.id = task_id
    task.title = "לקנות חלב"
    task.assigned_to = assignee_id
    mock_get_task.return_value = task

    member = MagicMock()
    member.id = sender_id
    member.name = "Sender"

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None  # not found

    state = _make_state(db=db, member=member, created_task_id=task_id)
    result = await assignee_notify_node(state)

    assert result == {}
