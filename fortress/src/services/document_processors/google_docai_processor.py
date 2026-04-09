"""Google Document AI processor — high-accuracy OCR + structured extraction.

Google Document AI is significantly stronger than Tesseract/Bedrock vision
for Hebrew documents, tables, and structured forms (salary slips, invoices).

Requires:
  pip install google-cloud-documentai pypdf
  Environment vars: GOOGLE_DOCAI_PROJECT_ID, GOOGLE_DOCAI_LOCATION, GOOGLE_DOCAI_PROCESSOR_ID
  Auth: GOOGLE_APPLICATION_CREDENTIALS pointing to a service account JSON key.
"""
from __future__ import annotations

import io
import logging
import mimetypes
import os
from typing import Any

from src.services.document_processors.base_processor import BaseProcessor, ProcessorResult

logger = logging.getLogger(__name__)

# Google DocAI synchronous API page limit (online processing)
_MAX_PAGES_PER_REQUEST = 15

_MIME_MAP: dict[str, str] = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".bmp": "image/x-ms-bmp",
    ".heic": "image/jpeg",  # convert before sending
}


def _detect_mime(file_path: str, hint: str = "") -> str:
    if hint:
        return hint
    _, ext = os.path.splitext(file_path)
    return _MIME_MAP.get(ext.lower(), mimetypes.guess_type(file_path)[0] or "application/pdf")


def _convert_heic_to_jpeg(file_path: str) -> bytes:
    """Convert HEIC to JPEG bytes for Document AI (doesn't support HEIC natively)."""
    from PIL import Image
    import io

    img = Image.open(file_path)
    buf = io.BytesIO()
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _extract_tables_from_document(document: Any) -> list[list[list[str]]]:
    """Extract tables from Document AI response as list of tables.

    Each table is a list of rows, each row is a list of cell text values.
    """
    tables: list[list[list[str]]] = []
    for page in document.pages:
        for table in page.tables:
            rows: list[list[str]] = []
            # Header rows
            for header_row in table.header_rows:
                row_cells = []
                for cell in header_row.cells:
                    cell_text = _layout_text(cell.layout, document.text)
                    row_cells.append(cell_text)
                rows.append(row_cells)
            # Body rows
            for body_row in table.body_rows:
                row_cells = []
                for cell in body_row.cells:
                    cell_text = _layout_text(cell.layout, document.text)
                    row_cells.append(cell_text)
                rows.append(row_cells)
            if rows:
                tables.append(rows)
    return tables


def _layout_text(layout: Any, full_text: str) -> str:
    """Extract text from a layout element using text anchors."""
    if not layout.text_anchor or not layout.text_anchor.text_segments:
        return ""
    parts = []
    for segment in layout.text_anchor.text_segments:
        start = int(segment.start_index) if segment.start_index else 0
        end = int(segment.end_index)
        parts.append(full_text[start:end])
    return "".join(parts).strip()


def _count_pdf_pages(pdf_bytes: bytes) -> int:
    """Count pages in a PDF without fully parsing it."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_bytes))
        return len(reader.pages)
    except Exception:
        return 0


def _split_pdf(pdf_bytes: bytes, max_pages: int) -> list[bytes]:
    """Split a PDF into chunks of max_pages, returning each as bytes."""
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        logger.error("google_docai: pypdf not installed, cannot split PDF")
        return [pdf_bytes]

    reader = PdfReader(io.BytesIO(pdf_bytes))
    total = len(reader.pages)
    if total <= max_pages:
        return [pdf_bytes]

    batches: list[bytes] = []
    for start in range(0, total, max_pages):
        writer = PdfWriter()
        for page_idx in range(start, min(start + max_pages, total)):
            writer.add_page(reader.pages[page_idx])
        buf = io.BytesIO()
        writer.write(buf)
        batches.append(buf.getvalue())

    return batches


class GoogleDocAIProcessor(BaseProcessor):
    """Google Document AI — best-in-class for Hebrew OCR and structured documents."""

    name = "google_docai"

    def __init__(self) -> None:
        self._project_id = os.getenv("GOOGLE_DOCAI_PROJECT_ID", "")
        self._location = os.getenv("GOOGLE_DOCAI_LOCATION", "us")
        self._processor_id = os.getenv("GOOGLE_DOCAI_PROCESSOR_ID", "")
        # Optional: separate processor for forms/invoices
        self._form_processor_id = os.getenv("GOOGLE_DOCAI_FORM_PROCESSOR_ID", "")

    def is_available(self) -> bool:
        if not (self._project_id and self._processor_id):
            return False
        try:
            from google.cloud import documentai  # noqa: F401
            return True
        except ImportError:
            logger.debug("google_docai: google-cloud-documentai not installed")
            return False

    async def process(self, file_path: str, mime_type: str = "") -> ProcessorResult:
        return await self._process_with_processor(file_path, mime_type, self._processor_id)

    async def process_form(self, file_path: str, mime_type: str = "") -> ProcessorResult:
        """Process with form/invoice processor if configured, else fall back to default."""
        pid = self._form_processor_id or self._processor_id
        return await self._process_with_processor(file_path, mime_type, pid)

    async def _process_with_processor(
        self, file_path: str, mime_type: str, processor_id: str
    ) -> ProcessorResult:
        try:
            from google.cloud import documentai
            from google.api_core.client_options import ClientOptions
        except ImportError:
            logger.error("google_docai: google-cloud-documentai not installed")
            return ProcessorResult(processor_name=self.name, extraction_method="error")

        resolved_mime = _detect_mime(file_path, mime_type)

        # Read file content
        _, ext = os.path.splitext(file_path)
        if ext.lower() == ".heic":
            file_content = _convert_heic_to_jpeg(file_path)
            resolved_mime = "image/jpeg"
        else:
            with open(file_path, "rb") as f:
                file_content = f.read()

        # Check if PDF needs splitting (page count > limit)
        pdf_page_count = 0
        if resolved_mime == "application/pdf":
            pdf_page_count = _count_pdf_pages(file_content)
            if pdf_page_count > _MAX_PAGES_PER_REQUEST:
                logger.info(
                    "google_docai: PDF has %d pages (limit=%d), splitting into batches for %s",
                    pdf_page_count, _MAX_PAGES_PER_REQUEST, os.path.basename(file_path),
                )
                return await self._process_pdf_in_batches(
                    file_content, file_path, processor_id, pdf_page_count,
                )

        # Build client
        opts = ClientOptions(api_endpoint=f"{self._location}-documentai.googleapis.com")
        client = documentai.DocumentProcessorServiceClient(client_options=opts)

        resource_name = client.processor_path(self._project_id, self._location, processor_id)

        raw_document = documentai.RawDocument(content=file_content, mime_type=resolved_mime)
        request = documentai.ProcessRequest(name=resource_name, raw_document=raw_document)

        try:
            response = client.process_document(request=request)
        except Exception as exc:
            logger.error("google_docai: API call failed: %s: %s", type(exc).__name__, exc)
            return ProcessorResult(processor_name=self.name, extraction_method="error")

        return self._build_result(response.document, file_path, processor_id)

    async def _process_pdf_in_batches(
        self,
        file_content: bytes,
        file_path: str,
        processor_id: str,
        total_pages: int,
    ) -> ProcessorResult:
        """Split a large PDF into batches and process each with Google DocAI."""
        try:
            from google.cloud import documentai
            from google.api_core.client_options import ClientOptions
        except ImportError:
            return ProcessorResult(processor_name=self.name, extraction_method="error")

        batches = _split_pdf(file_content, _MAX_PAGES_PER_REQUEST)
        logger.info(
            "google_docai: split %s into %d batches (%d pages total)",
            os.path.basename(file_path), len(batches), total_pages,
        )

        opts = ClientOptions(api_endpoint=f"{self._location}-documentai.googleapis.com")
        client = documentai.DocumentProcessorServiceClient(client_options=opts)
        resource_name = client.processor_path(self._project_id, self._location, processor_id)

        all_text_parts: list[str] = []
        all_tables: list[list[list[str]]] = []
        all_structured: dict[str, Any] = {}
        all_page_confidences: list[float] = []
        total_page_count = 0
        lang = ""

        for batch_idx, batch_bytes in enumerate(batches):
            try:
                raw_document = documentai.RawDocument(
                    content=batch_bytes, mime_type="application/pdf",
                )
                request = documentai.ProcessRequest(
                    name=resource_name, raw_document=raw_document,
                )
                response = client.process_document(request=request)
                document = response.document

                if document.text:
                    all_text_parts.append(document.text)
                all_tables.extend(_extract_tables_from_document(document))
                for entity in document.entities:
                    key = entity.type_ or ""
                    value = entity.mention_text or ""
                    if key and value and key not in all_structured:
                        all_structured[key] = value
                for page in document.pages:
                    if page.layout and page.layout.confidence:
                        all_page_confidences.append(page.layout.confidence)
                total_page_count += len(document.pages)
                if not lang and document.pages:
                    detected = document.pages[0].detected_languages
                    if detected:
                        lang = detected[0].language_code or ""

                logger.info(
                    "google_docai: batch %d/%d done, pages=%d chars=%d",
                    batch_idx + 1, len(batches),
                    len(document.pages), len(document.text or ""),
                )
            except Exception as exc:
                logger.error(
                    "google_docai: batch %d/%d failed: %s: %s",
                    batch_idx + 1, len(batches), type(exc).__name__, exc,
                )
                continue

        if not all_text_parts:
            logger.error("google_docai: all batches failed for %s", os.path.basename(file_path))
            return ProcessorResult(processor_name=self.name, extraction_method="error")

        raw_text = "\n\n".join(all_text_parts)
        avg_confidence = (
            sum(all_page_confidences) / len(all_page_confidences)
            if all_page_confidences else 0.0
        )

        logger.info(
            "google_docai: batched processing complete %s chars=%d tables=%d "
            "entities=%d confidence=%.2f pages=%d lang=%s",
            os.path.basename(file_path), len(raw_text), len(all_tables),
            len(all_structured), avg_confidence, total_page_count, lang,
        )

        return ProcessorResult(
            raw_text=raw_text,
            structured_data=all_structured,
            tables=all_tables,
            confidence=avg_confidence,
            processor_name=self.name,
            extraction_method="google_docai",
            page_count=total_page_count,
            language_detected=lang,
            metadata={
                "processor_id": processor_id,
                "entity_count": len(all_structured),
                "batch_count": len(batches),
                "batch_mode": True,
            },
        )

    def _build_result(self, document: Any, file_path: str, processor_id: str) -> ProcessorResult:
        """Build ProcessorResult from a single Document AI response."""
        raw_text = document.text or ""
        tables = _extract_tables_from_document(document)

        lang = ""
        if document.pages:
            detected = document.pages[0].detected_languages
            if detected:
                lang = detected[0].language_code or ""

        structured: dict[str, Any] = {}
        for entity in document.entities:
            key = entity.type_ or ""
            value = entity.mention_text or ""
            if key and value:
                structured[key] = value

        page_confidences = []
        for page in document.pages:
            if page.layout and page.layout.confidence:
                page_confidences.append(page.layout.confidence)
        avg_confidence = sum(page_confidences) / len(page_confidences) if page_confidences else 0.0

        logger.info(
            "google_docai: processed %s chars=%d tables=%d entities=%d confidence=%.2f lang=%s",
            os.path.basename(file_path), len(raw_text), len(tables),
            len(structured), avg_confidence, lang,
        )

        return ProcessorResult(
            raw_text=raw_text,
            structured_data=structured,
            tables=tables,
            confidence=avg_confidence,
            processor_name=self.name,
            extraction_method="google_docai",
            page_count=len(document.pages),
            language_detected=lang,
            metadata={
                "processor_id": processor_id,
                "entity_count": len(document.entities),
            },
        )
