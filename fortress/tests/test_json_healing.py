"""Unit tests for _heal_json() in unified_handler."""

import json

from src.services.unified_handler import _heal_json


def test_heal_json_clean_json() -> None:
    """Direct parse succeeds on first strategy."""
    raw = json.dumps({"intent": "greeting", "response": "שלום!"})
    result = _heal_json(raw)
    assert result is not None
    assert result["intent"] == "greeting"
    assert result["response"] == "שלום!"


def test_heal_json_markdown_fences() -> None:
    """Strips ```json ... ``` and parses."""
    raw = '```json\n{"intent": "greeting", "response": "שלום!"}\n```'
    result = _heal_json(raw)
    assert result is not None
    assert result["intent"] == "greeting"


def test_heal_json_markdown_fences_no_lang() -> None:
    """Strips ``` ... ``` without language tag."""
    raw = '```\n{"intent": "greeting", "response": "שלום!"}\n```'
    result = _heal_json(raw)
    assert result is not None
    assert result["intent"] == "greeting"


def test_heal_json_prefixed_text() -> None:
    """Regex extracts JSON after prefix text."""
    raw = 'Here is the response: {"intent": "greeting", "response": "שלום!"}'
    result = _heal_json(raw)
    assert result is not None
    assert result["intent"] == "greeting"


def test_heal_json_embedded_json() -> None:
    """First-brace-to-last-brace extracts embedded JSON."""
    raw = 'Some text before\n{"intent": "unknown", "response": "לא ברור"}\nSome text after'
    result = _heal_json(raw)
    assert result is not None
    assert result["intent"] == "unknown"
    assert result["response"] == "לא ברור"


def test_heal_json_plain_text_returns_none() -> None:
    """Returns None for non-JSON text."""
    assert _heal_json("this is just plain text") is None


def test_heal_json_empty_string_returns_none() -> None:
    """Returns None for empty input."""
    assert _heal_json("") is None
    assert _heal_json("   ") is None
    assert _heal_json(None) is None


def test_heal_json_nested_braces() -> None:
    """Correctly handles nested {} in JSON."""
    raw = json.dumps({
        "intent": "create_task",
        "response": "נוצרה משימה",
        "task_data": {"title": "לקנות חלב", "priority": "normal"},
    })
    result = _heal_json(raw)
    assert result is not None
    assert result["task_data"]["title"] == "לקנות חלב"


def test_heal_json_hebrew_text_returns_none() -> None:
    """Returns None for Hebrew-only text (caller uses raw fallback)."""
    assert _heal_json("שלום, מה שלומך היום?") is None
