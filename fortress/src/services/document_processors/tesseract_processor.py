"""Tesseract OCR processor — local free fallback.

Wraps existing pytesseract + image_preprocessor logic as a processor backend.
Lowest priority — used when cloud processors are unavailable.
"""
from __future__ import annotations

import logging
import os

from src.services.document_processors.base_processor import BaseProcessor, ProcessorResult

logger = logging.getLogger(__name__)

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".heic"}


class TesseractProcessor(BaseProcessor):
    """Local Tesseract OCR — free, always available if installed."""

    name = "tesseract"

    def is_available(self) -> bool:
        try:
            import pytesseract  # noqa: F401
            return True
        except ImportError:
            return False

    async def process(self, file_path: str, mime_type: str = "") -> ProcessorResult:
        _, ext = os.path.splitext(file_path)
        ext = ext.lower()

        if ext == ".pdf":
            return await self._process_pdf(file_path)
        elif ext in _IMAGE_EXTENSIONS:
            return await self._process_image(file_path)
        else:
            return ProcessorResult(processor_name=self.name, extraction_method="unsupported")

    async def _process_image(self, file_path: str) -> ProcessorResult:
        try:
            import pytesseract
            from src.services.image_preprocessor import (
                compute_text_quality_score,
                preprocess_for_ocr,
            )
        except ImportError:
            return ProcessorResult(processor_name=self.name, extraction_method="error")

        try:
            preprocessed = preprocess_for_ocr(file_path)
            text = pytesseract.image_to_string(preprocessed, lang="heb+eng").strip()
            score = compute_text_quality_score(text)
        except Exception as exc:
            logger.error("tesseract: OCR failed %s: %s", os.path.basename(file_path), exc)
            return ProcessorResult(processor_name=self.name, extraction_method="error")

        logger.info("tesseract: extracted %d chars quality=%.2f from %s",
                     len(text), score, os.path.basename(file_path))

        return ProcessorResult(
            raw_text=text,
            confidence=score,
            processor_name=self.name,
            extraction_method="tesseract",
        )

    async def _process_pdf(self, file_path: str) -> ProcessorResult:
        try:
            import pdfplumber
        except ImportError:
            return ProcessorResult(processor_name=self.name, extraction_method="error")

        from src.services.image_preprocessor import compute_text_quality_score

        # Try digital PDF first
        pages_text: list[str] = []
        try:
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        pages_text.append(text)
        except Exception as exc:
            logger.error("tesseract: pdfplumber failed %s: %s", os.path.basename(file_path), exc)

        combined = "\n\n".join(pages_text)
        if combined.strip():
            score = compute_text_quality_score(combined)
            if score >= 0.5:
                return ProcessorResult(
                    raw_text=combined,
                    confidence=score,
                    processor_name=self.name,
                    extraction_method="pdfplumber",
                    page_count=len(pages_text),
                )

        # Scanned PDF — OCR fallback
        try:
            import pytesseract
            from pdf2image import convert_from_path
            from src.services.image_preprocessor import preprocess_for_ocr
            import tempfile

            images = convert_from_path(file_path, dpi=300, first_page=1, last_page=10)
            ocr_pages: list[str] = []
            for img in images:
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    img.save(tmp, format="PNG")
                    tmp_path = tmp.name
                try:
                    preprocessed = preprocess_for_ocr(tmp_path)
                    text = pytesseract.image_to_string(preprocessed, lang="heb+eng").strip()
                    if text:
                        ocr_pages.append(text)
                finally:
                    os.unlink(tmp_path)

            combined = "\n\n".join(ocr_pages)
            score = compute_text_quality_score(combined)
            return ProcessorResult(
                raw_text=combined,
                confidence=score,
                processor_name=self.name,
                extraction_method="tesseract_pdf_ocr",
                page_count=len(ocr_pages),
            )
        except Exception as exc:
            logger.error("tesseract: PDF OCR failed %s: %s", os.path.basename(file_path), exc)
            return ProcessorResult(processor_name=self.name, extraction_method="error")
