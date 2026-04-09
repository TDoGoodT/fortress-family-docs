"""Processor router — picks the best extraction backend per document type.

Strategy (AWS-first, Google where significantly better):
  1. salary_slip, invoice, receipt, bank_statement → Google Document AI (OCR + tables)
  2. Images with Hebrew text → Google Document AI (best Hebrew OCR)
  3. Digital PDFs → Tesseract/pdfplumber (free, fast, good enough)
  4. Fallback chain: Google DocAI → Bedrock Vision → Tesseract

The router tries the preferred processor first. If it fails or returns
low-confidence results, it falls through to the next option.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from src.services.document_processors.base_processor import BaseProcessor, ProcessorResult

logger = logging.getLogger(__name__)

# Document types where Google Document AI is significantly better
_GOOGLE_PREFERRED_DOC_TYPES = {
    "salary_slip",
    "invoice",
    "receipt",
    "bank_statement",
    "credit_card_statement",
    "electricity_bill",
    "contract",
    "insurance",
}

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".heic"}

# Filename patterns that hint at structured documents (checked case-insensitive)
_GOOGLE_PREFERRED_FILENAME_PATTERNS = [
    "payslip", "pay_slip", "salary", "תלוש",
    "invoice", "חשבונית",
    "receipt", "קבלה",
    "bank_statement", "דף_חשבון",
    "contract", "חוזה", "הסכם",
    "insurance", "ביטוח", "פוליסה", "policy",
]

# Minimum confidence to accept a result without trying next processor
_CONFIDENCE_THRESHOLD = 0.4


def _get_processors() -> dict[str, BaseProcessor]:
    """Lazy-init all available processors."""
    processors: dict[str, BaseProcessor] = {}

    from src.services.document_processors.google_docai_processor import GoogleDocAIProcessor
    from src.services.document_processors.bedrock_vision_processor import BedrockVisionProcessor
    from src.services.document_processors.tesseract_processor import TesseractProcessor

    for cls in [GoogleDocAIProcessor, BedrockVisionProcessor, TesseractProcessor]:
        p = cls()
        if p.is_available():
            processors[p.name] = p
        else:
            logger.debug("processor_router: %s not available", p.name)

    return processors


def route_processor(
    doc_type: str,
    file_path: str,
) -> list[str]:
    """Return ordered list of processor names to try for this document.

    Priority logic:
      - Structured docs (salary_slip, invoice, etc.) → google_docai first
      - Filename hints (PaySlip, invoice, etc.) → google_docai first
      - Hebrew images → google_docai first
      - Digital PDFs → tesseract first (free + fast)
      - Everything else → tesseract → bedrock_vision → google_docai
    """
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()
    is_image = ext in _IMAGE_EXTENSIONS
    filename_lower = os.path.basename(file_path).lower()

    if doc_type in _GOOGLE_PREFERRED_DOC_TYPES:
        return ["google_docai", "bedrock_vision", "tesseract"]

    # Filename hints — catch salary slips etc. before classification runs
    if any(pattern in filename_lower for pattern in _GOOGLE_PREFERRED_FILENAME_PATTERNS):
        return ["google_docai", "bedrock_vision", "tesseract"]

    if is_image:
        return ["google_docai", "bedrock_vision", "tesseract"]

    if ext == ".pdf":
        # Digital PDFs — try Google first for better Hebrew, fall back to tesseract
        return ["google_docai", "tesseract", "bedrock_vision"]

    return ["tesseract", "bedrock_vision", "google_docai"]


async def process_with_best(
    file_path: str,
    doc_type: str = "other",
    min_confidence: float = _CONFIDENCE_THRESHOLD,
    pdf_passwords: list[str] | None = None,
) -> ProcessorResult:
    """Process document with the best available processor.

    Tries processors in priority order. Accepts the first result that
    meets the confidence threshold, or returns the best result seen.

    If the PDF is encrypted and pdf_passwords are provided, attempts
    decryption before processing.
    """
    _, ext = os.path.splitext(file_path)
    actual_file_path = file_path
    decrypted_tmp_path: str | None = None

    # Handle encrypted PDFs
    if ext.lower() == ".pdf" and pdf_passwords:
        from src.services.document_processors.pdf_decryptor import is_pdf_encrypted, try_decrypt_pdf
        if is_pdf_encrypted(file_path):
            decrypted_bytes, used_password = try_decrypt_pdf(file_path, pdf_passwords)
            if decrypted_bytes is not None:
                import tempfile
                tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
                tmp.write(decrypted_bytes)
                tmp.close()
                decrypted_tmp_path = tmp.name
                actual_file_path = decrypted_tmp_path
                logger.info(
                    "processor_router: decrypted %s, processing decrypted copy",
                    os.path.basename(file_path),
                )
            else:
                logger.warning(
                    "processor_router: PDF %s is encrypted and all passwords failed",
                    os.path.basename(file_path),
                )

    try:
        result = await _process_file(actual_file_path, file_path, doc_type, min_confidence)
    finally:
        # Clean up temp decrypted file
        if decrypted_tmp_path and os.path.exists(decrypted_tmp_path):
            os.unlink(decrypted_tmp_path)

    return result


async def _process_file(
    actual_file_path: str,
    original_file_path: str,
    doc_type: str,
    min_confidence: float,
) -> ProcessorResult:
    """Internal: process a file (possibly decrypted) with the best processor."""
    processors = _get_processors()
    if not processors:
        logger.error("processor_router: no processors available")
        return ProcessorResult(processor_name="none", extraction_method="no_processors")

    priority = route_processor(doc_type, actual_file_path)
    available_priority = [name for name in priority if name in processors]

    if not available_priority:
        logger.warning("processor_router: no available processors for doc_type=%s file=%s",
                        doc_type, os.path.basename(original_file_path))
        return ProcessorResult(processor_name="none", extraction_method="no_available_processors")

    best_result: ProcessorResult | None = None

    for proc_name in available_priority:
        proc = processors[proc_name]
        logger.info("processor_router: trying %s for %s (doc_type=%s)",
                     proc_name, os.path.basename(original_file_path), doc_type)
        try:
            result = await proc.process(actual_file_path)
        except Exception as exc:
            logger.warning("processor_router: %s failed for %s: %s: %s",
                           proc_name, os.path.basename(original_file_path), type(exc).__name__, exc)
            continue

        if not result.has_text:
            logger.info("processor_router: %s returned no text for %s",
                         proc_name, os.path.basename(original_file_path))
            continue

        # Track best result seen
        if best_result is None or result.confidence > best_result.confidence:
            best_result = result

        # Accept if confidence is good enough
        if result.confidence >= min_confidence:
            logger.info("processor_router: accepted %s confidence=%.2f for %s",
                         proc_name, result.confidence, os.path.basename(original_file_path))
            return result

        logger.info("processor_router: %s confidence=%.2f below threshold=%.2f, trying next",
                     proc_name, result.confidence, min_confidence)

    if best_result:
        logger.info("processor_router: returning best-effort %s confidence=%.2f for %s",
                     best_result.processor_name, best_result.confidence,
                     os.path.basename(original_file_path))
        return best_result

    return ProcessorResult(processor_name="fallthrough", extraction_method="all_failed")
