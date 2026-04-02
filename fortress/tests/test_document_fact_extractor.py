"""Unit tests for document_fact_extractor — regex, LLM, P4 property."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from src.services.document_classifier import ALLOWED_FACT_KEYS, MAX_SOURCE_EXCERPT_LENGTH
from src.services.document_fact_extractor import extract_facts, _extract_dates_regex, _extract_amounts_regex


# ---------------------------------------------------------------------------
# Phase 1: regex extraction
# ---------------------------------------------------------------------------

def test_regex_date_extraction():
    text = "תאריך חשבונית: 15/03/2026 סכום לתשלום"
    facts = _extract_dates_regex(text)
    assert len(facts) == 1
    assert facts[0]["fact_key"] == "source_date"
    assert "2026" in facts[0]["fact_value"]
    assert facts[0]["confidence"] > 0.0


def test_regex_date_iso_format():
    text = "Invoice date: 2026-03-15"
    facts = _extract_dates_regex(text)
    assert len(facts) == 1
    assert facts[0]["fact_value"] == "2026-03-15"


def test_regex_amount_ils():
    text = "סה\"כ לתשלום: ₪ 428.50"
    facts = _extract_amounts_regex(text)
    keys = {f["fact_key"] for f in facts}
    assert "amount" in keys
    assert "currency" in keys
    amount_fact = next(f for f in facts if f["fact_key"] == "amount")
    assert amount_fact["fact_value"] == "428.50"
    currency_fact = next(f for f in facts if f["fact_key"] == "currency")
    assert currency_fact["fact_value"] == "ILS"


def test_regex_amount_usd():
    text = "Total: $1,200.00"
    facts = _extract_amounts_regex(text)
    currency_fact = next((f for f in facts if f["fact_key"] == "currency"), None)
    assert currency_fact is not None
    assert currency_fact["fact_value"] == "USD"


def test_regex_no_date_returns_empty():
    facts = _extract_dates_regex("no date here at all")
    assert facts == []


def test_regex_no_amount_returns_empty():
    facts = _extract_amounts_regex("no amount here")
    assert facts == []


# ---------------------------------------------------------------------------
# fact_type is set to doc_type
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fact_type_equals_doc_type():
    text = "חשבונית מס 12345 תאריך: 01/01/2026 סכום: ₪500"
    with patch("src.services.document_fact_extractor.llm_generate", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = ""
        facts = await extract_facts(text, "invoice", "invoice.pdf")
    for fact in facts:
        assert fact["fact_type"] == "invoice"


# ---------------------------------------------------------------------------
# source_excerpt truncation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_source_excerpt_truncated():
    long_text = "A" * 1000 + " ₪500 " + "B" * 1000
    with patch("src.services.document_fact_extractor.llm_generate", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = ""
        facts = await extract_facts(long_text, "invoice", "doc.pdf")
    for fact in facts:
        assert len(fact.get("source_excerpt", "")) <= MAX_SOURCE_EXCERPT_LENGTH


# ---------------------------------------------------------------------------
# LLM Phase 2
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_llm_extraction_called_for_remaining_keys():
    text = "Counterparty: Super-Pharm Ltd. Policy: POL-12345"
    llm_response = '[{"fact_key": "counterparty", "fact_value": "Super-Pharm Ltd.", "confidence": 0.9, "source_excerpt": "Counterparty: Super-Pharm Ltd."}]'
    with patch("src.services.document_fact_extractor.llm_generate", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = llm_response
        facts = await extract_facts(text, "invoice", "doc.pdf")
    keys = {f["fact_key"] for f in facts}
    assert "counterparty" in keys


@pytest.mark.asyncio
async def test_unrecognized_fact_keys_discarded():
    text = "some document text"
    llm_response = '[{"fact_key": "unknown_key", "fact_value": "something", "confidence": 0.9, "source_excerpt": "text"}]'
    with patch("src.services.document_fact_extractor.llm_generate", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = llm_response
        facts = await extract_facts(text, "invoice", "doc.pdf")
    keys = {f["fact_key"] for f in facts}
    assert "unknown_key" not in keys


@pytest.mark.asyncio
async def test_llm_failure_returns_partial_results():
    """If LLM fails, regex-extracted facts are still returned."""
    text = "תאריך: 15/03/2026 סכום: ₪500"
    with patch("src.services.document_fact_extractor.llm_generate", new_callable=AsyncMock) as mock_llm:
        mock_llm.side_effect = Exception("LLM error")
        facts = await extract_facts(text, "invoice", "doc.pdf")
    # Regex facts should still be present
    keys = {f["fact_key"] for f in facts}
    assert "source_date" in keys or "amount" in keys


@pytest.mark.asyncio
async def test_empty_raw_text_returns_empty():
    facts = await extract_facts("", "invoice", "doc.pdf")
    assert facts == []


# ---------------------------------------------------------------------------
# Property P4: Fact Consistency
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_p4_fact_keys_in_allowed_set():
    """P4: All extracted fact_keys must be in ALLOWED_FACT_KEYS."""
    text = "חשבונית מס 12345 תאריך: 01/01/2026 סכום: ₪500 לקוח: Super-Pharm"
    llm_response = '[{"fact_key": "counterparty", "fact_value": "Super-Pharm", "confidence": 0.9, "source_excerpt": "לקוח: Super-Pharm"}]'
    with patch("src.services.document_fact_extractor.llm_generate", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = llm_response
        facts = await extract_facts(text, "invoice", "invoice.pdf")
    for fact in facts:
        assert fact["fact_key"] in ALLOWED_FACT_KEYS, f"Unexpected key: {fact['fact_key']}"
        assert 0.0 <= fact["confidence"] <= 1.0
        assert fact["fact_type"] == "invoice"
