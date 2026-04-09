"""Tests for document processor router — routing logic + fallback chain."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.document_processors.base_processor import ProcessorResult
from src.services.document_processors.processor_router import route_processor, process_with_best


# ── Routing logic tests ──────────────────────────────────────────────

class TestRouteProcessor:
    def test_salary_slip_prefers_google(self):
        order = route_processor("salary_slip", "payslip.pdf")
        assert order[0] == "google_docai"

    def test_invoice_prefers_google(self):
        order = route_processor("invoice", "invoice.pdf")
        assert order[0] == "google_docai"

    def test_receipt_prefers_google(self):
        order = route_processor("receipt", "receipt.jpg")
        assert order[0] == "google_docai"

    def test_bank_statement_prefers_google(self):
        order = route_processor("bank_statement", "statement.pdf")
        assert order[0] == "google_docai"

    def test_image_prefers_google(self):
        order = route_processor("other", "photo.jpg")
        assert order[0] == "google_docai"

    def test_digital_pdf_prefers_tesseract(self):
        order = route_processor("contract", "contract.pdf")
        assert order[0] == "tesseract"

    def test_payslip_filename_prefers_google(self):
        """Filename hint should route to Google even when doc_type is 'other'."""
        order = route_processor("other", "PaySlip2025-06.pdf.pdf")
        assert order[0] == "google_docai"

    def test_invoice_filename_prefers_google(self):
        order = route_processor("other", "חשבונית_מרץ.pdf")
        assert order[0] == "google_docai"

    def test_docx_prefers_tesseract(self):
        order = route_processor("other", "document.docx")
        assert order[0] == "tesseract"

    def test_all_routes_include_all_processors(self):
        """Every route should include all three processors as fallback."""
        for doc_type in ["salary_slip", "invoice", "other", "contract", "recipe"]:
            for ext in [".pdf", ".jpg", ".docx"]:
                order = route_processor(doc_type, f"file{ext}")
                assert set(order) == {"google_docai", "bedrock_vision", "tesseract"}


# ── process_with_best tests ──────────────────────────────────────────

def _make_result(name: str, text: str = "extracted text", confidence: float = 0.8) -> ProcessorResult:
    return ProcessorResult(
        raw_text=text,
        confidence=confidence,
        processor_name=name,
        extraction_method=name,
    )


def _make_empty_result(name: str) -> ProcessorResult:
    return ProcessorResult(processor_name=name, extraction_method="empty")


class TestProcessWithBest:
    @pytest.mark.asyncio
    async def test_accepts_first_good_result(self):
        """Should accept the first processor result above confidence threshold."""
        mock_google = MagicMock()
        mock_google.name = "google_docai"
        mock_google.is_available.return_value = True
        mock_google.process = AsyncMock(return_value=_make_result("google_docai", confidence=0.9))

        mock_tesseract = MagicMock()
        mock_tesseract.name = "tesseract"
        mock_tesseract.is_available.return_value = True
        mock_tesseract.process = AsyncMock(return_value=_make_result("tesseract", confidence=0.5))

        processors = {"google_docai": mock_google, "tesseract": mock_tesseract}

        with patch("src.services.document_processors.processor_router._get_processors", return_value=processors), \
             patch("src.services.document_processors.processor_router.route_processor",
                   return_value=["google_docai", "tesseract"]):
            result = await process_with_best("payslip.jpg", doc_type="salary_slip")

        assert result.processor_name == "google_docai"
        assert result.confidence == 0.9
        mock_tesseract.process.assert_not_called()

    @pytest.mark.asyncio
    async def test_falls_through_on_low_confidence(self):
        """Should try next processor when first returns low confidence."""
        mock_google = MagicMock()
        mock_google.name = "google_docai"
        mock_google.is_available.return_value = True
        mock_google.process = AsyncMock(return_value=_make_result("google_docai", confidence=0.2))

        mock_bedrock = MagicMock()
        mock_bedrock.name = "bedrock_vision"
        mock_bedrock.is_available.return_value = True
        mock_bedrock.process = AsyncMock(return_value=_make_result("bedrock_vision", confidence=0.7))

        processors = {"google_docai": mock_google, "bedrock_vision": mock_bedrock}

        with patch("src.services.document_processors.processor_router._get_processors", return_value=processors), \
             patch("src.services.document_processors.processor_router.route_processor",
                   return_value=["google_docai", "bedrock_vision"]):
            result = await process_with_best("doc.jpg")

        assert result.processor_name == "bedrock_vision"
        assert result.confidence == 0.7

    @pytest.mark.asyncio
    async def test_falls_through_on_empty_text(self):
        """Should skip processors that return no text."""
        mock_google = MagicMock()
        mock_google.name = "google_docai"
        mock_google.is_available.return_value = True
        mock_google.process = AsyncMock(return_value=_make_empty_result("google_docai"))

        mock_tesseract = MagicMock()
        mock_tesseract.name = "tesseract"
        mock_tesseract.is_available.return_value = True
        mock_tesseract.process = AsyncMock(return_value=_make_result("tesseract", confidence=0.6))

        processors = {"google_docai": mock_google, "tesseract": mock_tesseract}

        with patch("src.services.document_processors.processor_router._get_processors", return_value=processors), \
             patch("src.services.document_processors.processor_router.route_processor",
                   return_value=["google_docai", "tesseract"]):
            result = await process_with_best("doc.pdf")

        assert result.processor_name == "tesseract"

    @pytest.mark.asyncio
    async def test_handles_processor_exception(self):
        """Should continue to next processor if one throws."""
        mock_google = MagicMock()
        mock_google.name = "google_docai"
        mock_google.is_available.return_value = True
        mock_google.process = AsyncMock(side_effect=Exception("API down"))

        mock_tesseract = MagicMock()
        mock_tesseract.name = "tesseract"
        mock_tesseract.is_available.return_value = True
        mock_tesseract.process = AsyncMock(return_value=_make_result("tesseract", confidence=0.5))

        processors = {"google_docai": mock_google, "tesseract": mock_tesseract}

        with patch("src.services.document_processors.processor_router._get_processors", return_value=processors), \
             patch("src.services.document_processors.processor_router.route_processor",
                   return_value=["google_docai", "tesseract"]):
            result = await process_with_best("doc.jpg")

        assert result.processor_name == "tesseract"

    @pytest.mark.asyncio
    async def test_returns_best_effort_when_all_below_threshold(self):
        """When no processor meets threshold, return the highest confidence result."""
        mock_google = MagicMock()
        mock_google.name = "google_docai"
        mock_google.is_available.return_value = True
        mock_google.process = AsyncMock(return_value=_make_result("google_docai", confidence=0.3))

        mock_tesseract = MagicMock()
        mock_tesseract.name = "tesseract"
        mock_tesseract.is_available.return_value = True
        mock_tesseract.process = AsyncMock(return_value=_make_result("tesseract", confidence=0.2))

        processors = {"google_docai": mock_google, "tesseract": mock_tesseract}

        with patch("src.services.document_processors.processor_router._get_processors", return_value=processors), \
             patch("src.services.document_processors.processor_router.route_processor",
                   return_value=["google_docai", "tesseract"]):
            result = await process_with_best("doc.jpg")

        assert result.processor_name == "google_docai"
        assert result.confidence == 0.3

    @pytest.mark.asyncio
    async def test_no_processors_available(self):
        """Should return empty result when no processors are available."""
        with patch("src.services.document_processors.processor_router._get_processors", return_value={}):
            result = await process_with_best("doc.jpg")

        assert result.extraction_method == "no_processors"
