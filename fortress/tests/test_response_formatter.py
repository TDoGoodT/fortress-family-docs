"""Tests for response_formatter.py — WhatsApp truncation."""

from src.engine.response_formatter import format_response, WHATSAPP_CHAR_LIMIT, TRUNCATION_INDICATOR
from src.skills.base_skill import Result


class TestFormatResponse:
    def test_short_message_passthrough(self):
        r = Result(success=True, message="שלום!")
        assert format_response(r) == "שלום!"

    def test_exact_limit_passthrough(self):
        msg = "א" * WHATSAPP_CHAR_LIMIT
        r = Result(success=True, message=msg)
        assert format_response(r) == msg

    def test_over_limit_truncated(self):
        msg = "א" * (WHATSAPP_CHAR_LIMIT + 500)
        r = Result(success=True, message=msg)
        out = format_response(r)
        assert out.endswith(TRUNCATION_INDICATOR)
        assert len(out) == WHATSAPP_CHAR_LIMIT + len(TRUNCATION_INDICATOR)

    def test_empty_message(self):
        r = Result(success=True, message="")
        assert format_response(r) == ""
