from __future__ import annotations

from unittest.mock import MagicMock

from src.models.schema import Document
from src.skills.document_skill import _build_document_saved_message


def test_salary_slip_saved_message_includes_structured_highlights():
    doc = MagicMock(spec=Document)
    doc.doc_type = "salary_slip"
    doc.display_name = "תלוש שכר מרץ"
    doc.original_filename = "salary_march.pdf"
    doc.review_state = "auto_verified"
    doc.doc_metadata = {
        "structured_payload": {
            "employer_name": "ACME",
            "pay_month": "2026-03",
        }
    }

    message = _build_document_saved_message(doc)

    assert "תלוש שכר" in message
    assert "2026-03" in message
    assert "7800.0" not in message
    assert "ACME" not in message


def test_salary_slip_saved_message_mentions_review_when_needed():
    doc = MagicMock(spec=Document)
    doc.doc_type = "salary_slip"
    doc.display_name = None
    doc.original_filename = "salary.pdf"
    doc.review_state = "needs_review"
    doc.doc_metadata = {"structured_payload": {}}

    message = _build_document_saved_message(doc)

    assert "מסומן לבדיקה" in message
