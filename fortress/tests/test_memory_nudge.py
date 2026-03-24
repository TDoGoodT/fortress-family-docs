"""Tests for Memory Nudge service — S2 feature."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.services.memory_nudge import should_nudge, maybe_save_nudge


# ── should_nudge heuristic tests ─────────────────────────────────


def test_nudge_detects_hebrew_code_pattern() -> None:
    assert should_nudge("הקוד הוא 1234") is True


def test_nudge_detects_hebrew_address_pattern() -> None:
    assert should_nudge("הכתובת שלי היא רחוב הרצל 5") is True


def test_nudge_detects_birthday_pattern() -> None:
    assert should_nudge("יום הולדת של דני ב-15 למרץ") is True


def test_nudge_detects_allergy_pattern() -> None:
    assert should_nudge("אני אלרגי לבוטנים") is True


def test_nudge_detects_remember_pattern() -> None:
    assert should_nudge("תזכור שהפגישה ביום שלישי") is True


def test_nudge_detects_preference_pattern() -> None:
    assert should_nudge("אני אוהב קפה שחור") is True


def test_nudge_detects_english_remember_pattern() -> None:
    assert should_nudge("remember that the meeting is Tuesday") is True


def test_nudge_ignores_regular_message() -> None:
    assert should_nudge("מה המצב?") is False


def test_nudge_ignores_task_command() -> None:
    assert should_nudge("משימה חדשה: לקנות חלב") is False


def test_nudge_ignores_empty_string() -> None:
    assert should_nudge("") is False


def test_nudge_ignores_greeting() -> None:
    assert should_nudge("שלום") is False


# ── maybe_save_nudge integration tests ───────────────────────────


@pytest.mark.asyncio
async def test_maybe_save_nudge_saves_when_pattern_matches() -> None:
    """When message matches a fact pattern, a memory should be saved."""
    db = MagicMock()
    member_id = uuid4()

    mock_memory = MagicMock()
    mock_memory.id = uuid4()

    with patch("src.services.memory_nudge.check_exclusion", return_value=False), \
         patch("src.services.memory_nudge.save_memory", new_callable=AsyncMock, return_value=mock_memory):
        result = await maybe_save_nudge(db, member_id, "הקוד הוא 5678", "שמרתי")
    assert result is True


@pytest.mark.asyncio
async def test_maybe_save_nudge_skips_when_no_pattern() -> None:
    """When message doesn't match any fact pattern, nothing is saved."""
    db = MagicMock()
    member_id = uuid4()

    result = await maybe_save_nudge(db, member_id, "מה שלומך?", "הכל טוב")
    assert result is False


@pytest.mark.asyncio
async def test_maybe_save_nudge_skips_when_excluded() -> None:
    """When content is excluded by PII rules, nothing is saved."""
    db = MagicMock()
    member_id = uuid4()

    with patch("src.services.memory_nudge.check_exclusion", return_value=True):
        result = await maybe_save_nudge(db, member_id, "הקוד הוא 1234", "ok")
    assert result is False


@pytest.mark.asyncio
async def test_maybe_save_nudge_returns_false_when_save_fails() -> None:
    """When save_memory returns None, maybe_save_nudge returns False."""
    db = MagicMock()
    member_id = uuid4()

    with patch("src.services.memory_nudge.check_exclusion", return_value=False), \
         patch("src.services.memory_nudge.save_memory", new_callable=AsyncMock, return_value=None):
        result = await maybe_save_nudge(db, member_id, "הקוד הוא 9999", "ok")
    assert result is False


@pytest.mark.asyncio
async def test_maybe_save_nudge_truncates_long_messages() -> None:
    """Messages longer than 500 chars are truncated before saving."""
    db = MagicMock()
    member_id = uuid4()
    long_msg = "תזכור ש" + "א" * 600

    mock_memory = MagicMock()
    mock_memory.id = uuid4()

    with patch("src.services.memory_nudge.check_exclusion", return_value=False), \
         patch("src.services.memory_nudge.save_memory", new_callable=AsyncMock, return_value=mock_memory) as mock_save:
        await maybe_save_nudge(db, member_id, long_msg, "ok")
        # Verify the content passed to save_memory is truncated
        call_args = mock_save.call_args
        saved_content = call_args.kwargs.get("content") or call_args[1].get("content", "")
        if not saved_content:
            # positional args
            saved_content = call_args[0][2] if len(call_args[0]) > 2 else ""
        assert len(saved_content) <= 500
