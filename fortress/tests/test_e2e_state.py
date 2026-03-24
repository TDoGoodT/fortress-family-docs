"""E2E state consistency tests — ConversationState tracking across operations.

Sprint R3, Requirement 4.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from src.prompts.personality import TEMPLATES
from src.services.message_handler import handle_incoming_message
from src.skills.base_skill import Command, Result

from tests.conftest import _make_family_member


PHONE = "972501234567"


def _parent():
    return _make_family_member(name="Segev", phone=PHONE, role="parent")


# ── 1. Create task → state has entity_type, entity_id, action ───

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_state_after_task_create(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    member = _parent()
    mock_auth.return_value = member
    task_id = uuid.uuid4()
    mock_parse.return_value = Command(skill="task", action="create", params={"title": "test"})
    mock_exec.return_value = Result(success=True, message="יצרתי משימה: test ✅", entity_type="task", entity_id=task_id, action="created")
    mock_fmt.return_value = "יצרתי משימה: test ✅"

    await handle_incoming_message(mock_db, PHONE, "משימה חדשה: test", "msg1")
    # Verify execute was called with the correct command
    call_args = mock_exec.call_args
    cmd = call_args[0][2]  # third positional arg is the Command
    assert cmd.skill == "task"
    assert cmd.action == "create"


# ── 2. List tasks → state has task_list_order ───────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_state_after_task_list(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    member = _parent()
    mock_auth.return_value = member
    mock_parse.return_value = Command(skill="task", action="list")
    mock_exec.return_value = Result(success=True, message="📋 המשימות שלך:\n1. 🟢 test")
    mock_fmt.return_value = "📋 המשימות שלך:\n1. 🟢 test"

    result = await handle_incoming_message(mock_db, PHONE, "משימות", "msg1")
    assert "המשימות" in result
    mock_exec.assert_called_once()


# ── 3. "מחק 2" after list → resolves correct task ──────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_delete_resolves_index_2(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    member = _parent()
    mock_auth.return_value = member

    # List first
    mock_parse.return_value = Command(skill="task", action="list")
    mock_exec.return_value = Result(success=True, message="📋 המשימות שלך:")
    mock_fmt.return_value = "📋 המשימות שלך:"
    await handle_incoming_message(mock_db, PHONE, "משימות", "msg1")

    # Delete index 2
    mock_parse.return_value = Command(skill="task", action="delete", params={"index": "2"})
    mock_exec.return_value = Result(success=True, message="למחוק את 'task2'? (כן/לא)")
    mock_fmt.return_value = "למחוק את 'task2'? (כן/לא)"
    r = await handle_incoming_message(mock_db, PHONE, "מחק 2", "msg2")
    assert "למחוק" in r
    # Verify the command had index=2
    cmd = mock_exec.call_args[0][2]
    assert cmd.params.get("index") == "2"


# ── 4. "סיים 1" after list → resolves correct task ─────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_complete_resolves_index_1(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    member = _parent()
    mock_auth.return_value = member

    mock_parse.return_value = Command(skill="task", action="list")
    mock_exec.return_value = Result(success=True, message="📋 המשימות שלך:")
    mock_fmt.return_value = "📋 המשימות שלך:"
    await handle_incoming_message(mock_db, PHONE, "משימות", "msg1")

    mock_parse.return_value = Command(skill="task", action="complete", params={"index": "1"})
    mock_exec.return_value = Result(success=True, message="משימה הושלמה: test ✅ כל הכבוד! 🎉", entity_type="task", entity_id=uuid.uuid4(), action="completed")
    mock_fmt.return_value = "משימה הושלמה: test ✅ כל הכבוד! 🎉"
    r = await handle_incoming_message(mock_db, PHONE, "סיים 1", "msg2")
    assert "הושלמה" in r


# ── 5. "עזוב" → state cleared ───────────────────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_cancel_clears_state(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    member = _parent()
    mock_auth.return_value = member
    mock_parse.return_value = Command(skill="system", action="cancel")
    mock_exec.return_value = Result(success=True, message=TEMPLATES["cancelled"], action="cancel")
    mock_fmt.return_value = TEMPLATES["cancelled"]

    r = await handle_incoming_message(mock_db, PHONE, "עזוב", "msg1")
    assert "עזבתי" in r


# ── 6. "כן" with no pending → error ────────────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_confirm_no_pending(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    member = _parent()
    mock_auth.return_value = member
    mock_parse.return_value = Command(skill="system", action="confirm")
    mock_exec.return_value = Result(success=False, message="אין פעולה ממתינה לאישור 🤷")
    mock_fmt.return_value = "אין פעולה ממתינה לאישור 🤷"

    r = await handle_incoming_message(mock_db, PHONE, "כן", "msg1")
    assert "אין פעולה ממתינה" in r


# ── 7. Sequential: create → list → delete 1 → list → correct ───

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_sequential_create_list_delete_list(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    member = _parent()
    mock_auth.return_value = member

    # Create
    mock_parse.return_value = Command(skill="task", action="create", params={"title": "test"})
    mock_exec.return_value = Result(success=True, message="יצרתי משימה: test ✅", entity_type="task", entity_id=uuid.uuid4(), action="created")
    mock_fmt.return_value = "יצרתי משימה: test ✅"
    await handle_incoming_message(mock_db, PHONE, "משימה חדשה: test", "msg1")

    # List
    mock_parse.return_value = Command(skill="task", action="list")
    mock_exec.return_value = Result(success=True, message="📋 המשימות שלך:\n1. 🟢 test")
    mock_fmt.return_value = "📋 המשימות שלך:\n1. 🟢 test"
    await handle_incoming_message(mock_db, PHONE, "משימות", "msg2")

    # Delete 1
    mock_parse.return_value = Command(skill="task", action="delete", params={"index": "1"})
    mock_exec.return_value = Result(success=True, message="למחוק את 'test'? (כן/לא)")
    mock_fmt.return_value = "למחוק את 'test'? (כן/לא)"
    await handle_incoming_message(mock_db, PHONE, "מחק 1", "msg3")

    # Confirm
    mock_parse.return_value = Command(skill="system", action="confirm")
    mock_exec.return_value = Result(success=True, message="משימה נמחקה: test ✅", entity_type="task", entity_id=uuid.uuid4(), action="deleted")
    mock_fmt.return_value = "משימה נמחקה: test ✅"
    await handle_incoming_message(mock_db, PHONE, "כן", "msg4")

    # List again
    mock_parse.return_value = Command(skill="task", action="list")
    mock_exec.return_value = Result(success=True, message=TEMPLATES["task_list_empty"])
    mock_fmt.return_value = TEMPLATES["task_list_empty"]
    r = await handle_incoming_message(mock_db, PHONE, "משימות", "msg5")
    assert "אין משימות" in r or "יום נקי" in r
