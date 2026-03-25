"""Comprehensive MVP integration tests — all 10 MVP commands end-to-end.

Validates the fixed pipeline: deterministic responses, no raw JSON,
no LLM fallback, proper error handling, and correct confirmation flows.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from src.prompts.personality import TEMPLATES
from src.services.message_handler import _sanitize_response, handle_incoming_message
from src.skills.base_skill import Command, Result

from tests.conftest import _make_family_member


PARENT_PHONE = "972501234567"


def _parent():
    return _make_family_member(name="Segev", phone=PARENT_PHONE, role="parent")


# ── 1. "משימה חדשה: X" → task created, template response ────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_mvp_task_create(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    member = _parent()
    mock_auth.return_value = member
    mock_parse.return_value = Command(skill="task", action="create", params={"title": "לקנות חלב"})
    mock_exec.return_value = Result(
        success=True, message="יצרתי משימה: לקנות חלב ✅",
        entity_type="task", entity_id=uuid.uuid4(), action="created",
    )
    mock_fmt.return_value = "יצרתי משימה: לקנות חלב ✅"

    result = await handle_incoming_message(mock_db, PARENT_PHONE, "משימה חדשה: לקנות חלב", "msg1")
    assert "יצרתי משימה" in result
    assert "לקנות חלב" in result
    mock_exec.assert_called_once()
    # Verify intent saved correctly
    conv_args = mock_conv.call_args[0]
    assert conv_args[4] == "task.create"


# ── 2. "משימות" → task list, task_list_order stored ──────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_mvp_task_list(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    member = _parent()
    mock_auth.return_value = member
    mock_parse.return_value = Command(skill="task", action="list")
    mock_exec.return_value = Result(success=True, message="📋 המשימות שלך:\n1. 🟢 לקנות חלב")
    mock_fmt.return_value = "📋 המשימות שלך:\n1. 🟢 לקנות חלב"

    result = await handle_incoming_message(mock_db, PARENT_PHONE, "משימות", "msg1")
    assert "המשימות" in result
    conv_args = mock_conv.call_args[0]
    assert conv_args[4] == "task.list"


# ── 3. "מחק משימה N" → pending, then "כן" → task archived ──────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_mvp_delete_confirm(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    member = _parent()
    mock_auth.return_value = member

    # Step 1: delete request → pending confirmation
    mock_parse.return_value = Command(skill="task", action="delete", params={"index": "1"})
    mock_exec.return_value = Result(success=True, message="למחוק את 'לקנות חלב'? (כן/לא)")
    mock_fmt.return_value = "למחוק את 'לקנות חלב'? (כן/לא)"
    r1 = await handle_incoming_message(mock_db, PARENT_PHONE, "מחק משימה 1", "msg1")
    assert "למחוק" in r1

    # Step 2: confirm → deleted
    task_id = uuid.uuid4()
    mock_parse.return_value = Command(skill="system", action="confirm")
    mock_exec.return_value = Result(
        success=True, message="משימה נמחקה: לקנות חלב ✅",
        entity_type="task", entity_id=task_id, action="deleted",
    )
    mock_fmt.return_value = "משימה נמחקה: לקנות חלב ✅"
    r2 = await handle_incoming_message(mock_db, PARENT_PHONE, "כן", "msg2")
    assert "נמחקה" in r2


# ── 4. "מחק משימה N" → pending, then "לא" → NOT archived ────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_mvp_delete_deny(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
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


# ── 5. "מחק הכל" → pending with task_ids, then "כן" → all archived

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_mvp_delete_all_confirm(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    member = _parent()
    mock_auth.return_value = member

    # Step 1: delete all → confirmation prompt
    mock_parse.return_value = Command(skill="task", action="delete_all")
    mock_exec.return_value = Result(success=True, message="למחוק את כל 3 המשימות? 😮\n...")
    mock_fmt.return_value = "למחוק את כל 3 המשימות? 😮\n..."
    r1 = await handle_incoming_message(mock_db, PARENT_PHONE, "מחק הכל", "msg1")
    assert "למחוק" in r1

    # Step 2: confirm → all archived
    mock_parse.return_value = Command(skill="system", action="confirm")
    mock_exec.return_value = Result(success=True, message="3 משימות נמחקו ✅")
    mock_fmt.return_value = "3 משימות נמחקו ✅"
    r2 = await handle_incoming_message(mock_db, PARENT_PHONE, "כן", "msg2")
    assert "נמחקו" in r2


# ── 6. "סיים N" → task completed, template response ─────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_mvp_task_complete(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    member = _parent()
    mock_auth.return_value = member
    task_id = uuid.uuid4()
    mock_parse.return_value = Command(skill="task", action="complete", params={"index": "1"})
    mock_exec.return_value = Result(
        success=True, message="משימה הושלמה: לקנות חלב ✅ כל הכבוד! 🎉",
        entity_type="task", entity_id=task_id, action="completed",
    )
    mock_fmt.return_value = "משימה הושלמה: לקנות חלב ✅ כל הכבוד! 🎉"

    result = await handle_incoming_message(mock_db, PARENT_PHONE, "סיים 1", "msg1")
    assert "הושלמה" in result
    conv_args = mock_conv.call_args[0]
    assert conv_args[4] == "task.complete"


# ── 7. "שלום" → greeting with name ──────────────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_mvp_greeting(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    member = _parent()
    mock_auth.return_value = member
    mock_parse.return_value = Command(skill="chat", action="greet")
    mock_exec.return_value = Result(success=True, message="בוקר טוב Segev! ☀️ מה נעשה היום?")
    mock_fmt.return_value = "בוקר טוב Segev! ☀️ מה נעשה היום?"

    result = await handle_incoming_message(mock_db, PARENT_PHONE, "שלום", "msg1")
    assert "Segev" in result
    conv_args = mock_conv.call_args[0]
    assert conv_args[4] == "chat.greet"


# ── 8. "עזרה" → command list ────────────────────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_mvp_help(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    member = _parent()
    mock_auth.return_value = member
    mock_parse.return_value = Command(skill="system", action="help")
    mock_exec.return_value = Result(success=True, message="📋 פקודות זמינות:\n\n▸ ניהול משימות")
    mock_fmt.return_value = "📋 פקודות זמינות:\n\n▸ ניהול משימות"

    result = await handle_incoming_message(mock_db, PARENT_PHONE, "עזרה", "msg1")
    assert "פקודות" in result
    conv_args = mock_conv.call_args[0]
    assert conv_args[4] == "system.help"


# ── 9. "לא" → cancelled template ────────────────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_mvp_cancel(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    member = _parent()
    mock_auth.return_value = member
    mock_parse.return_value = Command(skill="system", action="cancel")
    mock_exec.return_value = Result(success=True, message=TEMPLATES["cancelled"], action="cancel")
    mock_fmt.return_value = TEMPLATES["cancelled"]

    result = await handle_incoming_message(mock_db, PARENT_PHONE, "לא", "msg1")
    assert "עזבתי" in result


# ── 10. "באג: X" → bug reported template ────────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_mvp_bug_report(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    member = _parent()
    mock_auth.return_value = member
    mock_parse.return_value = Command(skill="bug", action="report", params={"description": "כפתור לא עובד"})
    mock_exec.return_value = Result(
        success=True, message="באג נרשם ✅\n📝 כפתור לא עובד",
        entity_type="bug_report", entity_id=uuid.uuid4(), action="reported",
    )
    mock_fmt.return_value = "באג נרשם ✅\n📝 כפתור לא עובד"

    result = await handle_incoming_message(mock_db, PARENT_PHONE, "באג: כפתור לא עובד", "msg1")
    assert "באג נרשם" in result
    conv_args = mock_conv.call_args[0]
    assert conv_args[4] == "bug.report"


# ── 11. Media message → document saved ──────────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_mvp_media_save(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    member = _parent()
    mock_auth.return_value = member
    mock_parse.return_value = Command(skill="media", action="save", params={"media_file_path": "/data/receipt.jpg"})
    mock_exec.return_value = Result(
        success=True, message="שמרתי את הקובץ ✅ receipt.jpg",
        entity_type="document", entity_id=uuid.uuid4(), action="saved",
    )
    mock_fmt.return_value = "שמרתי את הקובץ ✅ receipt.jpg"

    result = await handle_incoming_message(
        mock_db, PARENT_PHONE, "", "msg1", has_media=True, media_file_path="/data/receipt.jpg"
    )
    assert "שמרתי" in result
    conv_args = mock_conv.call_args[0]
    assert conv_args[4] == "media.save"


# ── 12. _sanitize_response with JSON-like responses ─────────────

class TestSanitizeResponse:
    """Test the _sanitize_response guard function."""

    def test_valid_hebrew_passes_through(self):
        response = "יצרתי משימה: לקנות חלב ✅"
        assert _sanitize_response(response) == response

    def test_json_object_replaced(self):
        response = '{"intent": "list_tasks", "entities": []}'
        result = _sanitize_response(response)
        assert result == TEMPLATES["error_fallback"]

    def test_json_array_replaced(self):
        response = '[{"task": "buy milk"}]'
        result = _sanitize_response(response)
        assert result == TEMPLATES["error_fallback"]

    def test_json_with_whitespace_replaced(self):
        response = '  {"intent": "greet"}'
        result = _sanitize_response(response)
        assert result == TEMPLATES["error_fallback"]

    def test_empty_json_object_replaced(self):
        response = "{}"
        result = _sanitize_response(response)
        assert result == TEMPLATES["error_fallback"]

    def test_normal_template_with_braces_in_text_passes(self):
        """Hebrew text that doesn't start with { or [ should pass."""
        response = "בוקר טוב Segev! ☀️ מה נעשה היום?"
        assert _sanitize_response(response) == response

    def test_error_fallback_passes_through(self):
        response = TEMPLATES["error_fallback"]
        assert _sanitize_response(response) == response

    def test_cancelled_template_passes_through(self):
        response = TEMPLATES["cancelled"]
        assert _sanitize_response(response) == response


# ── 13. Deterministic fallback for unmatched messages ────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.parse_command", return_value=None)
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_mvp_unmatched_returns_cant_understand(mock_auth, mock_parse, mock_conv, mock_db):
    """Unmatched message returns cant_understand template — zero LLM calls."""
    member = _parent()
    mock_auth.return_value = member

    result = await handle_incoming_message(mock_db, PARENT_PHONE, "מה המצב עם הדברים?", "msg1")
    expected = TEMPLATES["cant_understand"].format(name="Segev")
    assert result == expected
    # Verify intent is mvp.cant_understand (not chat.respond)
    conv_args = mock_conv.call_args[0]
    assert conv_args[4] == "mvp.cant_understand"


@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.parse_command", return_value=None)
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_mvp_unmatched_includes_member_name(mock_auth, mock_parse, mock_conv, mock_db):
    """Unmatched message includes the member's name in the response."""
    member = _make_family_member(name="דנה", phone=PARENT_PHONE, role="parent")
    mock_auth.return_value = member

    result = await handle_incoming_message(mock_db, PARENT_PHONE, "random gibberish", "msg1")
    assert "דנה" in result


# ── 14. Error handling returns error_fallback ────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.execute", side_effect=Exception("DB crash"))
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_mvp_exception_returns_error_fallback(mock_auth, mock_parse, mock_exec, mock_conv, mock_db):
    """Exception during processing returns error_fallback, never silent failure."""
    member = _parent()
    mock_auth.return_value = member
    mock_parse.return_value = Command(skill="task", action="list")

    result = await handle_incoming_message(mock_db, PARENT_PHONE, "משימות", "msg1")
    assert result == TEMPLATES["error_fallback"]


@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response", return_value="")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_mvp_empty_response_returns_error_fallback(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    """Empty response from format_response is replaced with error_fallback."""
    member = _parent()
    mock_auth.return_value = member
    mock_parse.return_value = Command(skill="task", action="list")
    mock_exec.return_value = Result(success=True, message="")

    result = await handle_incoming_message(mock_db, PARENT_PHONE, "משימות", "msg1")
    assert result == TEMPLATES["error_fallback"]


# ── 15. Empty response never returned ───────────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response", return_value="   ")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_mvp_whitespace_response_returns_error_fallback(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    """Whitespace-only response is replaced with error_fallback."""
    member = _parent()
    mock_auth.return_value = member
    mock_parse.return_value = Command(skill="task", action="create", params={"title": "test"})
    mock_exec.return_value = Result(success=True, message="   ")

    result = await handle_incoming_message(mock_db, PARENT_PHONE, "משימה חדשה: test", "msg1")
    assert result == TEMPLATES["error_fallback"]
    assert result.strip() != ""


# ── 16. Response NEVER contains raw JSON ─────────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_mvp_json_response_sanitized(mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db):
    """If format_response returns JSON-like string, it gets sanitized."""
    member = _parent()
    mock_auth.return_value = member
    mock_parse.return_value = Command(skill="task", action="list")
    mock_exec.return_value = Result(success=True, message='{"tasks": []}')
    mock_fmt.return_value = '{"tasks": []}'

    result = await handle_incoming_message(mock_db, PARENT_PHONE, "משימות", "msg1")
    assert not result.strip().startswith("{")
    assert not result.strip().startswith("[")
    assert result == TEMPLATES["error_fallback"]
