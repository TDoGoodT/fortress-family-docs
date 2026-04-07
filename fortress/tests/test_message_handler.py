"""Unit tests for the message handler service.

Updated for Skills Engine architecture (Sprint R1).
The message handler now routes through: auth → parse → execute → format,
with LLM fallback for unmatched messages.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.schema import FamilyMember
from src.prompts.personality import TEMPLATES as PERSONALITY_TEMPLATES
from src.services.message_handler import handle_incoming_message
from src.services.agent_loop import AgentResult


def _make_member(
    *,
    phone: str = "972501234567",
    is_active: bool = True,
) -> MagicMock:
    m = MagicMock(spec=FamilyMember)
    m.id = uuid.uuid4()
    m.name = "Test User"
    m.phone = phone
    m.role = "parent"
    m.is_active = is_active
    return m


# ── Auth layer tests ─────────────────────────────────────────────


@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.get_family_member_by_phone", return_value=None)
async def test_unknown_phone_rejected(mock_auth, mock_conv, mock_db) -> None:
    """Unknown phone number should return rejection message."""
    result = await handle_incoming_message(mock_db, "000000000", "hello", "msg1")
    assert result == PERSONALITY_TEMPLATES["unknown_member"]


@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_inactive_member(mock_auth, mock_conv, mock_db) -> None:
    """Inactive member should return inactive message."""
    mock_auth.return_value = _make_member(is_active=False)
    result = await handle_incoming_message(mock_db, "972501234567", "hello", "msg1")
    assert result == PERSONALITY_TEMPLATES["inactive_member"]


@pytest.mark.asyncio
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_conversation_saved(mock_auth, mock_db) -> None:
    """Every interaction should save a conversation record."""
    mock_auth.return_value = None
    await handle_incoming_message(mock_db, "000000000", "hello", "msg1")
    assert mock_db.add.called
    assert mock_db.commit.called


# ── Skills Engine path tests ─────────────────────────────────────


@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_active_member_delegates_to_router(mock_auth, mock_parse, mock_exec, mock_conv, mock_db) -> None:
    """Active member messages matched by parser should go through Skills Engine."""
    from src.skills.base_skill import Command, Result

    member = _make_member()
    mock_auth.return_value = member
    mock_parse.return_value = Command(skill="task", action="list")
    mock_exec.return_value = Result(success=True, message="router response")

    result = await handle_incoming_message(mock_db, "972501234567", "משימות", "msg1")
    assert result == "router response"
    mock_exec.assert_called_once()


@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_media_message_delegates_to_router(mock_auth, mock_parse, mock_exec, mock_conv, mock_db) -> None:
    """Media messages should be parsed and executed through Skills Engine."""
    from src.skills.base_skill import Command, Result

    member = _make_member()
    mock_auth.return_value = member
    mock_parse.return_value = Command(skill="media", action="save", params={"media_file_path": "/data/file.pdf"})
    mock_exec.return_value = Result(success=True, message="document saved")

    result = await handle_incoming_message(
        mock_db, "972501234567", "", "msg1",
        has_media=True, media_file_path="/data/file.pdf",
    )
    assert result == "document saved"
    mock_parse.assert_called_once()
    # Verify has_media was passed to parser
    _, kwargs = mock_parse.call_args
    assert kwargs.get("has_media") is True


@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_router_receives_correct_text(mock_auth, mock_parse, mock_exec, mock_conv, mock_db) -> None:
    """Parser should receive the exact message text."""
    from src.skills.base_skill import Command, Result

    member = _make_member()
    mock_auth.return_value = member
    mock_parse.return_value = Command(skill="task", action="create")
    mock_exec.return_value = Result(success=True, message="ok")

    await handle_incoming_message(mock_db, "972501234567", "משימה חדשה: קניות", "msg1")
    call_args = mock_parse.call_args
    assert call_args[0][0] == "משימה חדשה: קניות"


@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_agent_text_for_structured_command_forces_regex_fallback(
    mock_auth, mock_parse, mock_exec, mock_conv, mock_db
) -> None:
    """If the agent answers in text for a known command, execute the structured path instead."""
    from src.skills.base_skill import Command, Result

    member = _make_member()
    mock_auth.return_value = member
    mock_parse.return_value = Command(skill="task", action="create", params={"title": "קניות"})
    mock_exec.return_value = Result(success=True, message="יצרתי משימה: קניות ✅")

    with patch(
        "src.services.agent_loop.run",
        new=AsyncMock(return_value=AgentResult(response="יצרתי משימה בלי tool", tool_name=None, iterations=1)),
    ):
        result = await handle_incoming_message(mock_db, "972501234567", "משימה חדשה: קניות", "msg1")

    assert result == "יצרתי משימה: קניות ✅"
    mock_exec.assert_called_once()


@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_agent_text_for_register_task_for_assignee_forces_regex_fallback(
    mock_auth, mock_parse, mock_exec, mock_conv, mock_db
) -> None:
    """Phrases like 'תרשום משימה לחן - ...' should be executed structurally."""
    from src.skills.base_skill import Command, Result

    member = _make_member()
    mock_auth.return_value = member
    mock_parse.return_value = Command(
        skill="task",
        action="create",
        params={"title": "אני אוהב אותך", "assignee_name": "חן"},
    )
    mock_exec.return_value = Result(success=True, message="יצרתי את המשימה לחן ✅")

    with patch(
        "src.services.agent_loop.run",
        new=AsyncMock(return_value=AgentResult(response="יצרתי משימה לחן ✅", tool_name=None, iterations=1)),
    ):
        result = await handle_incoming_message(
            mock_db,
            "972501234567",
            "תרשום משימה לחן - אני אוהב אותך",
            "msg1",
        )

    assert result == "יצרתי את המשימה לחן ✅"
    mock_exec.assert_called_once()


@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_task_commands_bypass_agent_and_run_structured_first(
    mock_auth, mock_parse, mock_exec, mock_conv, mock_db
) -> None:
    """Structured task commands should not go through the LLM agent first."""
    from src.skills.base_skill import Command, Result

    member = _make_member()
    mock_auth.return_value = member
    mock_parse.return_value = Command(skill="task", action="list", params={})
    mock_exec.return_value = Result(success=True, message="📋 המשימות שלך:")

    with patch("src.services.agent_loop.run", new=AsyncMock()) as mock_agent_run:
        result = await handle_incoming_message(mock_db, "972501234567", "משימות", "msg1")

    assert result == "📋 המשימות שלך:"
    mock_exec.assert_called_once()
    mock_agent_run.assert_not_awaited()


# ── MVP deterministic fallback tests ─────────────────────────────


@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.parse_command", return_value=None)
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_strict_unknown_when_no_match(mock_auth, mock_parse, mock_conv, mock_db) -> None:
    """Unmatched system-like messages should return strict unknown response."""
    member = _make_member()
    mock_auth.return_value = member

    result = await handle_incoming_message(mock_db, "972501234567", "מה המצב?", "msg1")

    assert result == PERSONALITY_TEMPLATES["cant_understand"]
    mock_conv.assert_called_once()


@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.parse_command", return_value=None)
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_chat_fallback_for_clear_non_system_query(mock_auth, mock_parse, mock_conv, mock_db) -> None:
    member = _make_member()
    mock_auth.return_value = member

    with patch("src.services.bedrock_client.BedrockClient") as mock_bedrock_cls:
        mock_bedrock = AsyncMock()
        mock_bedrock.generate.return_value = "תשובה מהמודל"
        mock_bedrock_cls.return_value = mock_bedrock
        result = await handle_incoming_message(mock_db, "972501234567", "תן לי בדיחה", "msg1")

    assert result == "תשובה מהמודל"


# ── Conversation saving tests ────────────────────────────────────


@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.get_family_member_by_phone", return_value=None)
async def test_unknown_phone_saves_conversation(mock_auth, mock_conv, mock_db) -> None:
    """Unknown phone should save conversation with unknown_sender intent."""
    await handle_incoming_message(mock_db, "000000000", "hello", "msg1")
    mock_conv.assert_called_once()
    call_args = mock_conv.call_args
    assert call_args[0][4] == "unknown_sender"


@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_inactive_member_saves_conversation(mock_auth, mock_conv, mock_db) -> None:
    """Inactive member should save conversation with inactive_member intent."""
    mock_auth.return_value = _make_member(is_active=False)
    await handle_incoming_message(mock_db, "972501234567", "hello", "msg1")
    mock_conv.assert_called_once()
    call_args = mock_conv.call_args
    assert call_args[0][4] == "inactive_member"


# ── Skills Engine intent tracking ────────────────────────────────


@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_skills_path_saves_intent(mock_auth, mock_parse, mock_exec, mock_conv, mock_db) -> None:
    """Skills Engine path should save conversation with skill.action intent."""
    from src.skills.base_skill import Command, Result

    member = _make_member()
    mock_auth.return_value = member
    mock_parse.return_value = Command(skill="system", action="cancel")
    mock_exec.return_value = Result(success=True, message="ok")

    await handle_incoming_message(mock_db, "972501234567", "בטל", "msg1")
    mock_conv.assert_called_once()
    call_args = mock_conv.call_args
    assert call_args[0][4] == "system.cancel"
