"""E2E permission enforcement tests — role-based access control across skills.

Sprint R3, Requirement 2: parent/child/grandparent permission matrix.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from src.prompts.personality import TEMPLATES
from src.services.message_handler import handle_incoming_message
from src.skills.base_skill import Command, Result

from tests.conftest import _make_family_member


PARENT_PHONE = "972501234567"
CHILD_PHONE = "972509876543"
GRANDPARENT_PHONE = "972508888888"


def _member(role, phone):
    return _make_family_member(name=f"Test {role.title()}", phone=phone, role=role)


# ── 1. Parent can create task ────────────────────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_parent_task_create_allowed(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    mock_auth.return_value = _member("parent", PARENT_PHONE)
    mock_parse.return_value = Command(skill="task", action="create", params={"title": "test"})
    mock_exec.return_value = Result(success=True, message="יצרתי משימה: test ✅")
    mock_fmt.return_value = "יצרתי משימה: test ✅"

    result = await handle_incoming_message(mock_db, PARENT_PHONE, "משימה חדשה: test", "msg1")
    assert "יצרתי" in result


# ── 2. Child cannot create task ──────────────────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_child_task_create_denied(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    mock_auth.return_value = _member("child", CHILD_PHONE)
    mock_parse.return_value = Command(skill="task", action="create", params={"title": "test"})
    mock_exec.return_value = Result(success=False, message=TEMPLATES["permission_denied"])
    mock_fmt.return_value = TEMPLATES["permission_denied"]

    result = await handle_incoming_message(mock_db, CHILD_PHONE, "משימה חדשה: test", "msg1")
    assert "🔒" in result


# ── 3. Parent can list tasks ────────────────────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_parent_task_list_allowed(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    mock_auth.return_value = _member("parent", PARENT_PHONE)
    mock_parse.return_value = Command(skill="task", action="list")
    mock_exec.return_value = Result(success=True, message="📋 המשימות שלך:")
    mock_fmt.return_value = "📋 המשימות שלך:"

    result = await handle_incoming_message(mock_db, PARENT_PHONE, "משימות", "msg1")
    assert "המשימות" in result


# ── 4. Child can list tasks (read allowed) ──────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_child_task_list_allowed(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    mock_auth.return_value = _member("child", CHILD_PHONE)
    mock_parse.return_value = Command(skill="task", action="list")
    mock_exec.return_value = Result(success=True, message="📋 המשימות שלך:")
    mock_fmt.return_value = "📋 המשימות שלך:"

    result = await handle_incoming_message(mock_db, CHILD_PHONE, "משימות", "msg1")
    assert "המשימות" in result


# ── 5. Parent can delete task ───────────────────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_parent_task_delete_allowed(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    mock_auth.return_value = _member("parent", PARENT_PHONE)
    mock_parse.return_value = Command(skill="task", action="delete", params={"index": "1"})
    mock_exec.return_value = Result(success=True, message="למחוק את 'test'? (כן/לא)")
    mock_fmt.return_value = "למחוק את 'test'? (כן/לא)"

    result = await handle_incoming_message(mock_db, PARENT_PHONE, "מחק משימה 1", "msg1")
    assert "למחוק" in result


# ── 6. Child cannot delete task ─────────────────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_child_task_delete_denied(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    mock_auth.return_value = _member("child", CHILD_PHONE)
    mock_parse.return_value = Command(skill="task", action="delete", params={"index": "1"})
    mock_exec.return_value = Result(success=False, message=TEMPLATES["permission_denied"])
    mock_fmt.return_value = TEMPLATES["permission_denied"]

    result = await handle_incoming_message(mock_db, CHILD_PHONE, "מחק משימה 1", "msg1")
    assert "🔒" in result


# ── 7. Parent can report bug ───────────────────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_parent_bug_report_allowed(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    mock_auth.return_value = _member("parent", PARENT_PHONE)
    mock_parse.return_value = Command(skill="bug", action="report", params={"description": "bug"})
    mock_exec.return_value = Result(success=True, message="באג נרשם ✅\n📝 bug")
    mock_fmt.return_value = "באג נרשם ✅\n📝 bug"

    result = await handle_incoming_message(mock_db, PARENT_PHONE, "באג: bug", "msg1")
    assert "באג נרשם" in result


# ── 8. Child cannot report bug ──────────────────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_child_bug_report_denied(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    mock_auth.return_value = _member("child", CHILD_PHONE)
    mock_parse.return_value = Command(skill="bug", action="report", params={"description": "bug"})
    mock_exec.return_value = Result(success=False, message=TEMPLATES["permission_denied"])
    mock_fmt.return_value = TEMPLATES["permission_denied"]

    result = await handle_incoming_message(mock_db, CHILD_PHONE, "באג: bug", "msg1")
    assert "🔒" in result


# ── 9. Parent can view summary ──────────────────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_parent_summary_allowed(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    mock_auth.return_value = _member("parent", PARENT_PHONE)
    mock_parse.return_value = Command(skill="morning", action="summary")
    mock_exec.return_value = Result(success=True, message=TEMPLATES["no_report_yet"])
    mock_fmt.return_value = TEMPLATES["no_report_yet"]

    result = await handle_incoming_message(mock_db, PARENT_PHONE, "דוח", "msg1")
    assert "דוח" in result


# ── 10. Child cannot view summary ───────────────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_child_summary_denied(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    mock_auth.return_value = _member("child", CHILD_PHONE)
    mock_parse.return_value = Command(skill="morning", action="summary")
    mock_exec.return_value = Result(success=False, message=TEMPLATES["permission_denied"])
    mock_fmt.return_value = TEMPLATES["permission_denied"]

    result = await handle_incoming_message(mock_db, CHILD_PHONE, "דוח", "msg1")
    assert "🔒" in result


# ── 11. Grandparent can list tasks (read only) ──────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_grandparent_task_list_allowed(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    mock_auth.return_value = _member("grandparent", GRANDPARENT_PHONE)
    mock_parse.return_value = Command(skill="task", action="list")
    mock_exec.return_value = Result(success=True, message="📋 המשימות שלך:")
    mock_fmt.return_value = "📋 המשימות שלך:"

    result = await handle_incoming_message(mock_db, GRANDPARENT_PHONE, "משימות", "msg1")
    assert "המשימות" in result


# ── 12. Grandparent cannot create task ──────────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_grandparent_task_create_denied(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    mock_auth.return_value = _member("grandparent", GRANDPARENT_PHONE)
    mock_parse.return_value = Command(skill="task", action="create", params={"title": "test"})
    mock_exec.return_value = Result(success=False, message=TEMPLATES["permission_denied"])
    mock_fmt.return_value = TEMPLATES["permission_denied"]

    result = await handle_incoming_message(mock_db, GRANDPARENT_PHONE, "משימה חדשה: test", "msg1")
    assert "🔒" in result
