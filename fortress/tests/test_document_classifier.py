"""Unit tests for document_classifier — keyword rules, LLM fallback, P3 property."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from src.services.document_classifier import (
    SUPPORTED_CATEGORIES,
    classify_document,
    _classify_by_keywords,
)


# ---------------------------------------------------------------------------
# Phase 1: keyword rules
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,filename,expected_category", [
    ("חשבונית מס 12345 סכום 500 ש\"ח", "invoice.pdf", "invoice"),
    ("invoice total $200", "doc.pdf", "invoice"),
    ("קבלה על תשלום", "receipt.pdf", "receipt"),
    ("receipt for purchase", "doc.pdf", "receipt"),
    ("חוזה שכירות דירה", "contract.pdf", "contract"),
    ("rental agreement signed", "agreement.docx", "contract"),
    ("דף חשבון בנק", "bank.pdf", "bank_statement"),
    ("bank statement january 2026", "statement.pdf", "bank_statement"),
    ("כרטיס אשראי חיובים", "cc.pdf", "credit_card_statement"),
    ("credit card statement", "doc.pdf", "credit_card_statement"),
    ("פוליסת ביטוח רכב", "insurance.pdf", "insurance"),
    ("insurance policy renewal", "doc.pdf", "insurance"),
    ("תעודת אחריות מוצר", "warranty.pdf", "warranty"),
    ("warranty certificate 2 years", "doc.pdf", "warranty"),
    ("עירייה תל אביב", "letter.pdf", "official_letter"),
    ("official government notice", "doc.pdf", "official_letter"),
])
def test_keyword_rules(text, filename, expected_category):
    category, confidence = _classify_by_keywords(text, filename)
    assert category == expected_category
    assert confidence == 0.8


def test_unknown_text_defaults_to_other():
    category, confidence = _classify_by_keywords("some random text", "file.pdf")
    assert category == "other"
    assert confidence == 0.0


# ---------------------------------------------------------------------------
# Phase 2: LLM fallback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_llm_fallback_called_when_phase1_low_confidence():
    """LLM fallback is invoked when Phase 1 confidence < 0.6."""
    with patch("src.services.document_classifier.llm_generate", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = '{"category": "contract", "confidence": 0.85}'
        category, confidence = await classify_document("some ambiguous text", "doc.pdf")
    mock_llm.assert_called_once()
    assert category == "contract"
    assert confidence == 0.85


@pytest.mark.asyncio
async def test_llm_parse_failure_defaults_to_other():
    """If LLM returns unparseable output, default to other."""
    with patch("src.services.document_classifier.llm_generate", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = "I cannot classify this document."
        category, confidence = await classify_document("random text", "doc.pdf")
    assert category == "other"
    assert confidence == 0.0


@pytest.mark.asyncio
async def test_llm_empty_response_defaults_to_other():
    """If LLM returns empty string, default to other."""
    with patch("src.services.document_classifier.llm_generate", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = ""
        category, confidence = await classify_document("random text", "doc.pdf")
    assert category == "other"
    assert confidence == 0.0


@pytest.mark.asyncio
async def test_llm_invalid_category_defaults_to_other():
    """If LLM returns a category not in SUPPORTED_CATEGORIES, default to other."""
    with patch("src.services.document_classifier.llm_generate", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = '{"category": "tax_return", "confidence": 0.9}'
        category, confidence = await classify_document("random text", "doc.pdf")
    assert category == "other"
    assert confidence == 0.0


# ---------------------------------------------------------------------------
# XLS/XLSX: filename-only classification
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_xlsx_filename_only_no_llm():
    """XLS/XLSX files use filename-only classification, LLM is never called."""
    with patch("src.services.document_classifier.llm_generate", new_callable=AsyncMock) as mock_llm:
        category, confidence = await classify_document("", "budget_2026.xlsx")
    mock_llm.assert_not_called()
    # filename doesn't match any keyword → other
    assert category == "other"


@pytest.mark.asyncio
async def test_xls_with_keyword_in_filename():
    """XLS with a keyword in filename should classify via Phase 1."""
    with patch("src.services.document_classifier.llm_generate", new_callable=AsyncMock) as mock_llm:
        category, confidence = await classify_document("", "invoice_march.xls")
    mock_llm.assert_not_called()
    assert category == "invoice"
    assert confidence == 0.8


# ---------------------------------------------------------------------------
# Phase 1 high-confidence skips LLM
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_high_confidence_phase1_skips_llm():
    """When Phase 1 returns confidence >= 0.6, LLM is not called."""
    with patch("src.services.document_classifier.llm_generate", new_callable=AsyncMock) as mock_llm:
        category, confidence = await classify_document("חשבונית מס 12345", "invoice.pdf")
    mock_llm.assert_not_called()
    assert category == "invoice"
    assert confidence == 0.8


# ---------------------------------------------------------------------------
# Property P3: Classification Completeness
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("text,filename", [
    ("", "unknown.pdf"),
    ("random gibberish xyz", "doc.pdf"),
    ("", "spreadsheet.xlsx"),
    ("חשבונית", "invoice.pdf"),
])
async def test_p3_result_always_in_supported_categories(text, filename):
    """P3: For any input, classify_document returns exactly one value from SUPPORTED_CATEGORIES."""
    with patch("src.services.document_classifier.llm_generate", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = ""
        category, confidence = await classify_document(text, filename)
    assert category in SUPPORTED_CATEGORIES, f"Got unexpected category: {category}"
    assert 0.0 <= confidence <= 1.0
