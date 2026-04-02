"""Unit tests for document_summarizer."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from src.services.document_summarizer import summarize_document


@pytest.mark.asyncio
async def test_returns_summary_from_llm():
    expected = "זוהי חשבונית מס עבור שירותי תקשורת לחודש מרץ 2026."
    with patch("src.services.document_summarizer.llm_generate", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = expected
        result = await summarize_document("חשבונית מס 12345 סכום 500 ש\"ח", "invoice", "invoice.pdf")
    assert result == expected
    mock_llm.assert_called_once()


@pytest.mark.asyncio
async def test_empty_raw_text_returns_empty():
    with patch("src.services.document_summarizer.llm_generate", new_callable=AsyncMock) as mock_llm:
        result = await summarize_document("", "invoice", "invoice.pdf")
    mock_llm.assert_not_called()
    assert result == ""


@pytest.mark.asyncio
async def test_whitespace_only_raw_text_returns_empty():
    with patch("src.services.document_summarizer.llm_generate", new_callable=AsyncMock) as mock_llm:
        result = await summarize_document("   \n  ", "invoice", "invoice.pdf")
    mock_llm.assert_not_called()
    assert result == ""


@pytest.mark.asyncio
async def test_llm_failure_returns_empty():
    with patch("src.services.document_summarizer.llm_generate", new_callable=AsyncMock) as mock_llm:
        mock_llm.side_effect = Exception("LLM unavailable")
        result = await summarize_document("some document text", "invoice", "invoice.pdf")
    assert result == ""


@pytest.mark.asyncio
async def test_llm_empty_response_returns_empty():
    with patch("src.services.document_summarizer.llm_generate", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = ""
        result = await summarize_document("some document text", "invoice", "invoice.pdf")
    assert result == ""


@pytest.mark.asyncio
async def test_uses_lite_model_tier():
    """Summarizer should use the lite model tier."""
    with patch("src.services.document_summarizer.llm_generate", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = "סיכום קצר."
        await summarize_document("document text", "contract", "contract.pdf")
    call_args = mock_llm.call_args
    assert call_args[0][2] == "lite"  # third positional arg is model_tier
