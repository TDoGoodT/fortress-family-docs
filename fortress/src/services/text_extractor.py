"""Fortress Text Extractor — extract raw text from documents.

Supports PDF (pdfplumber), Word (python-docx), and images (pytesseract OCR).
Each extractor is optional — gracefully returns empty string if the
dependency is not installed.
"""

import logging
import os

logger = logging.getLogger(__name__)


def extract_text(file_path: str) -> str:
    """Extract text from a file based on its extension.

    Returns the extracted text, or an empty string if extraction fails
    or the file type is unsupported.
    """
    if not os.path.isfile(file_path):
        logger.warning("text_extractor: file not found: %s", file_path)
        return ""

    _, ext = os.path.splitext(file_path)
    ext = ext.lower()

    try:
        if ext == ".pdf":
            return _extract_pdf(file_path)
        if ext in (".doc", ".docx"):
            return _extract_docx(file_path)
        if ext in (".jpg", ".jpeg", ".png", ".heic", ".tiff", ".bmp"):
            return _extract_image(file_path)
    except Exception:
        logger.exception("text_extractor: failed for %s", file_path)

    return ""


def _extract_pdf(file_path: str) -> str:
    """Extract text from a PDF using pdfplumber."""
    try:
        import pdfplumber
    except ImportError:
        logger.info("text_extractor: pdfplumber not installed, skipping PDF extraction")
        return ""

    pages_text: list[str] = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages_text.append(text)

    result = "\n\n".join(pages_text)
    logger.info("text_extractor: extracted %d chars from PDF %s", len(result), os.path.basename(file_path))
    return result


def _extract_docx(file_path: str) -> str:
    """Extract text from a Word document using python-docx."""
    try:
        import docx
    except ImportError:
        logger.info("text_extractor: python-docx not installed, skipping DOCX extraction")
        return ""

    doc = docx.Document(file_path)
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    result = "\n".join(paragraphs)
    logger.info("text_extractor: extracted %d chars from DOCX %s", len(result), os.path.basename(file_path))
    return result


def _extract_image(file_path: str) -> str:
    """Extract text from an image using pytesseract OCR.

    Requires Tesseract to be installed on the system.
    Falls back to empty string if pytesseract is not available.
    """
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        logger.info("text_extractor: pytesseract/Pillow not installed, skipping OCR")
        return ""

    try:
        image = Image.open(file_path)
        # Use Hebrew + English for OCR
        result = pytesseract.image_to_string(image, lang="heb+eng")
        result = result.strip()
        logger.info("text_extractor: OCR extracted %d chars from %s", len(result), os.path.basename(file_path))
        return result
    except pytesseract.TesseractNotFoundError:
        logger.warning("text_extractor: Tesseract not installed, skipping OCR")
        return ""
