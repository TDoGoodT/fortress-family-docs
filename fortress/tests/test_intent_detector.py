"""Unit tests for the intent detector service."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.intent_detector import INTENTS, detect_intent


def _mock_llm(return_value: str = "unknown") -> MagicMock:
    llm = MagicMock()
    llm.generate = AsyncMock(return_value=return_value)
    return llm


# ── INTENTS dict structure ───────────────────────────────────────


def test_intents_contains_all_required() -> None:
    """INTENTS dict should contain all 8 required intents."""
    required = {
        "list_tasks", "create_task", "complete_task", "greeting",
        "upload_document", "list_documents", "ask_question", "unknown",
    }
    assert required == set(INTENTS.keys())


def test_intents_all_local_tier() -> None:
    """All intents should map to 'local' model tier."""
    for intent, config in INTENTS.items():
        assert config["model_tier"] == "local", f"{intent} is not local tier"


# ── Media detection ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_media_returns_upload_document() -> None:
    """has_media=True should always return upload_document."""
    llm = _mock_llm()
    result = await detect_intent("some text", has_media=True, llm_client=llm)
    assert result == "upload_document"


@pytest.mark.asyncio
async def test_media_overrides_keywords() -> None:
    """has_media=True should override keyword matching."""
    llm = _mock_llm()
    result = await detect_intent("משימות", has_media=True, llm_client=llm)
    assert result == "upload_document"


# ── Hebrew keyword matching ──────────────────────────────────────


@pytest.mark.asyncio
async def test_hebrew_list_tasks() -> None:
    llm = _mock_llm()
    assert await detect_intent("משימות", False, llm) == "list_tasks"


@pytest.mark.asyncio
async def test_hebrew_list_tasks_alt() -> None:
    llm = _mock_llm()
    assert await detect_intent("מה המשימות", False, llm) == "list_tasks"


@pytest.mark.asyncio
async def test_hebrew_create_task() -> None:
    llm = _mock_llm()
    assert await detect_intent("משימה חדשה: לקנות חלב", False, llm) == "create_task"


@pytest.mark.asyncio
async def test_hebrew_complete_task() -> None:
    llm = _mock_llm()
    assert await detect_intent("סיום משימה 2", False, llm) == "complete_task"


@pytest.mark.asyncio
async def test_hebrew_complete_task_done() -> None:
    llm = _mock_llm()
    assert await detect_intent("בוצע", False, llm) == "complete_task"


@pytest.mark.asyncio
async def test_hebrew_greeting_shalom() -> None:
    llm = _mock_llm()
    assert await detect_intent("שלום", False, llm) == "greeting"


@pytest.mark.asyncio
async def test_hebrew_greeting_hey() -> None:
    llm = _mock_llm()
    assert await detect_intent("היי", False, llm) == "greeting"


@pytest.mark.asyncio
async def test_hebrew_greeting_boker_tov() -> None:
    llm = _mock_llm()
    assert await detect_intent("בוקר טוב", False, llm) == "greeting"


@pytest.mark.asyncio
async def test_hebrew_list_documents() -> None:
    llm = _mock_llm()
    assert await detect_intent("מסמכים", False, llm) == "list_documents"


# ── English keyword matching ─────────────────────────────────────


@pytest.mark.asyncio
async def test_english_list_tasks() -> None:
    llm = _mock_llm()
    assert await detect_intent("tasks", False, llm) == "list_tasks"


@pytest.mark.asyncio
async def test_english_create_task() -> None:
    llm = _mock_llm()
    assert await detect_intent("new task: buy milk", False, llm) == "create_task"


@pytest.mark.asyncio
async def test_english_complete_task() -> None:
    llm = _mock_llm()
    assert await detect_intent("done 3", False, llm) == "complete_task"


@pytest.mark.asyncio
async def test_english_greeting() -> None:
    llm = _mock_llm()
    assert await detect_intent("hello", False, llm) == "greeting"


@pytest.mark.asyncio
async def test_english_list_documents() -> None:
    llm = _mock_llm()
    assert await detect_intent("documents", False, llm) == "list_documents"


# ── LLM fallback ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_llm_fallback_invoked() -> None:
    """When no keyword matches, LLM should be called."""
    llm = _mock_llm(return_value="ask_question")
    result = await detect_intent("מה מזג האוויר?", False, llm)
    assert result == "ask_question"
    llm.generate.assert_called_once()


@pytest.mark.asyncio
async def test_llm_failure_returns_unknown() -> None:
    """When LLM fails, should return 'unknown'."""
    llm = MagicMock()
    llm.generate = AsyncMock(side_effect=Exception("connection error"))
    result = await detect_intent("random text", False, llm)
    assert result == "unknown"


@pytest.mark.asyncio
async def test_llm_invalid_intent_returns_unknown() -> None:
    """When LLM returns an invalid intent, should return 'unknown'."""
    llm = _mock_llm(return_value="invalid_intent_name")
    result = await detect_intent("random text", False, llm)
    assert result == "unknown"
