"""Bug condition exploration & preservation property tests for MVP commands.

Task 1: Bug condition exploration — these tests encode EXPECTED behavior.
They MUST FAIL on unfixed code (proving the bugs exist).
After the fix, they MUST PASS (proving the bugs are fixed).

Task 2: Preservation property tests — these encode CURRENT correct behavior.
They MUST PASS on unfixed code (confirming baseline to preserve).
After the fix, they MUST STILL PASS (confirming no regressions).
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.prompts.personality import TEMPLATES
from src.services.message_handler import handle_incoming_message
from src.skills.base_skill import Command, Result

from tests.conftest import (
    _make_family_member,
    _make_conversation_state,
    _make_task,
)

PARENT_PHONE = "972501234567"


def _parent():
    return _make_family_member(name="Segev", phone=PARENT_PHONE, role="parent")


# ═══════════════════════════════════════════════════════════════════
# TASK 1: Bug Condition Exploration Tests
# These MUST FAIL on unfixed code — failure confirms bugs exist.
# ═══════════════════════════════════════════════════════════════════


class TestBugConditionExploration:
    """Tests that surface counterexamples for each of the 6 bugs."""

    # ── Bug 1: Raw JSON Leak ─────────────────────────────────────

    @pytest.mark.asyncio
    @patch("src.services.message_handler._save_conversation")
    @patch("src.services.message_handler.strip_pii", return_value=("test", []))
    @patch("src.services.message_handler.parse_command", return_value=None)
    @patch("src.services.message_handler.get_family_member_by_phone")
    async def test_bug1_raw_json_never_reaches_user(
        self, mock_auth, mock_parse, mock_pii, mock_conv, mock_db
    ):
        """Bug 1: When LLM fallback returns raw JSON, user should NOT see it.

        EXPECTED: Response is error_fallback template, NOT raw JSON.
        ON UNFIXED CODE: FAILS — raw JSON passes through to user.
        """
        member = _parent()
        mock_auth.return_value = member

        result = await handle_incoming_message(mock_db, PARENT_PHONE, "מה המצב?", "msg1")

        # Expected behavior: raw JSON should be caught and replaced
        assert not result.strip().startswith("{"), f"Raw JSON leaked to user: {result[:100]}"
        assert not result.strip().startswith("["), f"Raw JSON array leaked to user: {result[:100]}"
        assert "intent" not in result, f"JSON content in response: {result[:100]}"

    # ── Bug 4: Silent Failure ────────────────────────────────────

    @pytest.mark.asyncio
    @patch("src.services.message_handler._save_conversation")
    @patch("src.services.message_handler.strip_pii", return_value=("test", []))
    @patch("src.services.message_handler.execute", side_effect=Exception("Executor crash"))
    @patch("src.services.message_handler.parse_command")
    @patch("src.services.message_handler.get_family_member_by_phone")
    async def test_bug4_exception_returns_error_fallback(
        self, mock_auth, mock_parse, mock_exec, mock_pii, mock_conv, mock_db
    ):
        """Bug 4: When execute() raises an exception, user should get error_fallback.

        EXPECTED: error_fallback template returned, never empty/None.
        ON UNFIXED CODE: FAILS — exception propagates, no response.
        """
        member = _parent()
        mock_auth.return_value = member
        mock_parse.return_value = Command(skill="task", action="list")

        # On unfixed code, this should raise and propagate
        try:
            result = await handle_incoming_message(mock_db, PARENT_PHONE, "משימות", "msg1")
        except Exception:
            pytest.fail("Exception propagated to caller — silent failure, no response sent")

        assert result is not None, "Response is None — silent failure"
        assert result.strip() != "", "Response is empty — silent failure"
        assert result == TEMPLATES["error_fallback"], f"Expected error_fallback, got: {result[:100]}"

    @pytest.mark.asyncio
    @patch("src.services.message_handler._save_conversation")
    @patch("src.services.message_handler.strip_pii", return_value=("test", []))
    @patch("src.services.message_handler.format_response", return_value="")
    @patch("src.services.message_handler.execute")
    @patch("src.services.message_handler.parse_command")
    @patch("src.services.message_handler.get_family_member_by_phone")
    async def test_bug4_empty_response_returns_error_fallback(
        self, mock_auth, mock_parse, mock_exec, mock_fmt, mock_pii, mock_conv, mock_db
    ):
        """Bug 4: When a skill returns empty response, user should get error_fallback.

        EXPECTED: error_fallback template returned, never empty string.
        ON UNFIXED CODE: FAILS — empty string returned to user.
        """
        member = _parent()
        mock_auth.return_value = member
        mock_parse.return_value = Command(skill="task", action="list")
        mock_exec.return_value = Result(success=True, message="")

        result = await handle_incoming_message(mock_db, PARENT_PHONE, "משימות", "msg1")

        assert result is not None, "Response is None"
        assert result.strip() != "", "Empty response returned to user"

    # ── Bug 6: LLM Fall-through for unmatched messages ───────────

    @pytest.mark.asyncio
    @patch("src.services.message_handler._save_conversation")
    @patch("src.services.message_handler.strip_pii", return_value=("test", []))
    @patch("src.services.message_handler.parse_command", return_value=None)
    @patch("src.services.message_handler.get_family_member_by_phone")
    async def test_bug6_unmatched_message_no_llm_fallback(
        self, mock_auth, mock_parse, mock_pii, mock_conv, mock_db
    ):
        """Bug 6: Unmatched messages should return cant_understand, NOT call LLM.

        EXPECTED: Deterministic cant_understand template with member name.
        ON UNFIXED CODE: FAILS — ChatSkill.respond (LLM) is called.
        """
        member = _parent()
        mock_auth.return_value = member

        result = await handle_incoming_message(mock_db, PARENT_PHONE, "מה המצב עם הדברים?", "msg1")

        # Expected: deterministic template, NOT LLM response
        expected = TEMPLATES["cant_understand"].format(name=member.name)
        assert result == expected, (
            f"Expected cant_understand template, got: {result[:100]}"
        )


# ═══════════════════════════════════════════════════════════════════
# TASK 2: Preservation Property Tests
# These MUST PASS on unfixed code — passing confirms baseline behavior.
# After the fix, they MUST STILL PASS — confirming no regressions.
# ═══════════════════════════════════════════════════════════════════


class TestPreservation:
    """Property 2: Existing MVP command behavior is unchanged.

    **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10**
    """

    # ── 3.2 Task Create ──────────────────────────────────────────

    @pytest.mark.asyncio
    @patch("src.services.message_handler._save_conversation")
    @patch("src.services.message_handler.format_response")
    @patch("src.services.message_handler.execute")
    @patch("src.services.message_handler.parse_command")
    @patch("src.services.message_handler.get_family_member_by_phone")
    async def test_task_create_returns_task_created_template(
        self, mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db
    ):
        """Task Create: 'משימה חדשה: {title}' → creates task in DB, returns task_created template.

        **Validates: Requirements 3.2**
        """
        member = _parent()
        mock_auth.return_value = member
        title = "לקנות חלב"
        task_id = uuid.uuid4()
        mock_parse.return_value = Command(skill="task", action="create", params={"title": title})
        expected_msg = TEMPLATES["task_created"].format(title=title, due_date_text="")
        mock_exec.return_value = Result(
            success=True, message=expected_msg,
            entity_type="task", entity_id=task_id, action="created",
        )
        mock_fmt.return_value = expected_msg

        result = await handle_incoming_message(mock_db, PARENT_PHONE, f"משימה חדשה: {title}", "msg1")

        assert "יצרתי משימה" in result
        assert title in result
        mock_exec.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.services.message_handler._save_conversation")
    @patch("src.services.message_handler.format_response")
    @patch("src.services.message_handler.execute")
    @patch("src.services.message_handler.parse_command")
    @patch("src.services.message_handler.get_family_member_by_phone")
    async def test_task_create_with_hebrew_title(
        self, mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db
    ):
        """Task Create with different Hebrew title preserves behavior.

        **Validates: Requirements 3.2**
        """
        member = _parent()
        mock_auth.return_value = member
        title = "לתקן את הברז"
        task_id = uuid.uuid4()
        mock_parse.return_value = Command(skill="task", action="create", params={"title": title})
        expected_msg = TEMPLATES["task_created"].format(title=title, due_date_text="")
        mock_exec.return_value = Result(
            success=True, message=expected_msg,
            entity_type="task", entity_id=task_id, action="created",
        )
        mock_fmt.return_value = expected_msg

        result = await handle_incoming_message(mock_db, PARENT_PHONE, f"משימה חדשה: {title}", "msg1")

        assert "יצרתי משימה" in result
        assert title in result

    # ── 3.3 Task List ────────────────────────────────────────────

    @pytest.mark.asyncio
    @patch("src.services.message_handler._save_conversation")
    @patch("src.services.message_handler.format_response")
    @patch("src.services.message_handler.execute")
    @patch("src.services.message_handler.parse_command")
    @patch("src.services.message_handler.get_family_member_by_phone")
    async def test_task_list_returns_formatted_list(
        self, mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db
    ):
        """Task List: 'משימות' → returns formatted task list via format_task_list.

        **Validates: Requirements 3.3**
        """
        member = _parent()
        mock_auth.return_value = member
        mock_parse.return_value = Command(skill="task", action="list")
        list_msg = "📋 המשימות שלך:\n1. 🟢 לקנות חלב\n2. 🟢 לתקן ברז"
        mock_exec.return_value = Result(success=True, message=list_msg)
        mock_fmt.return_value = list_msg

        result = await handle_incoming_message(mock_db, PARENT_PHONE, "משימות", "msg1")

        assert "המשימות" in result
        assert "לקנות חלב" in result

    @pytest.mark.asyncio
    @patch("src.services.message_handler._save_conversation")
    @patch("src.services.message_handler.format_response")
    @patch("src.services.message_handler.execute")
    @patch("src.services.message_handler.parse_command")
    @patch("src.services.message_handler.get_family_member_by_phone")
    async def test_task_list_empty_returns_empty_template(
        self, mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db
    ):
        """Task List with no tasks returns empty list template.

        **Validates: Requirements 3.3**
        """
        member = _parent()
        mock_auth.return_value = member
        mock_parse.return_value = Command(skill="task", action="list")
        mock_exec.return_value = Result(success=True, message=TEMPLATES["task_list_empty"])
        mock_fmt.return_value = TEMPLATES["task_list_empty"]

        result = await handle_incoming_message(mock_db, PARENT_PHONE, "משימות", "msg1")

        assert result == TEMPLATES["task_list_empty"]

    # ── 3.1 Greeting ─────────────────────────────────────────────

    @pytest.mark.asyncio
    @patch("src.services.message_handler._save_conversation")
    @patch("src.services.message_handler.format_response")
    @patch("src.services.message_handler.execute")
    @patch("src.services.message_handler.parse_command")
    @patch("src.services.message_handler.get_family_member_by_phone")
    async def test_greeting_returns_time_of_day_with_name(
        self, mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db
    ):
        """Greeting: 'שלום' → returns time-of-day greeting with member name.

        **Validates: Requirements 3.1**
        """
        member = _parent()
        mock_auth.return_value = member
        mock_parse.return_value = Command(skill="chat", action="greet")
        greeting_msg = "בוקר טוב Segev! ☀️ מה נעשה היום?"
        mock_exec.return_value = Result(success=True, message=greeting_msg)
        mock_fmt.return_value = greeting_msg

        result = await handle_incoming_message(mock_db, PARENT_PHONE, "שלום", "msg1")

        assert "Segev" in result

    # ── 3.4 Help ─────────────────────────────────────────────────

    @pytest.mark.asyncio
    @patch("src.services.message_handler._save_conversation")
    @patch("src.services.message_handler.format_response")
    @patch("src.services.message_handler.execute")
    @patch("src.services.message_handler.parse_command")
    @patch("src.services.message_handler.get_family_member_by_phone")
    async def test_help_returns_command_list(
        self, mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db
    ):
        """Help: 'עזרה' → returns command list from registered skills.

        **Validates: Requirements 3.4**
        """
        member = _parent()
        mock_auth.return_value = member
        mock_parse.return_value = Command(skill="system", action="help")
        help_msg = "📋 פקודות זמינות:\n\n▸ ניהול משימות"
        mock_exec.return_value = Result(success=True, message=help_msg)
        mock_fmt.return_value = help_msg

        result = await handle_incoming_message(mock_db, PARENT_PHONE, "עזרה", "msg1")

        assert "פקודות" in result

    # ── 3.5 Cancel ───────────────────────────────────────────────

    @pytest.mark.asyncio
    @patch("src.services.message_handler._save_conversation")
    @patch("src.services.message_handler.format_response")
    @patch("src.services.message_handler.execute")
    @patch("src.services.message_handler.parse_command")
    @patch("src.services.message_handler.get_family_member_by_phone")
    async def test_cancel_lo_clears_state_returns_cancelled(
        self, mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db
    ):
        """Cancel: 'לא' → clears state, returns cancelled template.

        **Validates: Requirements 3.5**
        """
        member = _parent()
        mock_auth.return_value = member
        mock_parse.return_value = Command(skill="system", action="cancel")
        mock_exec.return_value = Result(success=True, message=TEMPLATES["cancelled"])
        mock_fmt.return_value = TEMPLATES["cancelled"]

        result = await handle_incoming_message(mock_db, PARENT_PHONE, "לא", "msg1")

        assert result == TEMPLATES["cancelled"]
        assert "עזבתי" in result

    @pytest.mark.asyncio
    @patch("src.services.message_handler._save_conversation")
    @patch("src.services.message_handler.format_response")
    @patch("src.services.message_handler.execute")
    @patch("src.services.message_handler.parse_command")
    @patch("src.services.message_handler.get_family_member_by_phone")
    async def test_cancel_azov_clears_state_returns_cancelled(
        self, mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db
    ):
        """Cancel: 'עזוב' → clears state, returns cancelled template.

        **Validates: Requirements 3.5**
        """
        member = _parent()
        mock_auth.return_value = member
        mock_parse.return_value = Command(skill="system", action="cancel")
        mock_exec.return_value = Result(success=True, message=TEMPLATES["cancelled"])
        mock_fmt.return_value = TEMPLATES["cancelled"]

        result = await handle_incoming_message(mock_db, PARENT_PHONE, "עזוב", "msg1")

        assert result == TEMPLATES["cancelled"]

    # ── 3.8 Auth Rejection: Unknown Phone ────────────────────────

    @pytest.mark.asyncio
    @patch("src.services.message_handler._save_conversation")
    @patch("src.services.message_handler.get_family_member_by_phone", return_value=None)
    async def test_unknown_phone_returns_unknown_member_template(
        self, mock_auth, mock_conv, mock_db
    ):
        """Auth Rejection: unknown phone → unknown_member template.

        **Validates: Requirements 3.8**
        """
        result = await handle_incoming_message(mock_db, "000000000", "שלום", "msg1")

        assert result == TEMPLATES["unknown_member"]
        mock_conv.assert_called_once()

    # ── 3.9 Auth Rejection: Inactive Member ──────────────────────

    @pytest.mark.asyncio
    @patch("src.services.message_handler._save_conversation")
    @patch("src.services.message_handler.get_family_member_by_phone")
    async def test_inactive_member_returns_inactive_template(
        self, mock_auth, mock_conv, mock_db
    ):
        """Auth Rejection: inactive member → inactive_member template.

        **Validates: Requirements 3.9**
        """
        mock_auth.return_value = _make_family_member(is_active=False)

        result = await handle_incoming_message(mock_db, PARENT_PHONE, "שלום", "msg1")

        assert result == TEMPLATES["inactive_member"]

    # ── 3.7 Bug Report ───────────────────────────────────────────

    @pytest.mark.asyncio
    @patch("src.services.message_handler._save_conversation")
    @patch("src.services.message_handler.format_response")
    @patch("src.services.message_handler.execute")
    @patch("src.services.message_handler.parse_command")
    @patch("src.services.message_handler.get_family_member_by_phone")
    async def test_bug_report_returns_bug_reported_template(
        self, mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db
    ):
        """Bug Report: 'באג: {description}' → creates BugReport, returns bug_reported template.

        **Validates: Requirements 3.7**
        """
        member = _parent()
        mock_auth.return_value = member
        description = "הכפתור לא עובד"
        mock_parse.return_value = Command(skill="bug", action="report", params={"description": description})
        expected_msg = TEMPLATES["bug_reported"].format(description=description)
        mock_exec.return_value = Result(
            success=True, message=expected_msg,
            entity_type="bug_report", entity_id=uuid.uuid4(), action="reported",
        )
        mock_fmt.return_value = expected_msg

        result = await handle_incoming_message(mock_db, PARENT_PHONE, f"באג: {description}", "msg1")

        assert "באג נרשם" in result
        assert description in result

    # ── 3.6 Media Save ───────────────────────────────────────────

    @pytest.mark.asyncio
    @patch("src.services.message_handler._save_conversation")
    @patch("src.services.message_handler.format_response")
    @patch("src.services.message_handler.execute")
    @patch("src.services.message_handler.parse_command")
    @patch("src.services.message_handler.get_family_member_by_phone")
    async def test_media_save_returns_document_saved_template(
        self, mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db
    ):
        """Media Save: media message → saves document, returns document_saved template.

        **Validates: Requirements 3.6**
        """
        member = _parent()
        mock_auth.return_value = member
        filename = "receipt.jpg"
        mock_parse.return_value = Command(skill="media", action="save", params={"media_file_path": "/data/receipt.jpg"})
        expected_msg = TEMPLATES["document_saved"].format(filename=filename)
        mock_exec.return_value = Result(
            success=True, message=expected_msg,
            entity_type="document", entity_id=uuid.uuid4(), action="saved",
        )
        mock_fmt.return_value = expected_msg

        result = await handle_incoming_message(
            mock_db, PARENT_PHONE, "", "msg1", has_media=True, media_file_path="/data/receipt.jpg"
        )

        assert "שמרתי" in result
        assert filename in result

    # ── Delete with valid index ──────────────────────────────────

    @pytest.mark.asyncio
    @patch("src.services.message_handler._save_conversation")
    @patch("src.services.message_handler.format_response")
    @patch("src.services.message_handler.execute")
    @patch("src.services.message_handler.parse_command")
    @patch("src.services.message_handler.get_family_member_by_phone")
    async def test_delete_with_valid_index_sets_pending_confirmation(
        self, mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db
    ):
        """Delete with valid index: 'משימות' then 'מחק משימה N' → sets pending confirmation.

        **Validates: Requirements 3.3, 3.5**
        """
        member = _parent()
        mock_auth.return_value = member

        # Step 1: list tasks to populate task_list_order
        mock_parse.return_value = Command(skill="task", action="list")
        list_msg = "📋 המשימות שלך:\n1. 🟢 לקנות חלב"
        mock_exec.return_value = Result(success=True, message=list_msg)
        mock_fmt.return_value = list_msg
        await handle_incoming_message(mock_db, PARENT_PHONE, "משימות", "msg1")

        # Step 2: delete task 1 → pending confirmation
        mock_parse.return_value = Command(skill="task", action="delete", params={"index": "1"})
        confirm_msg = TEMPLATES["confirm_delete"].format(title="לקנות חלב")
        mock_exec.return_value = Result(success=True, message=confirm_msg)
        mock_fmt.return_value = confirm_msg

        result = await handle_incoming_message(mock_db, PARENT_PHONE, "מחק משימה 1", "msg2")

        assert "למחוק" in result
        assert "לקנות חלב" in result

    # ── Complete with valid index ────────────────────────────────

    @pytest.mark.asyncio
    @patch("src.services.message_handler._save_conversation")
    @patch("src.services.message_handler.format_response")
    @patch("src.services.message_handler.execute")
    @patch("src.services.message_handler.parse_command")
    @patch("src.services.message_handler.get_family_member_by_phone")
    async def test_complete_with_valid_index_returns_task_completed(
        self, mock_auth, mock_parse, mock_exec, mock_fmt, mock_conv, mock_db
    ):
        """Complete with valid index: 'משימות' then 'סיים N' → marks task done, returns task_completed.

        **Validates: Requirements 3.3**
        """
        member = _parent()
        mock_auth.return_value = member

        # Step 1: list tasks
        mock_parse.return_value = Command(skill="task", action="list")
        list_msg = "📋 המשימות שלך:\n1. 🟢 לקנות חלב"
        mock_exec.return_value = Result(success=True, message=list_msg)
        mock_fmt.return_value = list_msg
        await handle_incoming_message(mock_db, PARENT_PHONE, "משימות", "msg1")

        # Step 2: complete task 1
        task_id = uuid.uuid4()
        mock_parse.return_value = Command(skill="task", action="complete", params={"index": "1"})
        completed_msg = TEMPLATES["task_completed"].format(title="לקנות חלב")
        mock_exec.return_value = Result(
            success=True, message=completed_msg,
            entity_type="task", entity_id=task_id, action="completed",
        )
        mock_fmt.return_value = completed_msg

        result = await handle_incoming_message(mock_db, PARENT_PHONE, "סיים 1", "msg2")

        assert "הושלמה" in result
        assert "לקנות חלב" in result
