from __future__ import annotations
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
    """Extract text from a PDF using pdfplumber, with OCR fallback for scanned PDFs."""
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

    # If pdfplumber found no text, this is likely a scanned PDF — try OCR
    if not result.strip():
        logger.info("text_extractor: pdfplumber returned empty for %s, trying OCR fallback", os.path.basename(file_path))
        result = _ocr_pdf(file_path)

    logger.info("text_extractor: extracted %d chars from PDF %s", len(result), os.path.basename(file_path))
    return result


def _ocr_pdf(file_path: str) -> str:
    """OCR a scanned PDF by converting pages to images and running pytesseract."""
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError:
        logger.info("text_extractor: pdf2image/pytesseract not installed, skipping PDF OCR")
        return ""

    try:
        images = convert_from_path(file_path, dpi=300, first_page=1, last_page=10)
        pages_text: list[str] = []
        for i, img in enumerate(images):
            text = pytesseract.image_to_string(img, lang="heb+eng")
            if text and text.strip():
                pages_text.append(text.strip())
        result = "\n\n".join(pages_text)
        logger.info("text_extractor: OCR extracted %d chars from %d pages of %s",
                     len(result), len(images), os.path.basename(file_path))
        return result
    except pytesseract.TesseractNotFoundError:
        logger.warning("text_extractor: Tesseract not installed, skipping PDF OCR")
        return ""
    except Exception:
        logger.exception("text_extractor: PDF OCR failed for %s", os.path.basename(file_path))
        return ""


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


# ── Image extensions for v2 extractor ────────────────────────────────
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".tiff", ".bmp"}


def _detect_extension_by_mime(file_path: str) -> str:
    """Detect file extension using MIME type when the file has no extension.

    Returns the detected extension (e.g. ".jpg") or "" if unknown.
    """
    import mimetypes
    try:
        import magic  # python-magic if available
        mime = magic.from_file(file_path, mime=True)
    except (ImportError, Exception):
        # Fallback: read magic bytes manually
        mime = _detect_mime_from_bytes(file_path)

    ext_map = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/bmp": ".bmp",
        "image/tiff": ".tiff",
        "image/heic": ".heic",
        "image/heif": ".heic",
        "application/pdf": ".pdf",
    }
    return ext_map.get(mime, "")


def _detect_mime_from_bytes(file_path: str) -> str:
    """Detect MIME type from file magic bytes."""
    try:
        with open(file_path, "rb") as f:
            header = f.read(16)
        if not header:
            return ""
        if header[:3] == b"\xff\xd8\xff":
            return "image/jpeg"
        if header[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png"
        if header[:4] == b"%PDF":
            return "application/pdf"
        if header[:2] == b"BM":
            return "image/bmp"
        if header[:4] in (b"II\x2a\x00", b"MM\x00\x2a"):
            return "image/tiff"
        # HEIC/HEIF: ftyp box
        if len(header) >= 12 and header[4:8] == b"ftyp":
            return "image/heic"
    except Exception:
        pass
    return ""


async def extract_text_v2(file_path: str) -> tuple[str, float, str]:
    """Extract text with preprocessing, quality scoring, and vision fallback.

    Returns: (raw_text, quality_score, extraction_method)

    Enforces hard decision thresholds via get_quality_band():
    - GOOD (≥ 0.5): keep result, no vision
    - BORDERLINE (0.3–0.5): vision fallback allowed, pick better
    - LOW (< 0.3): vision only if image AND DOCUMENT_VISION_FALLBACK_ENABLED
    """
    from src.config import DOCUMENT_VISION_FALLBACK_ENABLED
    from src.services.image_preprocessor import (
        compute_text_quality_score,
        get_quality_band,
        preprocess_for_ocr,
    )
    from src.services.vision_extractor import extract_text_with_vision

    if not os.path.isfile(file_path):
        logger.warning("extract_text_v2: file not found: %s", file_path)
        return "", 0.0, "unsupported"

    _, ext = os.path.splitext(file_path)
    ext = ext.lower()

    # Detect file type by MIME when extension is missing or generic
    if not ext or ext in ("", ".bin", ".dat"):
        detected = _detect_extension_by_mime(file_path)
        if detected:
            logger.info("extract_text_v2: detected extension %s for %s via MIME", detected, os.path.basename(file_path))
            ext = detected

    is_image = ext in _IMAGE_EXTENSIONS

    # ── PDF path ─────────────────────────────────────────────────────
    if ext == ".pdf":
        # Digital PDF guarantee: pdfplumber with good quality → return immediately
        text = _extract_pdf_pdfplumber_only(file_path)
        if text.strip():
            score = compute_text_quality_score(text)
            if get_quality_band(score) == "GOOD":
                return text, score, "pdfplumber"

        # Scanned PDF — convert to images, run image pipeline
        text, score = _ocr_pdf_v2(file_path)

        band = get_quality_band(score)
        if band == "GOOD":
            return text, score, "ocr_preprocessed"

        if band == "BORDERLINE" and DOCUMENT_VISION_FALLBACK_ENABLED:
            vision_text = await extract_text_with_vision(file_path)
            if vision_text:
                vision_score = compute_text_quality_score(vision_text)
                if vision_score > score:
                    return vision_text, vision_score, "vision"
            return text, score, "ocr_preprocessed"

        # LOW or vision disabled
        return text, score, "ocr_preprocessed"

    # ── Image path ───────────────────────────────────────────────────
    if is_image:
        try:
            import pytesseract
        except ImportError:
            logger.info("extract_text_v2: pytesseract not installed")
            return "", 0.0, "unsupported"

        preprocessed = preprocess_for_ocr(file_path)
        try:
            ocr_text = pytesseract.image_to_string(preprocessed, lang="heb+eng").strip()
        except Exception:
            logger.exception("extract_text_v2: OCR failed for %s", file_path)
            ocr_text = ""

        ocr_score = compute_text_quality_score(ocr_text)
        band = get_quality_band(ocr_score)

        if band == "GOOD":
            return ocr_text, ocr_score, "ocr_preprocessed"

        if band == "BORDERLINE" and DOCUMENT_VISION_FALLBACK_ENABLED:
            vision_text = await extract_text_with_vision(file_path)
            if vision_text:
                vision_score = compute_text_quality_score(vision_text)
                if vision_score > ocr_score:
                    return vision_text, vision_score, "vision"
            return ocr_text, ocr_score, "ocr_preprocessed"

        if band == "LOW" and DOCUMENT_VISION_FALLBACK_ENABLED:
            vision_text = await extract_text_with_vision(file_path)
            if vision_text:
                vision_score = compute_text_quality_score(vision_text)
                return vision_text, vision_score, "vision"

        return ocr_text, ocr_score, "ocr_preprocessed"

    # ── DOCX path ────────────────────────────────────────────────────
    if ext in (".doc", ".docx"):
        text = _extract_docx(file_path)
        score = compute_text_quality_score(text)
        return text, score, "docx"

    # ── Unsupported ──────────────────────────────────────────────────
    return "", 0.0, "unsupported"


def _extract_pdf_pdfplumber_only(file_path: str) -> str:
    """Extract text from PDF using pdfplumber only (no OCR fallback)."""
    try:
        import pdfplumber
    except ImportError:
        return ""

    pages_text: list[str] = []
    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)
    except Exception:
        logger.exception("_extract_pdf_pdfplumber_only: failed for %s", file_path)
        return ""

    return "\n\n".join(pages_text)


def _ocr_pdf_v2(file_path: str) -> tuple[str, float]:
    """OCR a scanned PDF with preprocessing. Returns (text, quality_score)."""
    from src.services.image_preprocessor import compute_text_quality_score, preprocess_for_ocr

    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError:
        logger.info("_ocr_pdf_v2: pdf2image/pytesseract not installed")
        return "", 0.0

    try:
        images = convert_from_path(file_path, dpi=300, first_page=1, last_page=10)
        pages_text: list[str] = []
        for img in images:
            # Save temp image for preprocessing
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                img.save(tmp, format="PNG")
                tmp_path = tmp.name
            try:
                preprocessed = preprocess_for_ocr(tmp_path)
                text = pytesseract.image_to_string(preprocessed, lang="heb+eng").strip()
                if text:
                    pages_text.append(text)
            finally:
                os.unlink(tmp_path)

        combined = "\n\n".join(pages_text)
        score = compute_text_quality_score(combined)
        return combined, score
    except Exception:
        logger.exception("_ocr_pdf_v2: failed for %s", file_path)
        return "", 0.0
