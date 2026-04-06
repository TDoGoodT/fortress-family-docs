"""Tests for compute_text_quality_score and get_quality_band."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.services.image_preprocessor import (
    compute_text_quality_score,
    get_quality_band,
)


# ── compute_text_quality_score tests ─────────────────────────────


def test_clean_hebrew_text_high_score() -> None:
    """Clean Hebrew text produces a high quality score."""
    text = "שלום עולם\nזהו מסמך בדיקה\nעם מספר שורות של טקסט עברי"
    score = compute_text_quality_score(text)
    assert score >= 0.5, f"Clean Hebrew text scored {score}, expected >= 0.5"


def test_noisy_gibberish_low_score() -> None:
    """Noisy/gibberish text produces a low quality score."""
    text = "xkjhdf bcdfghjklmnp qrstvwxyz bcdfghjklmnpqrst vwxyz bcdfghjklmnpqrstvwxyz"
    score = compute_text_quality_score(text)
    assert score < 0.5, f"Gibberish text scored {score}, expected < 0.5"


def test_empty_string_returns_zero() -> None:
    """Empty string returns 0.0."""
    assert compute_text_quality_score("") == 0.0


def test_whitespace_only_returns_zero() -> None:
    """Whitespace-only string returns 0.0."""
    assert compute_text_quality_score("   \t\n  ") == 0.0


def test_none_like_empty() -> None:
    """None-ish input returns 0.0."""
    assert compute_text_quality_score("") == 0.0


@given(st.text(min_size=0, max_size=500))
@settings(max_examples=200)
def test_property_score_always_in_range(text: str) -> None:
    """Property: any random string produces a float in [0.0, 1.0]."""
    score = compute_text_quality_score(text)
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


# ── get_quality_band tests ───────────────────────────────────────


@pytest.mark.parametrize("score,expected", [
    (0.0, "LOW"),
    (0.29, "LOW"),
    (0.3, "BORDERLINE"),
    (0.49, "BORDERLINE"),
    (0.5, "GOOD"),
    (1.0, "GOOD"),
    (0.299, "LOW"),
    (0.999, "GOOD"),
])
def test_quality_band_boundaries(score: float, expected: str) -> None:
    """get_quality_band matches threshold ranges for all boundary values."""
    assert get_quality_band(score) == expected
