"""Tests for system_prompts — MEMORY_EXTRACTOR category enforcement."""

from src.prompts.system_prompts import MEMORY_EXTRACTOR


def test_memory_extractor_contains_all_valid_categories():
    """MEMORY_EXTRACTOR prompt lists all five valid categories."""
    for cat in ("preference", "goal", "fact", "habit", "context"):
        assert cat in MEMORY_EXTRACTOR, f"Missing category '{cat}' in MEMORY_EXTRACTOR"


def test_memory_extractor_contains_hebrew_instructions():
    """MEMORY_EXTRACTOR prompt contains Hebrew category enforcement."""
    assert "קטגוריה חייבת להיות אחת מאלה בלבד" in MEMORY_EXTRACTOR


def test_memory_extractor_warns_against_invalid_categories():
    """MEMORY_EXTRACTOR prompt warns against using 'task', 'reminder', 'note'."""
    assert "task" in MEMORY_EXTRACTOR
    assert "reminder" in MEMORY_EXTRACTOR
    assert "note" in MEMORY_EXTRACTOR
    assert 'אל תשתמש ב-"task"' in MEMORY_EXTRACTOR


def test_memory_extractor_context_as_default():
    """MEMORY_EXTRACTOR prompt instructs to use 'context' as default."""
    assert "context" in MEMORY_EXTRACTOR
    assert "ברירת מחדל" in MEMORY_EXTRACTOR
