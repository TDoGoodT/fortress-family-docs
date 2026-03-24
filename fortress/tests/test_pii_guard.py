"""Unit tests for the PII Guard service (strip_pii, restore_pii)."""

from src.services.pii_guard import ReplacementRecord, restore_pii, strip_pii


# ── 8.1 — Unit tests for each PII pattern type ──────────────────


def test_israeli_id_detected_and_replaced() -> None:
    """A 9-digit Israeli ID should be replaced with [ת.ז._1]."""
    text = "מספר ת.ז. 123456789 בבקשה"
    cleaned, records = strip_pii(text)
    assert "[ת.ז._1]" in cleaned
    assert "123456789" not in cleaned
    assert len(records) == 1
    assert records[0].original == "123456789"
    assert records[0].pattern_type == "israeli_id"


def test_phone_local_format_detected() -> None:
    """A local Israeli phone number (0XX...) should be replaced with [טלפון_N]."""
    text = "התקשר אליי 0521234567"
    cleaned, records = strip_pii(text)
    assert "[טלפון_1]" in cleaned
    assert "0521234567" not in cleaned
    assert len(records) == 1
    assert records[0].pattern_type == "phone"


def test_phone_international_format_detected() -> None:
    """International phone formats (972... and +972...) should be replaced."""
    text = "מספרים: 972521234567 ו-+972531234567"
    cleaned, records = strip_pii(text)
    assert "972521234567" not in cleaned
    assert "+972531234567" not in cleaned
    phone_records = [r for r in records if r.pattern_type == "phone"]
    assert len(phone_records) == 2


def test_credit_card_with_spaces_detected() -> None:
    """A credit card number with spaces should be replaced with [כרטיס_1]."""
    text = "כרטיס אשראי 4580 1234 5678 9012"
    cleaned, records = strip_pii(text)
    assert "[כרטיס_1]" in cleaned
    assert "4580 1234 5678 9012" not in cleaned
    assert len(records) == 1
    assert records[0].pattern_type == "credit_card"


def test_email_detected() -> None:
    """An email address should be replaced with [אימייל_1]."""
    text = "שלח מייל ל-user@example.com"
    cleaned, records = strip_pii(text)
    assert "[אימייל_1]" in cleaned
    assert "user@example.com" not in cleaned
    assert len(records) == 1
    assert records[0].pattern_type == "email"


def test_bank_account_detected() -> None:
    """An Israeli bank account number should be replaced with [חשבון בנק_1]."""
    text = "חשבון בנק 12-123456"
    cleaned, records = strip_pii(text)
    assert "[חשבון בנק_1]" in cleaned
    assert "12-123456" not in cleaned
    assert len(records) == 1
    assert records[0].pattern_type == "bank_account"


# ── 8.2 — Unit tests for multi-PII and edge cases ───────────────


def test_multiple_pii_types_in_one_string() -> None:
    """Text with both a phone and an email should have both replaced."""
    text = "טלפון 0521234567 ומייל user@example.com"
    cleaned, records = strip_pii(text)
    assert "0521234567" not in cleaned
    assert "user@example.com" not in cleaned
    assert len(records) == 2
    types = {r.pattern_type for r in records}
    assert types == {"phone", "email"}


def test_no_pii_in_text() -> None:
    """Hebrew-only text with no PII should be returned unchanged."""
    text = "שלום עולם"
    cleaned, records = strip_pii(text)
    assert cleaned == text
    assert records == []


def test_empty_string_input() -> None:
    """Empty string should return empty string with no records."""
    cleaned, records = strip_pii("")
    assert cleaned == ""
    assert records == []


def test_overlapping_pattern_nine_digit_inside_phone() -> None:
    """A phone number contains 9+ digits — the phone pattern should match, not Israeli ID."""
    text = "0521234567"
    cleaned, records = strip_pii(text)
    # Should be detected as phone, not as Israeli ID
    assert len(records) == 1
    assert records[0].pattern_type == "phone"


def test_strip_then_restore_round_trip() -> None:
    """Stripping PII and then restoring should reproduce the original text."""
    original = "ת.ז. 123456789 טלפון 0521234567 מייל test@mail.com"
    cleaned, records = strip_pii(original)
    restored = restore_pii(cleaned, records)
    assert restored == original


def test_short_numbers_not_stripped() -> None:
    """Short numbers (4-5 digits) should NOT be detected as PII."""
    text = "קוד 1234 ומספר 56789"
    cleaned, records = strip_pii(text)
    assert cleaned == text
    assert records == []


def test_hebrew_text_with_embedded_numbers() -> None:
    """Hebrew text with short embedded numbers should not trigger PII detection."""
    text = "יש לי 3 ילדים ו-2 חתולים"
    cleaned, records = strip_pii(text)
    assert cleaned == text
    assert records == []
