"""Unit tests for the intent detector service."""

import inspect

from src.services import intent_detector
from src.services.intent_detector import INTENTS, detect_intent


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


def test_media_returns_upload_document() -> None:
    """has_media=True should always return upload_document."""
    result = detect_intent("some text", has_media=True)
    assert result == "upload_document"


def test_media_overrides_keywords() -> None:
    """has_media=True should override keyword matching."""
    result = detect_intent("משימות", has_media=True)
    assert result == "upload_document"


# ── Hebrew keyword matching ──────────────────────────────────────


def test_hebrew_list_tasks() -> None:
    assert detect_intent("משימות", False) == "list_tasks"


def test_hebrew_list_tasks_alt() -> None:
    assert detect_intent("מה המשימות", False) == "list_tasks"


def test_hebrew_create_task() -> None:
    assert detect_intent("משימה חדשה: לקנות חלב", False) == "create_task"


def test_hebrew_complete_task() -> None:
    assert detect_intent("סיום משימה 2", False) == "complete_task"


def test_hebrew_complete_task_done() -> None:
    assert detect_intent("בוצע", False) == "complete_task"


def test_hebrew_greeting_shalom() -> None:
    assert detect_intent("שלום", False) == "greeting"


def test_hebrew_greeting_hey() -> None:
    assert detect_intent("היי", False) == "greeting"


def test_hebrew_greeting_boker_tov() -> None:
    assert detect_intent("בוקר טוב", False) == "greeting"


def test_hebrew_list_documents() -> None:
    assert detect_intent("מסמכים", False) == "list_documents"


# ── English keyword matching ─────────────────────────────────────


def test_english_list_tasks() -> None:
    assert detect_intent("tasks", False) == "list_tasks"


def test_english_create_task() -> None:
    assert detect_intent("new task: buy milk", False) == "create_task"


def test_english_complete_task() -> None:
    assert detect_intent("done 3", False) == "complete_task"


def test_english_greeting() -> None:
    assert detect_intent("hello", False) == "greeting"


def test_english_list_documents() -> None:
    assert detect_intent("documents", False) == "list_documents"


# ── No keyword → needs_llm ──────────────────────────────────────


def test_no_keyword_returns_needs_llm() -> None:
    """Non-keyword text with no media should return 'needs_llm'."""
    assert detect_intent("מה מזג האוויר?", False) == "needs_llm"


# ── Synchronous / no-Ollama verification ─────────────────────────


def test_detect_intent_is_sync() -> None:
    """detect_intent should be a plain function, not a coroutine."""
    assert not inspect.iscoroutinefunction(detect_intent)


def test_no_ollama_import() -> None:
    """intent_detector module source should have no OllamaClient reference."""
    source = inspect.getsource(intent_detector)
    assert "OllamaClient" not in source


def test_no_llm_fallback_function() -> None:
    """_detect_intent_with_llm should not exist in the module."""
    assert not hasattr(intent_detector, "_detect_intent_with_llm")
