"""Unit tests for the time_context utility module."""

from datetime import datetime
from unittest.mock import patch, MagicMock

import pytz

from src.utils.time_context import (
    get_time_context,
    format_time_for_prompt,
    _month_name_he,
)


IL_TZ = pytz.timezone("Asia/Jerusalem")

# A fixed datetime for deterministic tests: Wednesday, 15 Jan 2025, 14:30 IST
FIXED_NOW = IL_TZ.localize(datetime(2025, 1, 15, 14, 30, 0))


# ── get_time_context ─────────────────────────────────────────────


@patch("src.utils.time_context.datetime")
def test_get_time_context_returns_all_keys(mock_dt) -> None:
    """get_time_context should return a dict with all required keys."""
    mock_dt.now.return_value = FIXED_NOW
    mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

    ctx = get_time_context()

    required_keys = {
        "now", "today_date", "today_day_he", "today_display",
        "tomorrow_date", "tomorrow_display", "current_time", "hour",
    }
    assert required_keys == set(ctx.keys())


@patch("src.utils.time_context.datetime")
def test_get_time_context_values(mock_dt) -> None:
    """get_time_context should return correct values for a known date."""
    mock_dt.now.return_value = FIXED_NOW
    mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

    ctx = get_time_context()

    assert ctx["today_date"] == "2025-01-15"
    assert ctx["current_time"] == "14:30"
    assert ctx["hour"] == 14
    # Wednesday = weekday 2 → "רביעי"
    assert "רביעי" in ctx["today_day_he"]


# ── format_time_for_prompt ───────────────────────────────────────


@patch("src.utils.time_context.datetime")
def test_format_time_for_prompt_non_empty(mock_dt) -> None:
    """format_time_for_prompt should return a non-empty string containing today's date."""
    mock_dt.now.return_value = FIXED_NOW
    mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

    result = format_time_for_prompt()

    assert len(result) > 0
    assert "2025-01-15" in result


@patch("src.utils.time_context.datetime")
def test_format_time_for_prompt_contains_hebrew(mock_dt) -> None:
    """format_time_for_prompt should contain Hebrew text."""
    mock_dt.now.return_value = FIXED_NOW
    mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

    result = format_time_for_prompt()

    assert "היום" in result
    assert "מחר" in result


# ── _month_name_he ───────────────────────────────────────────────


def test_month_name_he_all_months() -> None:
    """_month_name_he should return correct Hebrew names for months 1-12."""
    expected = {
        1: "ינואר", 2: "פברואר", 3: "מרץ",
        4: "אפריל", 5: "מאי", 6: "יוני",
        7: "יולי", 8: "אוגוסט", 9: "ספטמבר",
        10: "אוקטובר", 11: "נובמבר", 12: "דצמבר",
    }
    for month, name in expected.items():
        assert _month_name_he(month) == name


def test_month_name_he_invalid_zero() -> None:
    """_month_name_he should return empty string for month 0."""
    assert _month_name_he(0) == ""


def test_month_name_he_invalid_thirteen() -> None:
    """_month_name_he should return empty string for month 13."""
    assert _month_name_he(13) == ""
