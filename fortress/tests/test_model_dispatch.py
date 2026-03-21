"""Unit tests for ModelDispatcher."""

import pytest
from unittest.mock import AsyncMock, patch

from src.services.bedrock_client import HEBREW_FALLBACK
from src.services.model_dispatch import ModelDispatcher


def _make_dispatcher(
    openrouter_result=None,
    bedrock_result=None,
    ollama_result=None,
    openrouter_api_key="test-key",
):
    """Build a ModelDispatcher with mocked clients."""
    bedrock = AsyncMock()
    bedrock.generate = AsyncMock(return_value=bedrock_result or HEBREW_FALLBACK)

    openrouter = AsyncMock()
    openrouter.generate = AsyncMock(return_value=openrouter_result or HEBREW_FALLBACK)

    ollama = AsyncMock()
    ollama.generate = AsyncMock(return_value=ollama_result or HEBREW_FALLBACK)

    with patch("src.services.model_dispatch.OPENROUTER_API_KEY", openrouter_api_key):
        dispatcher = ModelDispatcher(
            bedrock_client=bedrock,
            openrouter_client=openrouter,
            ollama_client=ollama,
        )

    return dispatcher, bedrock, openrouter, ollama, openrouter_api_key


@pytest.mark.asyncio
async def test_dispatch_low_sensitivity_openrouter_succeeds():
    """Low sensitivity intent dispatches to openrouter first."""
    dispatcher, bedrock, openrouter, ollama, key = _make_dispatcher(
        openrouter_result="שלום!",
    )
    with patch("src.services.model_dispatch.OPENROUTER_API_KEY", key):
        result = await dispatcher.dispatch("hello", "sys", "greeting")
    assert result == "שלום!"
    openrouter.generate.assert_called_once()
    bedrock.generate.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_openrouter_fails_falls_back_to_bedrock():
    """When openrouter returns fallback, bedrock is tried next."""
    dispatcher, bedrock, openrouter, ollama, key = _make_dispatcher(
        openrouter_result=HEBREW_FALLBACK,
        bedrock_result="תשובה מבדרוק",
    )
    with patch("src.services.model_dispatch.OPENROUTER_API_KEY", key):
        result = await dispatcher.dispatch("hello", "sys", "greeting")
    assert result == "תשובה מבדרוק"
    openrouter.generate.assert_called_once()
    bedrock.generate.assert_called_once()


@pytest.mark.asyncio
async def test_dispatch_openrouter_and_bedrock_fail_falls_back_to_ollama():
    """When openrouter and bedrock fail, ollama is tried."""
    dispatcher, bedrock, openrouter, ollama, key = _make_dispatcher(
        openrouter_result=HEBREW_FALLBACK,
        bedrock_result=HEBREW_FALLBACK,
        ollama_result="תשובה מאולמה",
    )
    with patch("src.services.model_dispatch.OPENROUTER_API_KEY", key):
        result = await dispatcher.dispatch("hello", "sys", "greeting")
    assert result == "תשובה מאולמה"


@pytest.mark.asyncio
async def test_dispatch_all_fail_returns_hebrew_fallback():
    """When all providers fail, returns HEBREW_FALLBACK."""
    dispatcher, bedrock, openrouter, ollama, key = _make_dispatcher(
        openrouter_result=HEBREW_FALLBACK,
        bedrock_result=HEBREW_FALLBACK,
        ollama_result=HEBREW_FALLBACK,
    )
    with patch("src.services.model_dispatch.OPENROUTER_API_KEY", key):
        result = await dispatcher.dispatch("hello", "sys", "greeting")
    assert result == HEBREW_FALLBACK


@pytest.mark.asyncio
async def test_dispatch_hebrew_fallback_treated_as_failure():
    """Provider returning HEBREW_FALLBACK is treated as failure."""
    dispatcher, bedrock, openrouter, ollama, key = _make_dispatcher(
        openrouter_result=HEBREW_FALLBACK,
        bedrock_result="success",
    )
    with patch("src.services.model_dispatch.OPENROUTER_API_KEY", key):
        result = await dispatcher.dispatch("hello", "sys", "greeting")
    assert result == "success"
    # openrouter was tried first but failed, bedrock succeeded
    assert openrouter.generate.call_count == 1
    assert bedrock.generate.call_count == 1


@pytest.mark.asyncio
async def test_dispatch_high_sensitivity_skips_openrouter():
    """High sensitivity intent goes to bedrock first, skips openrouter."""
    dispatcher, bedrock, openrouter, ollama, key = _make_dispatcher(
        bedrock_result="sensitive answer",
    )
    with patch("src.services.model_dispatch.OPENROUTER_API_KEY", key):
        result = await dispatcher.dispatch("question", "sys", "ask_question")
    assert result == "sensitive answer"
    openrouter.generate.assert_not_called()
    bedrock.generate.assert_called_once()


@pytest.mark.asyncio
async def test_dispatch_ask_question_uses_sonnet():
    """ask_question intent uses bedrock sonnet model."""
    dispatcher, bedrock, openrouter, ollama, key = _make_dispatcher(
        bedrock_result="sonnet answer",
    )
    with patch("src.services.model_dispatch.OPENROUTER_API_KEY", key):
        await dispatcher.dispatch("question", "sys", "ask_question")
    bedrock.generate.assert_called_once_with("question", "sys", model="sonnet")


@pytest.mark.asyncio
async def test_dispatch_non_ask_question_uses_haiku():
    """Non-ask_question intent uses bedrock haiku model."""
    dispatcher, bedrock, openrouter, ollama, key = _make_dispatcher(
        openrouter_result=HEBREW_FALLBACK,
        bedrock_result="haiku answer",
    )
    with patch("src.services.model_dispatch.OPENROUTER_API_KEY", key):
        await dispatcher.dispatch("hello", "sys", "list_tasks")
    bedrock.generate.assert_called_once_with("hello", "sys", model="haiku")


@pytest.mark.asyncio
async def test_dispatch_empty_api_key_skips_openrouter():
    """Empty API key skips openrouter without HTTP call."""
    dispatcher, bedrock, openrouter, ollama, _ = _make_dispatcher(
        bedrock_result="bedrock answer",
        openrouter_api_key="",
    )
    with patch("src.services.model_dispatch.OPENROUTER_API_KEY", ""):
        result = await dispatcher.dispatch("hello", "sys", "greeting")
    assert result == "bedrock answer"
    openrouter.generate.assert_not_called()
    bedrock.generate.assert_called_once()


@pytest.mark.asyncio
async def test_dispatch_logs_attempts():
    """Dispatch logs each attempt."""
    dispatcher, bedrock, openrouter, ollama, key = _make_dispatcher(
        openrouter_result="success",
    )
    with patch("src.services.model_dispatch.OPENROUTER_API_KEY", key), \
         patch("src.services.model_dispatch.logger") as mock_logger:
        await dispatcher.dispatch("hello", "sys", "greeting")
    # Should have logged the successful dispatch
    assert mock_logger.info.call_count >= 1


# ── _is_valid_response validation ────────────────────────────────


@pytest.mark.asyncio
async def test_empty_string_treated_as_failure():
    """Empty string triggers fallback to next provider."""
    dispatcher, bedrock, openrouter, ollama, key = _make_dispatcher(
        openrouter_result="",
        bedrock_result="bedrock answer",
    )
    with patch("src.services.model_dispatch.OPENROUTER_API_KEY", key):
        result = await dispatcher.dispatch("hello", "sys", "greeting")
    assert result == "bedrock answer"
    openrouter.generate.assert_called_once()
    bedrock.generate.assert_called_once()


@pytest.mark.asyncio
async def test_whitespace_only_treated_as_failure():
    """Whitespace-only string triggers fallback."""
    dispatcher, bedrock, openrouter, ollama, key = _make_dispatcher(
        openrouter_result="   \n  ",
        bedrock_result="bedrock answer",
    )
    with patch("src.services.model_dispatch.OPENROUTER_API_KEY", key):
        result = await dispatcher.dispatch("hello", "sys", "greeting")
    assert result == "bedrock answer"


@pytest.mark.asyncio
async def test_too_short_treated_as_failure():
    """Single-char string triggers fallback."""
    dispatcher, bedrock, openrouter, ollama, key = _make_dispatcher(
        openrouter_result=".",
        bedrock_result="bedrock answer",
    )
    with patch("src.services.model_dispatch.OPENROUTER_API_KEY", key):
        result = await dispatcher.dispatch("hello", "sys", "greeting")
    assert result == "bedrock answer"


@pytest.mark.asyncio
async def test_valid_hebrew_not_rejected():
    """Valid Hebrew response is accepted, not confused with fallback."""
    dispatcher, bedrock, openrouter, ollama, key = _make_dispatcher(
        openrouter_result="שלום, מה שלומך?",
    )
    with patch("src.services.model_dispatch.OPENROUTER_API_KEY", key):
        result = await dispatcher.dispatch("hello", "sys", "greeting")
    assert result == "שלום, מה שלומך?"
    bedrock.generate.assert_not_called()
