"""Unit tests for the personality module and its integrations."""

import pytest

from src.prompts.personality import (
    GREETINGS,
    PERSONALITY,
    TEMPLATES,
    format_document_list,
    format_task_created,
    format_task_list,
    get_greeting,
)


# ── Module exports ───────────────────────────────────────────────


def test_personality_is_nonempty_string() -> None:
    assert isinstance(PERSONALITY, str)
    assert len(PERSONALITY) > 0


def test_greetings_has_all_keys() -> None:
    assert set(GREETINGS.keys()) == {"morning", "afternoon", "evening", "night"}


REQUIRED_TEMPLATE_KEYS = {
    "task_created",
    "task_completed",
    "task_list_empty",
    "task_list_header",
    "document_saved",
    "document_list_header",
    "document_list_empty",
    "permission_denied",
    "unknown_member",
    "inactive_member",
    "error_fallback",
    "cant_understand",
    "task_deleted",
    "task_delete_which",
    "task_not_found",
    "task_duplicate",
    "reminder_new_task",
    "scheduler_summary",
    "recurring_list_header",
    "recurring_list_empty",
    "recurring_list_item",
    "recurring_created",
    "recurring_deleted",
    "recurring_not_found",
    "bug_reported",
    "bug_list_header",
    "bug_list_empty",
    "bug_list_item",
    "confirm_delete",
    "action_cancelled",
    "cancelled",
    "task_updated",
    "task_update_which",
    "verification_failed",
}


def test_templates_has_all_required_keys() -> None:
    assert set(TEMPLATES.keys()) == REQUIRED_TEMPLATE_KEYS


def test_templates_values_are_nonempty_strings() -> None:
    for key, value in TEMPLATES.items():
        assert isinstance(value, str), f"TEMPLATES[{key!r}] is not a string"
        assert len(value) > 0, f"TEMPLATES[{key!r}] is empty"


# ── get_greeting ─────────────────────────────────────────────────


@pytest.mark.parametrize("hour", [0, 6, 12, 18])
def test_get_greeting_contains_name(hour: int) -> None:
    result = get_greeting("שגב", hour)
    assert "שגב" in result


def test_get_greeting_morning_vs_evening_differ() -> None:
    morning = get_greeting("שגב", 8)
    evening = get_greeting("שגב", 20)
    assert morning != evening


@pytest.mark.parametrize(
    "hour,expected_key",
    [
        (5, "morning"),
        (11, "morning"),
        (12, "afternoon"),
        (16, "afternoon"),
        (17, "evening"),
        (21, "evening"),
        (22, "night"),
        (4, "night"),
    ],
)
def test_get_greeting_boundary_hours(hour: int, expected_key: str) -> None:
    result = get_greeting("Test", hour)
    expected = GREETINGS[expected_key].format(name="Test")
    assert result == expected


# ── format_task_created ──────────────────────────────────────────


def test_format_task_created_includes_title() -> None:
    result = format_task_created("לקנות חלב")
    assert "לקנות חלב" in result


def test_format_task_created_with_due_date() -> None:
    result = format_task_created("לקנות חלב", "2026-04-01")
    assert "2026-04-01" in result


def test_format_task_created_without_due_date() -> None:
    result = format_task_created("לקנות חלב")
    assert "📅" not in result


# ── format_task_list ─────────────────────────────────────────────


def test_format_task_list_empty() -> None:
    assert format_task_list([]) == TEMPLATES["task_list_empty"]


def test_format_task_list_multiple_tasks() -> None:
    tasks = [
        {"title": "לקנות חלב", "priority": "normal"},
        {"title": "לשלם חשבון", "priority": "urgent"},
    ]
    result = format_task_list(tasks)
    assert "לקנות חלב" in result
    assert "לשלם חשבון" in result


def test_format_task_list_priority_emojis() -> None:
    tasks = [
        {"title": "a", "priority": "urgent"},
        {"title": "b", "priority": "high"},
        {"title": "c", "priority": "normal"},
        {"title": "d", "priority": "low"},
    ]
    result = format_task_list(tasks)
    assert "🔴" in result
    assert "🟡" in result
    assert "🟢" in result
    assert "⚪" in result


# ── System prompt integration ────────────────────────────────────


def test_fortress_base_starts_with_personality() -> None:
    from src.prompts.system_prompts import FORTRESS_BASE
    assert FORTRESS_BASE.startswith(PERSONALITY)


def test_unified_prompt_starts_with_personality() -> None:
    from src.prompts.system_prompts import UNIFIED_CLASSIFY_AND_RESPOND
    assert UNIFIED_CLASSIFY_AND_RESPOND.startswith(PERSONALITY)


def test_task_responder_starts_with_personality() -> None:
    from src.prompts.system_prompts import TASK_RESPONDER
    assert TASK_RESPONDER.startswith(PERSONALITY)


# ── format_document_list ─────────────────────────────────────────


def test_format_document_list_empty() -> None:
    assert format_document_list([]) == TEMPLATES["document_list_empty"]


def test_format_document_list_multiple_documents() -> None:
    docs = [
        {"original_filename": "invoice.pdf", "doc_type": "document", "created_at": "2026-03-01T10:00:00"},
        {"original_filename": "photo.jpg", "doc_type": "image", "created_at": "2026-03-02T12:00:00"},
    ]
    result = format_document_list(docs)
    assert "invoice.pdf" in result
    assert "photo.jpg" in result


def test_format_document_list_emojis_per_type() -> None:
    docs = [
        {"original_filename": "a.pdf", "doc_type": "document", "created_at": "2026-01-01"},
        {"original_filename": "b.jpg", "doc_type": "image", "created_at": "2026-01-01"},
        {"original_filename": "c.xlsx", "doc_type": "spreadsheet", "created_at": "2026-01-01"},
        {"original_filename": "d.zip", "doc_type": "other", "created_at": "2026-01-01"},
    ]
    result = format_document_list(docs)
    assert "📄" in result
    assert "🖼️" in result
    assert "📊" in result
    assert "📎" in result


# ── Bug tracker templates (STABLE-6) ─────────────────────────────

from src.prompts.personality import format_bug_list


def test_bug_templates_exist() -> None:
    """Bug tracker templates should be in TEMPLATES dict."""
    for key in ("bug_reported", "bug_list_header", "bug_list_empty", "bug_list_item"):
        assert key in TEMPLATES, f"Missing template key: {key}"


def test_format_bug_list_empty() -> None:
    """Empty bug list returns bug_list_empty template."""
    assert format_bug_list([]) == TEMPLATES["bug_list_empty"]


def test_format_bug_list_multiple_bugs() -> None:
    """format_bug_list formats multiple bugs correctly."""
    bugs = [
        {"description": "תמונה לא נשמרת", "created_at": "2026-03-20T10:00:00"},
        {"description": "הודעה לא נשלחת", "created_at": "2026-03-21T12:00:00"},
    ]
    result = format_bug_list(bugs)
    assert "תמונה לא נשמרת" in result
    assert "הודעה לא נשלחת" in result
    assert TEMPLATES["bug_list_header"].strip() in result


def test_format_bug_list_contains_dates() -> None:
    """format_bug_list includes date info."""
    bugs = [{"description": "test bug", "created_at": "2026-03-20T10:00:00"}]
    result = format_bug_list(bugs)
    assert "2026-03-20" in result


def test_bug_reported_template_has_description_placeholder() -> None:
    """bug_reported template should contain {description} placeholder."""
    assert "{description}" in TEMPLATES["bug_reported"]
