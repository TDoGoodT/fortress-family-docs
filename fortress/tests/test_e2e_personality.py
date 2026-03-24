"""Personality consistency tests — Hebrew response templates used everywhere.

Sprint R3, Requirement 7.
"""

import re

from src.prompts.personality import (
    GREETINGS,
    TEMPLATES,
    _PRIORITY_EMOJI,
    format_task_list,
    get_greeting,
)


# ── 1. Error responses use templates ────────────────────────────

def test_error_responses_use_templates():
    """All error-related template values should contain Hebrew text."""
    error_keys = [
        "error_fallback",
        "permission_denied",
        "verification_failed",
        "task_not_found",
        "recurring_not_found",
        "need_list_first",
    ]
    for key in error_keys:
        val = TEMPLATES[key]
        # Should contain at least one Hebrew character
        assert re.search(r"[\u0590-\u05FF]", val), f"Template '{key}' should contain Hebrew"


# ── 2. Permission denied has 🔒 ─────────────────────────────────

def test_permission_denied_has_lock_emoji():
    """Permission denied template should contain 🔒."""
    assert "🔒" in TEMPLATES["permission_denied"]


# ── 3. Verification failed uses template ────────────────────────

def test_verification_failed_uses_template():
    """Verification failed template should exist and contain Hebrew."""
    val = TEMPLATES["verification_failed"]
    assert re.search(r"[\u0590-\u05FF]", val)


# ── 4. Greeting includes member name ────────────────────────────

def test_greeting_includes_name():
    """Greeting should include the member name."""
    greeting = get_greeting("שגב", 9)
    assert "שגב" in greeting


# ── 5. Greeting changes by time of day ──────────────────────────

def test_greeting_time_of_day():
    """Greetings should use different templates for different times."""
    morning = get_greeting("Test", 8)
    afternoon = get_greeting("Test", 14)
    evening = get_greeting("Test", 19)
    night = get_greeting("Test", 2)

    assert "בוקר" in morning
    assert "צהריים" in afternoon
    assert "ערב" in evening
    # Night greeting is different from the others
    assert morning != afternoon != evening != night


# ── 6. Task list uses priority emojis ───────────────────────────

def test_task_list_priority_emojis():
    """Task list should use priority emojis: 🔴🟡🟢⚪."""
    tasks = [
        {"title": "urgent task", "priority": "urgent", "due_date": None},
        {"title": "high task", "priority": "high", "due_date": None},
        {"title": "normal task", "priority": "normal", "due_date": None},
        {"title": "low task", "priority": "low", "due_date": None},
    ]
    formatted = format_task_list(tasks)
    assert "🔴" in formatted
    assert "🟡" in formatted
    assert "🟢" in formatted
    assert "⚪" in formatted


# ── 7. No English error messages ────────────────────────────────

def test_no_english_error_messages():
    """All template values should not contain common English error patterns."""
    english_errors = [
        "error", "exception", "failed", "invalid", "not found",
        "unauthorized", "forbidden", "internal server",
    ]
    for key, val in TEMPLATES.items():
        val_lower = val.lower()
        for err in english_errors:
            assert err not in val_lower, (
                f"Template '{key}' contains English error '{err}': {val}"
            )
