"""Tests for Google Document AI processor — unit tests with mocked API."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, mock_open

from src.services.document_processors.google_docai_processor import (
    GoogleDocAIProcessor,
    _extract_tables_from_document,
    _layout_text,
)


class TestGoogleDocAIAvailability:
    def test_not_available_without_config(self):
        with patch.dict("os.environ", {}, clear=True):
            proc = GoogleDocAIProcessor()
            assert not proc.is_available()

    def test_not_available_without_library(self):
        with patch.dict("os.environ", {
            "GOOGLE_DOCAI_PROJECT_ID": "test-project",
            "GOOGLE_DOCAI_PROCESSOR_ID": "abc123",
        }):
            proc = GoogleDocAIProcessor()
            with patch.dict("sys.modules", {"google.cloud.documentai": None}):
                # ImportError when trying to import
                import importlib
                with patch("builtins.__import__", side_effect=ImportError("no module")):
                    assert not proc.is_available()

    def test_available_with_config_and_library(self):
        with patch.dict("os.environ", {
            "GOOGLE_DOCAI_PROJECT_ID": "test-project",
            "GOOGLE_DOCAI_PROCESSOR_ID": "abc123",
        }):
            proc = GoogleDocAIProcessor()
            with patch("builtins.__import__", wraps=__builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__):
                # Just check the config part
                assert proc._project_id == "test-project"
                assert proc._processor_id == "abc123"


class TestExtractTables:
    def test_empty_document(self):
        doc = MagicMock()
        doc.pages = []
        assert _extract_tables_from_document(doc) == []

    def test_single_table(self):
        """Test extraction of a simple 2x2 table."""
        doc = MagicMock()
        doc.text = "Header1Header2Value1Value2"

        # Build mock table structure
        def make_cell(start: int, end: int):
            cell = MagicMock()
            segment = MagicMock()
            segment.start_index = start
            segment.end_index = end
            cell.layout.text_anchor.text_segments = [segment]
            return cell

        header_row = MagicMock()
        header_row.cells = [make_cell(0, 7), make_cell(7, 14)]

        body_row = MagicMock()
        body_row.cells = [make_cell(14, 20), make_cell(20, 26)]

        table = MagicMock()
        table.header_rows = [header_row]
        table.body_rows = [body_row]

        page = MagicMock()
        page.tables = [table]
        doc.pages = [page]

        tables = _extract_tables_from_document(doc)
        assert len(tables) == 1
        assert len(tables[0]) == 2  # header + body row
        assert tables[0][0] == ["Header1", "Header2"]
        assert tables[0][1] == ["Value1", "Value2"]


class TestLayoutText:
    def test_empty_layout(self):
        layout = MagicMock()
        layout.text_anchor = None
        assert _layout_text(layout, "some text") == ""

    def test_no_segments(self):
        layout = MagicMock()
        layout.text_anchor.text_segments = []
        assert _layout_text(layout, "some text") == ""

    def test_single_segment(self):
        layout = MagicMock()
        segment = MagicMock()
        segment.start_index = 6
        segment.end_index = 11
        layout.text_anchor.text_segments = [segment]
        assert _layout_text(layout, "Hello World") == "World"


class TestProcessDocument:
    @pytest.mark.asyncio
    async def test_process_returns_result_on_success(self):
        """Mock the full Google Document AI call and verify result structure."""
        proc = GoogleDocAIProcessor()
        proc._project_id = "test-project"
        proc._location = "us"
        proc._processor_id = "proc-123"

        # Mock document response
        mock_doc = MagicMock()
        mock_doc.text = "תלוש שכר לחודש מרץ 2026\nשכר ברוטו: 15,000 ₪"
        mock_page = MagicMock()
        mock_page.tables = []
        mock_page.detected_languages = [MagicMock(language_code="he")]
        mock_page.layout.confidence = 0.95
        mock_doc.pages = [mock_page]
        mock_doc.entities = []

        mock_response = MagicMock()
        mock_response.document = mock_doc

        mock_client = MagicMock()
        mock_client.processor_path.return_value = "projects/test/locations/us/processors/proc-123"
        mock_client.process_document.return_value = mock_response

        # Build a mock documentai module
        mock_dai = MagicMock()
        mock_dai.DocumentProcessorServiceClient.return_value = mock_client
        mock_dai.RawDocument.return_value = MagicMock()
        mock_dai.ProcessRequest.return_value = MagicMock()

        mock_google_cloud = MagicMock()
        mock_google_cloud.documentai = mock_dai

        import sys
        with patch.dict(sys.modules, {
            "google": MagicMock(),
            "google.cloud": mock_google_cloud,
            "google.cloud.documentai": mock_dai,
            "google.api_core": MagicMock(),
            "google.api_core.client_options": MagicMock(),
        }), patch("builtins.open", mock_open(read_data=b"fake pdf content")):
            # Force re-import inside the method
            result = await proc._process_with_processor("test.pdf", "", "proc-123")

        assert result.has_text
        assert "תלוש שכר" in result.raw_text
        assert result.processor_name == "google_docai"
        assert result.confidence == 0.95
        assert result.language_detected == "he"
        assert result.page_count == 1

    @pytest.mark.asyncio
    async def test_process_handles_api_error(self):
        """Should return error result on API failure, not raise."""
        proc = GoogleDocAIProcessor()
        proc._project_id = "test-project"
        proc._location = "us"
        proc._processor_id = "proc-123"

        mock_client = MagicMock()
        mock_client.processor_path.return_value = "projects/test/locations/us/processors/proc-123"
        mock_client.process_document.side_effect = Exception("API quota exceeded")

        mock_dai = MagicMock()
        mock_dai.DocumentProcessorServiceClient.return_value = mock_client
        mock_dai.RawDocument.return_value = MagicMock()
        mock_dai.ProcessRequest.return_value = MagicMock()

        mock_google_cloud = MagicMock()
        mock_google_cloud.documentai = mock_dai

        import sys
        with patch.dict(sys.modules, {
            "google": MagicMock(),
            "google.cloud": mock_google_cloud,
            "google.cloud.documentai": mock_dai,
            "google.api_core": MagicMock(),
            "google.api_core.client_options": MagicMock(),
        }), patch("builtins.open", mock_open(read_data=b"fake pdf")):
            result = await proc._process_with_processor("test.pdf", "", "proc-123")

        assert result.extraction_method == "error"
        assert not result.has_text
