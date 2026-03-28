"""E2E conversation persistence tests — every action saves a Conversation record.

Sprint R3, Requirement 5.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.schema import Conversation
from src.prompts.personality import TEMPLATES
from src.services.message_handler import handle_incoming_message
from src.skills.base_skill import Command, Result

from tests.conftest import _make_family_member


PHONE = "972501234567"


def _parent():
    return _make_family_member(name="Segev", phone=PHONE, role="parent")


# ── 1. Skill action saves Conversation record ──────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_skill_action_saves_conversation(mock_auth, mock_parse, mock_exec, mock_fmt, mock_db):
    member = _parent()
    mock_auth.return_value = member
    mock_parse.return_value = Command(skill="task", action="list")
    mock_exec.return_value = Result(success=True, message="📋 המשימות שלך:")
    mock_fmt.return_value = "📋 המשימות שלך:"

    await handle_incoming_message(mock_db, PHONE, "משימות", "msg1")
    # _save_conversation calls db.add + db.commit
    assert mock_db.add.called
    assert mock_db.commit.called


# ── 2. Intent matches "{skill}.{action}" format ────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_conversation_intent_format(mock_auth, mock_parse, mock_exec, mock_fmt, mock_db):
    member = _parent()
    mock_auth.return_value = member
    mock_parse.return_value = Command(skill="task", action="create", params={"title": "test"})
    mock_exec.return_value = Result(success=True, message="יצרתי משימה: test ✅")
    mock_fmt.return_value = "יצרתי משימה: test ✅"

    await handle_incoming_message(mock_db, PHONE, "משימה חדשה: test", "msg1")
    # Check the Conversation object added to db
    conv_obj = mock_db.add.call_args[0][0]
    assert isinstance(conv_obj, Conversation)
    assert conv_obj.intent == "task.create"


# ── 3. message_in contains original message ─────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_conversation_message_in(mock_auth, mock_parse, mock_exec, mock_fmt, mock_db):
    member = _parent()
    mock_auth.return_value = member
    mock_parse.return_value = Command(skill="task", action="list")
    mock_exec.return_value = Result(success=True, message="📋 המשימות שלך:")
    mock_fmt.return_value = "📋 המשימות שלך:"

    await handle_incoming_message(mock_db, PHONE, "משימות", "msg1")
    conv_obj = mock_db.add.call_args[0][0]
    assert conv_obj.message_in == "משימות"


# ── 4. message_out contains response ────────────────────────────

@pytest.mark.asyncio
@patch("src.services.message_handler.format_response")
@patch("src.services.message_handler.execute")
@patch("src.services.message_handler.parse_command")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_conversation_message_out(mock_auth, mock_parse, mock_exec, mock_fmt, mock_db):
    member = _parent()
    mock_auth.return_value = member
    mock_parse.return_value = Command(skill="task", action="list")
    mock_exec.return_value = Result(success=True, message="📋 המשימות שלך:")
    mock_fmt.return_value = "📋 המשימות שלך:"

    await handle_incoming_message(mock_db, PHONE, "משימות", "msg1")
    conv_obj = mock_db.add.call_args[0][0]
    assert conv_obj.message_out == "📋 המשימות שלך:"


# ── 5. Unknown phone → Conversation with None member_id ─────────

@pytest.mark.asyncio
@patch("src.services.message_handler.get_family_member_by_phone", return_value=None)
async def test_unknown_phone_conversation(mock_auth, mock_db):
    await handle_incoming_message(mock_db, "000000000", "hello", "msg1")
    conv_obj = mock_db.add.call_args[0][0]
    assert isinstance(conv_obj, Conversation)
    assert conv_obj.family_member_id is None


# ── 6. MVP deterministic fallback → intent "mvp.cant_understand" ─

@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.parse_command", return_value=None)
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_llm_fallback_conversation_intent(mock_auth, mock_parse, mock_conv, mock_db):
    member = _parent()
    mock_auth.return_value = member

    with patch("src.skills.chat_skill.BedrockClient") as mock_bedrock_cls:
        mock_bedrock = AsyncMock()
        mock_bedrock.generate.return_value = "תשובה"
        mock_bedrock_cls.return_value = mock_bedrock

        await handle_incoming_message(mock_db, PHONE, "מה המצב?", "msg1")

    conv_args = mock_conv.call_args[0]
    assert conv_args[4] == "chat.llm"
