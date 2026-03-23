"""Unit tests for priority-based intent classification (Sprint 2 — Req 9.1).

Validates the 4-tier priority system in detect_intent:
  Priority 0: Cancel override ("אל " prefix, "לא" exact)
  Priority 1: Exact phrases (including bulk patterns)
  Priority 2: Action verbs (substring match)
  Priority 3: Standalone keywords (exact match)
  Priority 4: No match → needs_llm
"""

from src.services.intent_detector import detect_intent


# ── Priority 0: Cancel override ─────────────────────────────────


def test_p0_al_timchak_cancel() -> None:
    """'אל תמחק' → cancel_action (P0 prefix match)."""
    assert detect_intent("אל תמחק", has_media=False) == "cancel_action"


def test_p0_lo_cancel() -> None:
    """'לא' → cancel_action (P0 exact match)."""
    assert detect_intent("לא", has_media=False) == "cancel_action"


def test_p0_cancel_overrides_all() -> None:
    """'אל תיצור משימה' → cancel_action (P0 beats P1/P2 create keywords)."""
    assert detect_intent("אל תיצור משימה", has_media=False) == "cancel_action"


# ── Priority 1: Exact phrases ───────────────────────────────────


def test_p1_create_task_prefix() -> None:
    """'משימה חדשה: X' → create_task."""
    assert detect_intent("משימה חדשה: לקנות חלב", has_media=False) == "create_task"


def test_p1_delete_task_phrase() -> None:
    """'מחק משימה' → delete_task."""
    assert detect_intent("מחק משימה", has_media=False) == "delete_task"


def test_p1_complete_task_phrase() -> None:
    """'סיום משימה' → complete_task."""
    assert detect_intent("סיום משימה", has_media=False) == "complete_task"


def test_p1_report_bug_prefix() -> None:
    """'באג:' → report_bug."""
    assert detect_intent("באג: תמונה לא נשמרת", has_media=False) == "report_bug"


def test_p1_bulk_delete_all() -> None:
    """'מחק הכל' → bulk_delete_tasks."""
    assert detect_intent("מחק הכל", has_media=False) == "bulk_delete_tasks"


def test_p1_bulk_delete_range_dash() -> None:
    """'מחק 1-5' → bulk_delete_range."""
    assert detect_intent("מחק 1-5", has_media=False) == "bulk_delete_range"


def test_p1_bulk_delete_range_ad() -> None:
    """'מחק 2 עד 4' → bulk_delete_range."""
    assert detect_intent("מחק 2 עד 4", has_media=False) == "bulk_delete_range"


# ── Priority 2: Action verbs ────────────────────────────────────


def test_p2_timchak_delete() -> None:
    """'תמחק' → delete_task (P2 verb)."""
    assert detect_intent("תמחק", has_media=False) == "delete_task"


def test_p2_titzor_create() -> None:
    """'תיצור' → create_task (P2 verb)."""
    assert detect_intent("תיצור", has_media=False) == "create_task"


def test_p2_taadken_update() -> None:
    """'תעדכן' → update_task (P2 verb)."""
    assert detect_intent("תעדכן", has_media=False) == "update_task"


def test_p2_butzah_complete() -> None:
    """'בוצע' → complete_task (P2 verb)."""
    assert detect_intent("בוצע", has_media=False) == "complete_task"


# ── Priority 3: Standalone keywords ─────────────────────────────


def test_p3_meshimot_list() -> None:
    """'משימות' → list_tasks (P3 standalone)."""
    assert detect_intent("משימות", has_media=False) == "list_tasks"


def test_p3_shalom_greeting() -> None:
    """'שלום' → greeting (P3 standalone)."""
    assert detect_intent("שלום", has_media=False) == "greeting"


def test_p3_bagim_list_bugs() -> None:
    """'באגים' → list_bugs (P3 standalone)."""
    assert detect_intent("באגים", has_media=False) == "list_bugs"


# ── Special case: "משימה" singular → needs_llm ──────────────────


def test_meshima_singular_needs_llm() -> None:
    """'משימה' singular (no action prefix) → needs_llm."""
    assert detect_intent("משימה", has_media=False) == "needs_llm"


# ── Priority ordering ───────────────────────────────────────────


def test_p1_beats_p2_delete_phrase() -> None:
    """'מחק משימה חדשה' → delete_task (P1 phrase beats P2 verbs)."""
    assert detect_intent("מחק משימה חדשה", has_media=False) == "delete_task"


def test_p0_beats_all_cancel_create() -> None:
    """'אל תיצור משימה' → cancel_action (P0 beats all)."""
    assert detect_intent("אל תיצור משימה", has_media=False) == "cancel_action"
