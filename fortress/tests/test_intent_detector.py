"""Unit tests for the intent detector service."""

import inspect

from src.services import intent_detector
from src.services.intent_detector import INTENTS, detect_intent


# ── INTENTS dict structure ───────────────────────────────────────


def test_intents_contains_all_required() -> None:
    """INTENTS dict should contain all required intents."""
    required = {
        "list_tasks", "create_task", "complete_task", "greeting",
        "upload_document", "list_documents", "ask_question", "unknown",
        "delete_task", "list_recurring", "create_recurring", "delete_recurring",
        "report_bug", "list_bugs",
        "cancel_action", "update_task",
        "multi_intent", "ambiguous", "bulk_delete_tasks", "bulk_delete_range",
        "store_info",
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


# ── Delete task keyword matching ─────────────────────────────────


def test_hebrew_delete_task_machak_meshima() -> None:
    assert detect_intent("מחק משימה", False) == "delete_task"


def test_hebrew_delete_task_machak_standalone() -> None:
    assert detect_intent("מחק", False) == "delete_task"


def test_hebrew_delete_task_haser_meshima() -> None:
    assert detect_intent("הסר משימה", False) == "delete_task"


def test_hebrew_delete_task_batel_meshima() -> None:
    assert detect_intent("בטל משימה", False) == "delete_task"


def test_english_delete_task() -> None:
    assert detect_intent("delete task", False) == "delete_task"


def test_hebrew_delete_task_with_number() -> None:
    """'מחק משימה 3' should also return delete_task (substring match)."""
    assert detect_intent("מחק משימה 3", False) == "delete_task"


# ── Bug tracker keyword matching (STABLE-6) ──────────────────────


def test_hebrew_report_bug_prefix() -> None:
    """'באג: ...' should return report_bug."""
    assert detect_intent("באג: תמונה לא נשמרת", False) == "report_bug"


def test_hebrew_report_bug_standalone() -> None:
    """'באג' alone should return report_bug."""
    assert detect_intent("באג", False) == "report_bug"


def test_english_report_bug_prefix() -> None:
    """'bug: ...' should return report_bug."""
    assert detect_intent("bug: photos not saving", False) == "report_bug"


def test_english_report_bug_standalone() -> None:
    """'bug' alone should return report_bug."""
    assert detect_intent("bug", False) == "report_bug"


def test_hebrew_list_bugs() -> None:
    """'באגים' should return list_bugs."""
    assert detect_intent("באגים", False) == "list_bugs"


def test_hebrew_list_bugs_alt() -> None:
    """'רשימת באגים' should return list_bugs."""
    assert detect_intent("רשימת באגים", False) == "list_bugs"


def test_english_list_bugs() -> None:
    """'bugs' should return list_bugs."""
    assert detect_intent("bugs", False) == "list_bugs"


def test_intents_includes_bug_tracker() -> None:
    """INTENTS dict should include report_bug and list_bugs."""
    assert "report_bug" in INTENTS
    assert "list_bugs" in INTENTS


# ── Cancel action keyword matching (Sprint 1) ────────────────────


def test_cancel_azov() -> None:
    """'עזוב' should return cancel_action."""
    assert detect_intent("עזוב", False) == "cancel_action"


def test_cancel_taazov() -> None:
    """'תעזוב' should return cancel_action."""
    assert detect_intent("תעזוב", False) == "cancel_action"


def test_cancel_batel() -> None:
    """'בטל' should return cancel_action."""
    assert detect_intent("בטל", False) == "cancel_action"


def test_cancel_tavtel() -> None:
    """'תבטל' should return cancel_action."""
    assert detect_intent("תבטל", False) == "cancel_action"


def test_cancel_lo() -> None:
    """'לא' should return cancel_action."""
    assert detect_intent("לא", False) == "cancel_action"


def test_cancel_english() -> None:
    """'cancel' should return cancel_action."""
    assert detect_intent("cancel", False) == "cancel_action"


def test_cancel_al_taase_et_ze() -> None:
    """'אל תעשה את זה' should return cancel_action (prefix match)."""
    assert detect_intent("אל תעשה את זה", False) == "cancel_action"


def test_cancel_al_timchak() -> None:
    """'אל תמחק' should return cancel_action (prefix match)."""
    assert detect_intent("אל תמחק", False) == "cancel_action"


# ── Update task keyword matching (Sprint 1) ──────────────────────


def test_update_teshane() -> None:
    """'תשנה' should return update_task."""
    assert detect_intent("תשנה", False) == "update_task"


def test_update_taadken() -> None:
    """'תעדכן' should return update_task."""
    assert detect_intent("תעדכן", False) == "update_task"


def test_update_adken() -> None:
    """'עדכן' should return update_task."""
    assert detect_intent("עדכן", False) == "update_task"


def test_update_shane() -> None:
    """'שנה' should return update_task."""
    assert detect_intent("שנה", False) == "update_task"


def test_update_english() -> None:
    """'update' should return update_task."""
    assert detect_intent("update", False) == "update_task"
