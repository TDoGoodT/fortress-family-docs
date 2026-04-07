"""Tests for ChatSkill — greet, respond, verify, structure."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from src.models.schema import FamilyMember
from src.prompts.personality import TEMPLATES
from src.services.bedrock_client import HEBREW_FALLBACK
from src.skills.base_skill import Command, Result
from src.skills.chat_skill import ChatSkill


@pytest.fixture()
def skill():
    return ChatSkill()


@pytest.fixture()
def db():
    return MagicMock(spec=Session)


@pytest.fixture()
def member():
    m = MagicMock(spec=FamilyMember)
    m.id = uuid.uuid4()
    m.name = "שגב"
    m.phone = "+972501234567"
    m.role = "parent"
    return m


# ------------------------------------------------------------------
# Structure
# ------------------------------------------------------------------

def test_name(skill):
    assert skill.name == "chat"


def test_description(skill):
    assert skill.description == "שיחה חופשית וברכות"


def test_commands_count(skill):
    assert len(skill.commands) == 1
    _, action = skill.commands[0]
    assert action == "greet"


def test_get_help(skill):
    help_text = skill.get_help()
    assert "שלום" in help_text or "hello" in help_text


def test_execute_unknown_action(skill, db, member):
    """Unknown action returns error_fallback."""
    cmd = Command(skill="chat", action="unknown", params={})
    result = skill.execute(db, member, cmd)
    assert result.success is False
    assert result.message == TEMPLATES["error_fallback"]


# ------------------------------------------------------------------
# Greet — deterministic, no LLM
# ------------------------------------------------------------------

@patch("src.skills.chat_skill.get_time_context")
def test_greet_morning(mock_time, skill, db, member):
    mock_time.return_value = {"hour": 8}
    cmd = Command(skill="chat", action="greet", params={})
    result = skill.execute(db, member, cmd)
    assert result.success is True
    assert "בוקר טוב" in result.message
    assert member.name in result.message


@patch("src.skills.chat_skill.get_time_context")
def test_greet_afternoon(mock_time, skill, db, member):
    mock_time.return_value = {"hour": 14}
    cmd = Command(skill="chat", action="greet", params={})
    result = skill.execute(db, member, cmd)
    assert result.success is True
    assert "צהריים טובים" in result.message
    assert member.name in result.message


@patch("src.skills.chat_skill.get_time_context")
def test_greet_evening(mock_time, skill, db, member):
    mock_time.return_value = {"hour": 19}
    cmd = Command(skill="chat", action="greet", params={})
    result = skill.execute(db, member, cmd)
    assert result.success is True
    assert "ערב טוב" in result.message
    assert member.name in result.message


@patch("src.skills.chat_skill.get_time_context")
def test_greet_night(mock_time, skill, db, member):
    mock_time.return_value = {"hour": 2}
    cmd = Command(skill="chat", action="greet", params={})
    result = skill.execute(db, member, cmd)
    assert result.success is True
    assert "ער/ה" in result.message
    assert member.name in result.message


# ------------------------------------------------------------------
# Respond — async LLM conversation
# ------------------------------------------------------------------

@pytest.mark.asyncio
@patch("src.skills.chat_skill.llm_generate", new_callable=AsyncMock, return_value="שלום! מה שלומך?")
@patch("src.skills.chat_skill.load_memories")
async def test_respond_calls_llm(mock_load_memories, mock_dispatch, skill, db, member):
    """respond() builds prompt with memories and calls llm_generate."""
    mock_mem = MagicMock()
    mock_mem.content = "אוהב קפה"
    mock_load_memories.return_value = [mock_mem]

    result = await skill.respond(db, member, "מה קורה?")

    assert result == "שלום! מה שלומך?"
    mock_load_memories.assert_called_once_with(db, member.id)
    mock_dispatch.assert_called_once()
    call_args = mock_dispatch.call_args
    # First positional arg is the prompt
    prompt_arg = call_args[0][0] if call_args[0] else call_args.kwargs.get("prompt", "")
    assert "מה קורה?" in prompt_arg


@pytest.mark.asyncio
@patch("src.skills.chat_skill.llm_generate", new_callable=AsyncMock, return_value="")
@patch("src.skills.chat_skill.load_memories")
async def test_respond_fallback_on_llm_failure(mock_load_memories, mock_dispatch, skill, db, member):
    """respond() returns error_fallback when llm_generate returns empty string."""
    mock_load_memories.return_value = []

    result = await skill.respond(db, member, "ספר לי בדיחה")

    assert result == TEMPLATES["error_fallback"]


@pytest.mark.asyncio
@patch("src.skills.chat_skill.load_memories")
async def test_respond_fallback_on_exception(mock_load_memories, skill, db, member):
    """respond() returns error_fallback when an exception is raised."""
    mock_load_memories.side_effect = Exception("DB down")

    result = await skill.respond(db, member, "מה קורה?")

    assert result == TEMPLATES["error_fallback"]


# ------------------------------------------------------------------
# Verify — always True
# ------------------------------------------------------------------

def test_verify_always_true(skill, db):
    result = Result(success=True, message="ok")
    assert skill.verify(db, result) is True


def test_verify_true_even_on_failure(skill, db):
    result = Result(success=False, message="error")
    assert skill.verify(db, result) is True
