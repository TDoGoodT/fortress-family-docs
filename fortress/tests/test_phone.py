"""Unit tests for phone number utilities."""

from src.utils.phone import (
    canonicalize_phone,
    is_valid_israeli_phone,
    normalize_phone,
    phone_lookup_candidates,
)


def test_normalize_strips_c_us() -> None:
    assert normalize_phone("972501234567@c.us") == "972501234567"


def test_normalize_strips_non_digits() -> None:
    assert normalize_phone("972-50-123-4567") == "972501234567"


def test_normalize_strips_plus() -> None:
    assert normalize_phone("+972501234567") == "972501234567"


def test_normalize_local_number() -> None:
    assert normalize_phone("0501234567") == "0501234567"


def test_normalize_combined() -> None:
    assert normalize_phone("+972-50-123-4567@c.us") == "972501234567"


def test_normalize_lid() -> None:
    assert normalize_phone("972501234567@lid") == "972501234567"


def test_phone_lookup_candidates_include_local_and_international() -> None:
    candidates = phone_lookup_candidates("972501234567@c.us")
    assert "972501234567" in candidates
    assert "+972501234567" in candidates
    assert "0501234567" in candidates
    assert "+0501234567" in candidates


def test_canonicalize_local_to_international() -> None:
    assert canonicalize_phone("0501234567") == "972501234567"


def test_valid_israeli_972() -> None:
    assert is_valid_israeli_phone("972501234567") is True


def test_valid_israeli_05x() -> None:
    assert is_valid_israeli_phone("0501234567") is True


def test_invalid_too_short() -> None:
    assert is_valid_israeli_phone("97250123") is False


def test_invalid_no_prefix() -> None:
    assert is_valid_israeli_phone("1234567890") is False


def test_invalid_non_digits() -> None:
    assert is_valid_israeli_phone("972-501-2345") is False
