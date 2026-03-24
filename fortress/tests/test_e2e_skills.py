"""E2E integration tests — full message flow through handle_incoming_message.

Sprint R3, Requirement 1: Every skill exercised via the real pipeline
(auth → parse → execute → format → save conversation).
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.prompts.personality import TEMPLATES
from src.services.message_handler import handle_incoming_message
from src.skills.base_skill import Command, Result

from tests.conftest import _make_family_member, _make_task, _make_document, _make_bug, _make_recurring


PARENT_PHONE = "972501234567"


# ── Helpers ──────────────────────────────────────────────────────

def _parent():
    return _make_family_member(name="Segev", phone=PARENT_PHONE, role="parent")


def _permission_allow(db, phone, resource, action):
    return True


# ── 1. Task create ───────────────────────────────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_task_create_e2e(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    member = _parent()
    mock_auth.return_value = member
    mock_parse.return_value = Command(skill="task", action="create", params={"title": "לקנות חלב"})
    mock_exec.return_value = Result(success=True, message="יצרתי משימה: לקנות חלב ✅", entity_type="task", entity_id=uuid.uuid4(), action="created")
    mock_fmt.return_value = "יצרתי משימה: לקנות חלב ✅"

    result = await handle_incoming_message(mock_db, PARENT_PHONE, "משימה חדשה: לקנות חלב", "msg1")
    assert "יצרתי משימה" in result
    mock_exec.assert_called_once()


# ── 2. Task list ─────────────────────────────────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_task_list_e2e(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    member = _parent()
    mock_auth.return_value = member
    mock_parse.return_value = Command(skill="task", action="list")
    mock_exec.return_value = Result(success=True, message="📋 המשימות שלך:\n1. 🟢 לקנות חלב")
    mock_fmt.return_value = "📋 המשימות שלך:\n1. 🟢 לקנות חלב"

    result = await handle_incoming_message(mock_db, PARENT_PHONE, "משימות", "msg1")
    assert "המשימות" in result


# ── 3. Task delete + confirm ─────────────────────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_task_delete_confirm_e2e(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    member = _parent()
    mock_auth.return_value = member

    # Step 1: delete request → pending confirmation
    mock_parse.return_value = Command(skill="task", action="delete", params={"index": "1"})
    mock_exec.return_value = Result(success=True, message="למחוק את 'לקנות חלב'? (כן/לא)")
    mock_fmt.return_value = "למחוק את 'לקנות חלב'? (כן/לא)"
    r1 = await handle_incoming_message(mock_db, PARENT_PHONE, "מחק משימה 1", "msg1")
    assert "למחוק" in r1

    # Step 2: confirm → deleted
    mock_parse.return_value = Command(skill="system", action="confirm")
    mock_exec.return_value = Result(success=True, message="משימה נמחקה: לקנות חלב ✅", entity_type="task", entity_id=uuid.uuid4(), action="deleted")
    mock_fmt.return_value = "משימה נמחקה: לקנות חלב ✅"
    r2 = await handle_incoming_message(mock_db, PARENT_PHONE, "כן", "msg2")
    assert "נמחקה" in r2


# ── 4. Task delete + deny ────────────────────────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_task_delete_deny_e2e(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    member = _parent()
    mock_auth.return_value = member

    # Step 1: delete request
    mock_parse.return_value = Command(skill="task", action="delete", params={"index": "1"})
    mock_exec.return_value = Result(success=True, message="למחוק את 'לקנות חלב'? (כן/לא)")
    mock_fmt.return_value = "למחוק את 'לקנות חלב'? (כן/לא)"
    await handle_incoming_message(mock_db, PARENT_PHONE, "מחק משימה 1", "msg1")

    # Step 2: deny → cancelled
    mock_parse.return_value = Command(skill="system", action="cancel")
    mock_exec.return_value = Result(success=True, message=TEMPLATES["cancelled"])
    mock_fmt.return_value = TEMPLATES["cancelled"]
    r2 = await handle_incoming_message(mock_db, PARENT_PHONE, "לא", "msg2")
    assert "עזבתי" in r2


# ── 5. Document save (media) ─────────────────────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_document_save_e2e(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    member = _parent()
    mock_auth.return_value = member
    mock_parse.return_value = Command(skill="media", action="save", params={"media_file_path": "/data/receipt.jpg"})
    mock_exec.return_value = Result(success=True, message="שמרתי את הקובץ ✅ receipt.jpg", entity_type="document", entity_id=uuid.uuid4(), action="saved")
    mock_fmt.return_value = "שמרתי את הקובץ ✅ receipt.jpg"

    result = await handle_incoming_message(
        mock_db, PARENT_PHONE, "", "msg1", has_media=True, media_file_path="/data/receipt.jpg"
    )
    assert "שמרתי" in result


# ── 6. Greeting (no LLM) ────────────────────────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_greeting_e2e(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    member = _parent()
    mock_auth.return_value = member
    mock_parse.return_value = Command(skill="chat", action="greet")
    mock_exec.return_value = Result(success=True, message="בוקר טוב Segev! ☀️ מה נעשה היום?")
    mock_fmt.return_value = "בוקר טוב Segev! ☀️ מה נעשה היום?"

    result = await handle_incoming_message(mock_db, PARENT_PHONE, "שלום", "msg1")
    assert "Segev" in result


# ── 7. Bug report ────────────────────────────────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_bug_report_e2e(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    member = _parent()
    mock_auth.return_value = member
    mock_parse.return_value = Command(skill="bug", action="report", params={"description": "תמונה לא עובדת"})
    mock_exec.return_value = Result(success=True, message="באג נרשם ✅\n📝 תמונה לא עובדת", entity_type="bug_report", entity_id=uuid.uuid4(), action="reported")
    mock_fmt.return_value = "באג נרשם ✅\n📝 תמונה לא עובדת"

    result = await handle_incoming_message(mock_db, PARENT_PHONE, "באג: תמונה לא עובדת", "msg1")
    assert "באג נרשם" in result


# ── 8. Recurring create ──────────────────────────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_recurring_create_e2e(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    member = _parent()
    mock_auth.return_value = member
    mock_parse.return_value = Command(skill="recurring", action="create", params={"title": "ארנונה, חודשי"})
    mock_exec.return_value = Result(success=True, message="יצרתי תזכורת חוזרת: ארנונה ✅", entity_type="recurring_pattern", entity_id=uuid.uuid4(), action="created")
    mock_fmt.return_value = "יצרתי תזכורת חוזרת: ארנונה ✅"

    result = await handle_incoming_message(mock_db, PARENT_PHONE, "תזכורת חדשה: ארנונה, חודשי", "msg1")
    assert "תזכורת חוזרת" in result


# ── 9. Help ──────────────────────────────────────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_help_e2e(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    member = _parent()
    mock_auth.return_value = member
    mock_parse.return_value = Command(skill="system", action="help")
    mock_exec.return_value = Result(success=True, message="📋 פקודות זמינות:\n\n▸ ניהול משימות")
    mock_fmt.return_value = "📋 פקודות זמינות:\n\n▸ ניהול משימות"

    result = await handle_incoming_message(mock_db, PARENT_PHONE, "עזרה", "msg1")
    assert "פקודות" in result


# ── 10. Morning briefing ────────────────────────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_morning_briefing_e2e(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    member = _parent()
    mock_auth.return_value = member
    mock_parse.return_value = Command(skill="morning", action="briefing")
    mock_exec.return_value = Result(success=True, message="בוקר טוב Segev! ☀️\n\n📋 3 משימות פתוחות\n🐛 1 באגים פתוחים")
    mock_fmt.return_value = "בוקר טוב Segev! ☀️\n\n📋 3 משימות פתוחות\n🐛 1 באגים פתוחים"

    result = await handle_incoming_message(mock_db, PARENT_PHONE, "בוקר", "msg1")
    assert "בוקר טוב" in result
    assert "משימות" in result


# ── 11. LLM fallback ────────────────────────────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.registry")
@patch("src.services.message_handler.parse_command", return_value=None)
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_llm_fallback_e2e(mock_auth, mock_parse, mock_registry, mock_conv, mock_db):
    member = _parent()
    mock_auth.return_value = member
    mock_chat = MagicMock()
    mock_chat.respond = AsyncMock(return_value="אני לא בטוח מה התכוונת 🤔")
    mock_registry.get.return_value = mock_chat

    result = await handle_incoming_message(mock_db, PARENT_PHONE, "מה המצב עם הדברים?", "msg1")
    assert result == "אני לא בטוח מה התכוונת 🤔"
    mock_conv.assert_called_once()
    # Verify intent saved as chat.respond
    call_args = mock_conv.call_args[0]
    assert call_args[4] == "chat.respond"


# ── 12. Unknown phone ───────────────────────────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.get_family_member_by_phone", return_value=None)
async def test_unknown_phone_e2e(mock_auth, mock_conv, mock_db):
    result = await handle_incoming_message(mock_db, "000000000", "שלום", "msg1")
    assert result == TEMPLATES["unknown_member"]
    mock_conv.assert_called_once()
    call_args = mock_conv.call_args[0]
    assert call_args[1] is None  # member_id is None


# ── 13. Inactive member ─────────────────────────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_inactive_member_e2e(mock_auth, mock_conv, mock_db):
    mock_auth.return_value = _make_family_member(is_active=False)
    result = await handle_incoming_message(mock_db, PARENT_PHONE, "שלום", "msg1")
    assert result == TEMPLATES["inactive_member"]
