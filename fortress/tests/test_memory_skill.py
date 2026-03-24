"""Tests for MemorySkill — store, recall, list."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from src.models.schema import FamilyMember, Memory
from src.prompts.personality import TEMPLATES
from src.skills.base_skill import Command, Result
from src.skills.memory_skill import MemorySkill


@pytest.fixture()
def skill():
    return MemorySkill()


@pytest.fixture()
def db():
    return MagicMock(spec=Session)


@pytest.fixture()
def member():
    m = MagicMock(spec=FamilyMember)
    m.id = uuid.uuid4()
    m.name = "Test User"
    m.phone = "+972501234567"
    m.role = "parent"
    return m


# ------------------------------------------------------------------
# Properties
# ------------------------------------------------------------------

def test_name(skill):
    assert skill.name == "memory"


def test_description(skill):
    assert skill.description == "ניהול זיכרונות — שמירה, שליפה, רשימה"


def test_commands_list_pattern(skill):
    patterns = skill.commands
    assert len(patterns) == 1
    regex, action = patterns[0]
    assert action == "list"
    assert regex.match("זכרונות")
    assert regex.match("memories")
    assert not regex.match("זכרונות שלי")


def test_get_help(skill):
    assert "זכרונות" in skill.get_help()


# ------------------------------------------------------------------
# _store
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_store_success(skill, db, member):
    """Valid content is stored and returns entity_type='memory'."""
    mock_memory = MagicMock(spec=Memory)
    mock_memory.id = uuid.uuid4()

    with patch("src.skills.memory_skill.memory_service") as ms:
        ms.check_exclusion.return_value = False
        ms.save_memory = AsyncMock(return_value=mock_memory)

        result = await skill._store(db, member, "likes coffee", "preference", "short")

    assert result.success is True
    assert result.entity_type == "memory"
    assert result.entity_id == mock_memory.id
    assert result.action == "stored"


@pytest.mark.asyncio
async def test_store_excluded_by_check(skill, db, member):
    """Content matching exclusion pattern returns failure."""
    with patch("src.skills.memory_skill.memory_service") as ms:
        ms.check_exclusion.return_value = True

        result = await skill._store(db, member, "secret password", "fact", "short")

    assert result.success is False
    assert result.message == TEMPLATES["memory_excluded"]


@pytest.mark.asyncio
async def test_store_excluded_by_save_memory(skill, db, member):
    """save_memory returning None (service-level exclusion) returns failure."""
    with patch("src.skills.memory_skill.memory_service") as ms:
        ms.check_exclusion.return_value = False
        ms.save_memory = AsyncMock(return_value=None)

        result = await skill._store(db, member, "something", "fact", "short")

    assert result.success is False
    assert result.message == TEMPLATES["memory_excluded"]


# ------------------------------------------------------------------
# _recall
# ------------------------------------------------------------------

def test_recall_returns_memories(skill, db, member):
    """Recall loads memories and returns them in Result.data."""
    mock_memories = [MagicMock(spec=Memory), MagicMock(spec=Memory)]

    with patch("src.skills.memory_skill.memory_service") as ms:
        ms.load_memories.return_value = mock_memories

        result = skill._recall(db, member)

    assert result.success is True
    assert result.data == {"memories": mock_memories}


def test_recall_empty(skill, db, member):
    """Recall with no memories returns empty list in data."""
    with patch("src.skills.memory_skill.memory_service") as ms:
        ms.load_memories.return_value = []

        result = skill._recall(db, member)

    assert result.success is True
    assert result.data == {"memories": []}


# ------------------------------------------------------------------
# _list (via execute)
# ------------------------------------------------------------------

def test_list_with_memories(skill, db, member):
    """List formats memories as numbered list with category."""
    m1 = MagicMock(spec=Memory)
    m1.category = "preference"
    m1.content = "likes coffee"
    m2 = MagicMock(spec=Memory)
    m2.category = "fact"
    m2.content = "birthday is Jan 1"

    with patch("src.skills.memory_skill.memory_service") as ms:
        ms.load_memories.return_value = [m1, m2]

        cmd = Command(skill="memory", action="list", params={})
        result = skill.execute(db, member, cmd)

    assert result.success is True
    assert TEMPLATES["memory_list_header"] in result.message
    assert "1. [preference] likes coffee" in result.message
    assert "2. [fact] birthday is Jan 1" in result.message


def test_list_empty(skill, db, member):
    """List with no memories returns empty template."""
    with patch("src.skills.memory_skill.memory_service") as ms:
        ms.load_memories.return_value = []

        cmd = Command(skill="memory", action="list", params={})
        result = skill.execute(db, member, cmd)

    assert result.success is True
    assert result.message == TEMPLATES["memory_list_empty"]


def test_execute_unknown_action(skill, db, member):
    """Unknown action returns error_fallback."""
    cmd = Command(skill="memory", action="unknown", params={})
    result = skill.execute(db, member, cmd)
    assert result.success is False
    assert result.message == TEMPLATES["error_fallback"]


# ------------------------------------------------------------------
# verify
# ------------------------------------------------------------------

def test_verify_stored_exists(skill, db):
    """Verify returns True when stored memory exists in DB."""
    memory_id = uuid.uuid4()
    mock_memory = MagicMock(spec=Memory)
    db.query.return_value.filter.return_value.first.return_value = mock_memory

    result = Result(
        success=True, message="ok",
        entity_type="memory", entity_id=memory_id, action="stored",
    )
    assert skill.verify(db, result) is True


def test_verify_stored_missing(skill, db):
    """Verify returns False when stored memory is not found in DB."""
    memory_id = uuid.uuid4()
    db.query.return_value.filter.return_value.first.return_value = None

    result = Result(
        success=True, message="ok",
        entity_type="memory", entity_id=memory_id, action="stored",
    )
    assert skill.verify(db, result) is False


def test_verify_recall_always_true(skill, db):
    """Verify for recall action always returns True."""
    result = Result(success=True, message="", action="recall")
    assert skill.verify(db, result) is True


def test_verify_list_always_true(skill, db):
    """Verify for list action always returns True."""
    result = Result(success=True, message="", action="list")
    assert skill.verify(db, result) is True


def test_verify_no_entity_id_true(skill, db):
    """Verify returns True when entity_id is None even for stored action."""
    result = Result(
        success=True, message="ok",
        entity_type="memory", entity_id=None, action="stored",
    )
    assert skill.verify(db, result) is True
