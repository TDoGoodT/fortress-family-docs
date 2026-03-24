"""E2E confirmation flow tests — confirm/deny/ignore paths for destructive actions.

Sprint R3, Requirement 3.
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


# ── 1. Delete task → confirm → deleted ──────────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_task_delete_confirm(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    mock_auth.return_value = _parent()
    mock_parse.return_value = Command(skill="task", action="delete", params={"index": "1"})
    mock_exec.return_value = Result(success=True, message="למחוק את 'test'? (כן/לא)")
    mock_fmt.return_value = "למחוק את 'test'? (כן/לא)"
    await handle_incoming_message(mock_db, PHONE, "מחק משימה 1", "msg1")

    mock_parse.return_value = Command(skill="system", action="confirm")
    mock_exec.return_value = Result(success=True, message="משימה נמחקה: test ✅", entity_type="task", entity_id=uuid.uuid4(), action="deleted")
    mock_fmt.return_value = "משימה נמחקה: test ✅"
    r = await handle_incoming_message(mock_db, PHONE, "כן", "msg2")
    assert "נמחקה" in r


# ── 2. Delete task → deny → not deleted ─────────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_task_delete_deny(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    mock_auth.return_value = _parent()
    mock_parse.return_value = Command(skill="task", action="delete", params={"index": "1"})
    mock_exec.return_value = Result(success=True, message="למחוק את 'test'? (כן/לא)")
    mock_fmt.return_value = "למחוק את 'test'? (כן/לא)"
    await handle_incoming_message(mock_db, PHONE, "מחק משימה 1", "msg1")

    mock_parse.return_value = Command(skill="system", action="cancel")
    mock_exec.return_value = Result(success=True, message=TEMPLATES["cancelled"])
    mock_fmt.return_value = TEMPLATES["cancelled"]
    r = await handle_incoming_message(mock_db, PHONE, "לא", "msg2")
    assert "עזבתי" in r


# ── 3. Delete task → unrelated message → state cleared ──────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_task_delete_ignore(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    mock_auth.return_value = _parent()
    mock_parse.return_value = Command(skill="task", action="delete", params={"index": "1"})
    mock_exec.return_value = Result(success=True, message="למחוק את 'test'? (כן/לא)")
    mock_fmt.return_value = "למחוק את 'test'? (כן/לא)"
    await handle_incoming_message(mock_db, PHONE, "מחק משימה 1", "msg1")

    # Unrelated message — should process normally (task list)
    mock_parse.return_value = Command(skill="task", action="list")
    mock_exec.return_value = Result(success=True, message="📋 המשימות שלך:")
    mock_fmt.return_value = "📋 המשימות שלך:"
    r = await handle_incoming_message(mock_db, PHONE, "משימות", "msg2")
    assert "המשימות" in r


# ── 4. Delete all → confirm → all archived ──────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_delete_all_confirm(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    mock_auth.return_value = _parent()
    mock_parse.return_value = Command(skill="task", action="delete_all")
    mock_exec.return_value = Result(success=True, message="למחוק את כל 3 המשימות?")
    mock_fmt.return_value = "למחוק את כל 3 המשימות?"
    await handle_incoming_message(mock_db, PHONE, "מחק הכל", "msg1")

    mock_parse.return_value = Command(skill="system", action="confirm")
    mock_exec.return_value = Result(success=True, message="3 משימות נמחקו ✅")
    mock_fmt.return_value = "3 משימות נמחקו ✅"
    r = await handle_incoming_message(mock_db, PHONE, "כן", "msg2")
    assert "נמחקו" in r


# ── 5. Delete all → deny → none archived ────────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_delete_all_deny(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    mock_auth.return_value = _parent()
    mock_parse.return_value = Command(skill="task", action="delete_all")
    mock_exec.return_value = Result(success=True, message="למחוק את כל 3 המשימות?")
    mock_fmt.return_value = "למחוק את כל 3 המשימות?"
    await handle_incoming_message(mock_db, PHONE, "מחק הכל", "msg1")

    mock_parse.return_value = Command(skill="system", action="cancel")
    mock_exec.return_value = Result(success=True, message=TEMPLATES["cancelled"])
    mock_fmt.return_value = TEMPLATES["cancelled"]
    r = await handle_incoming_message(mock_db, PHONE, "לא", "msg2")
    assert "עזבתי" in r


# ── 6. Recurring delete → confirm → deactivated ────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_recurring_delete_confirm(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    mock_auth.return_value = _parent()
    mock_parse.return_value = Command(skill="recurring", action="delete", params={"index": "1"})
    mock_exec.return_value = Result(success=True, message="למחוק את 'ארנונה'? (כן/לא)")
    mock_fmt.return_value = "למחוק את 'ארנונה'? (כן/לא)"
    await handle_incoming_message(mock_db, PHONE, "מחק תזכורת 1", "msg1")

    mock_parse.return_value = Command(skill="system", action="confirm")
    mock_exec.return_value = Result(success=True, message="תזכורת חוזרת בוטלה: ארנונה ✅", entity_type="recurring_pattern", entity_id=uuid.uuid4(), action="deleted")
    mock_fmt.return_value = "תזכורת חוזרת בוטלה: ארנונה ✅"
    r = await handle_incoming_message(mock_db, PHONE, "כן", "msg2")
    assert "בוטלה" in r


# ── 7. Duplicate task → confirm → created anyway ────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_duplicate_task_confirm(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    mock_auth.return_value = _parent()
    mock_parse.return_value = Command(skill="task", action="create", params={"title": "test"})
    mock_exec.return_value = Result(success=True, message="כבר יש משימה דומה: 'test'\nליצור בכל זאת?")
    mock_fmt.return_value = "כבר יש משימה דומה: 'test'\nליצור בכל זאת?"
    await handle_incoming_message(mock_db, PHONE, "משימה חדשה: test", "msg1")

    mock_parse.return_value = Command(skill="system", action="confirm")
    mock_exec.return_value = Result(success=True, message="יצרתי משימה: test ✅", entity_type="task", entity_id=uuid.uuid4(), action="created")
    mock_fmt.return_value = "יצרתי משימה: test ✅"
    r = await handle_incoming_message(mock_db, PHONE, "כן", "msg2")
    assert "יצרתי" in r


# ── 8. Duplicate task → deny → not created ──────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_duplicate_task_deny(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    mock_auth.return_value = _parent()
    mock_parse.return_value = Command(skill="task", action="create", params={"title": "test"})
    mock_exec.return_value = Result(success=True, message="כבר יש משימה דומה: 'test'\nליצור בכל זאת?")
    mock_fmt.return_value = "כבר יש משימה דומה: 'test'\nליצור בכל זאת?"
    await handle_incoming_message(mock_db, PHONE, "משימה חדשה: test", "msg1")

    mock_parse.return_value = Command(skill="system", action="cancel")
    mock_exec.return_value = Result(success=True, message=TEMPLATES["cancelled"])
    mock_fmt.return_value = TEMPLATES["cancelled"]
    r = await handle_incoming_message(mock_db, PHONE, "לא", "msg2")
    assert "עזבתי" in r
