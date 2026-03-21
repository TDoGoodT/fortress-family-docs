"""Unit tests for the unified handler service."""

import json
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.prompts.system_prompts import UNIFIED_CLASSIFY_AND_RESPOND
from src.services.unified_handler import HEBREW_FALLBACK_MSG, handle_with_llm


def _mock_dispatcher(return_value: str) -> MagicMock:
    d = MagicMock()
    d.dispatch = AsyncMock(return_value=return_value)
    return d


# ── Valid JSON responses ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_valid_json_greeting() -> None:
    payload = json.dumps({"intent": "greeting", "response": "שלום וברכה!"})
    d = _mock_dispatcher(payload)
    intent, response, task_data = await handle_with_llm("שלום", "אבא", [], d)
    assert intent == "greeting"
    assert response == "שלום וברכה!"
    assert task_data is None


@pytest.mark.asyncio
async def test_valid_json_ask_question() -> None:
    payload = json.dumps({"intent": "ask_question", "response": "התשובה היא 42"})
    d = _mock_dispatcher(payload)
    intent, response, task_data = await handle_with_llm("מה התשובה?", "אמא", [], d)
    assert intent == "ask_question"
    assert response == "התשובה היא 42"
    assert task_data is None


# ── create_task with/without task_data ───────────────────────────


@pytest.mark.asyncio
async def test_create_task_with_task_data() -> None:
    payload = json.dumps({
        "intent": "create_task",
        "response": "נוצרה משימה חדשה",
        "task_data": {"title": "לקנות חלב", "due_date": None, "category": "groceries", "priority": "normal"},
    })
    d = _mock_dispatcher(payload)
    intent, response, task_data = await handle_with_llm("משימה חדשה: לקנות חלב", "אבא", [], d)
    assert intent == "create_task"
    assert task_data is not None
    assert task_data["title"] == "לקנות חלב"


@pytest.mark.asyncio
async def test_create_task_without_task_data() -> None:
    payload = json.dumps({"intent": "create_task", "response": "נוצרה משימה"})
    d = _mock_dispatcher(payload)
    intent, response, task_data = await handle_with_llm("צור משימה", "אבא", [], d)
    assert intent == "create_task"
    assert task_data is None


# ── Error handling ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_invalid_json_returns_fallback() -> None:
    d = _mock_dispatcher("this is not json at all")
    intent, response, task_data = await handle_with_llm("test", "user", [], d)
    assert intent == "unknown"
    assert response == HEBREW_FALLBACK_MSG
    assert task_data is None


@pytest.mark.asyncio
async def test_invalid_intent_defaults_unknown() -> None:
    payload = json.dumps({"intent": "nonexistent_intent", "response": "some text"})
    d = _mock_dispatcher(payload)
    intent, response, task_data = await handle_with_llm("test", "user", [], d)
    assert intent == "unknown"
    assert response == "some text"
    assert task_data is None


# ── Dispatcher integration ───────────────────────────────────────


@pytest.mark.asyncio
async def test_dispatcher_called_with_unified_prompt() -> None:
    payload = json.dumps({"intent": "greeting", "response": "hi"})
    d = _mock_dispatcher(payload)
    await handle_with_llm("שלום", "אבא", [], d)
    d.dispatch.assert_called_once()
    call_kwargs = d.dispatch.call_args
    assert call_kwargs.kwargs["system_prompt"] == UNIFIED_CLASSIFY_AND_RESPOND
    assert call_kwargs.kwargs["intent"] == "needs_llm"


# ── Logging ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_logging_output(caplog: pytest.LogCaptureFixture) -> None:
    payload = json.dumps({"intent": "greeting", "response": "שלום!"})
    d = _mock_dispatcher(payload)
    with caplog.at_level(logging.INFO, logger="src.services.unified_handler"):
        await handle_with_llm("שלום", "אבא", [], d)
    assert any("intent=greeting" in r.message for r in caplog.records)
    assert any("response_len=" in r.message for r in caplog.records)
    assert any("elapsed=" in r.message for r in caplog.records)
