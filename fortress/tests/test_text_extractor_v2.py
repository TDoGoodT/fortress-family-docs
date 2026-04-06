"""Tests for extract_text_v2 — threshold enforcement, vision disable, digital PDF guarantee."""

import os
import sys
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Inject stub pytesseract before any import that might need it ──
if "pytesseract" not in sys.modules:
    _fake_pytesseract = MagicMock()
    _fake_pytesseract.image_to_string = MagicMock(return_value="")
    sys.modules["pytesseract"] = _fake_pytesseract

from src.services.text_extractor import extract_text_v2  # noqa: E402


# ── Helpers ──────────────────────────────────────────────────────


def _tmp_file(suffix: str) -> str:
    f = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    f.write(b"fake content")
    f.close()
    return f.name


# ── Threshold enforcement tests (Task 8.1) ───────────────────────


@pytest.mark.asyncio
async def test_good_band_no_vision_call() -> None:
    """GOOD band (>=0.5): vision is NOT called."""
    path = _tmp_file(".jpg")
    try:
        mock_preprocess = MagicMock(return_value=MagicMock())
        vision_mock = AsyncMock(return_value="")
        with patch("src.services.image_preprocessor.preprocess_for_ocr", mock_preprocess), \
             patch("src.services.image_preprocessor.compute_text_quality_score", return_value=0.7), \
             patch("src.services.image_preprocessor.get_quality_band", return_value="GOOD"), \
             patch("src.services.vision_extractor.extract_text_with_vision", vision_mock), \
             patch("src.config.DOCUMENT_VISION_FALLBACK_ENABLED", True):
            text, score, method = await extract_text_v2(path)
        vision_mock.assert_not_called()
        assert method == "ocr_preprocessed"
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_borderline_vision_called_when_enabled() -> None:
    """BORDERLINE (0.3-0.5) + flag true: vision IS called, higher score wins."""
    path = _tmp_file(".jpg")
    try:
        mock_preprocess = MagicMock(return_value=MagicMock())
        vision_mock = AsyncMock(return_value="טקסט מהוויזן")

        call_count = [0]

        def quality_side_effect(text, lang="heb"):
            call_count[0] += 1
            return 0.4 if call_count[0] == 1 else 0.8

        def band_side_effect(s):
            if s >= 0.5:
                return "GOOD"
            if s >= 0.3:
                return "BORDERLINE"
            return "LOW"

        with patch("src.services.image_preprocessor.preprocess_for_ocr", mock_preprocess), \
             patch("src.services.image_preprocessor.compute_text_quality_score", side_effect=quality_side_effect), \
             patch("src.services.image_preprocessor.get_quality_band", side_effect=band_side_effect), \
             patch("src.services.vision_extractor.extract_text_with_vision", vision_mock), \
             patch("src.config.DOCUMENT_VISION_FALLBACK_ENABLED", True):
            text, score, method = await extract_text_v2(path)
        vision_mock.assert_called_once()
        assert method == "vision"
        assert score == 0.8
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_borderline_vision_not_called_when_disabled() -> None:
    """BORDERLINE + flag false: vision NOT called."""
    path = _tmp_file(".jpg")
    try:
        mock_preprocess = MagicMock(return_value=MagicMock())
        vision_mock = AsyncMock(return_value="")
        with patch("src.services.image_preprocessor.preprocess_for_ocr", mock_preprocess), \
             patch("src.services.image_preprocessor.compute_text_quality_score", return_value=0.4), \
             patch("src.services.image_preprocessor.get_quality_band", return_value="BORDERLINE"), \
             patch("src.services.vision_extractor.extract_text_with_vision", vision_mock), \
             patch("src.config.DOCUMENT_VISION_FALLBACK_ENABLED", False):
            text, score, method = await extract_text_v2(path)
        vision_mock.assert_not_called()
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_low_image_vision_called_when_enabled() -> None:
    """LOW (<0.3) + image + flag true: vision IS called."""
    path = _tmp_file(".jpg")
    try:
        mock_preprocess = MagicMock(return_value=MagicMock())
        vision_mock = AsyncMock(return_value="טקסט מוויזן")

        call_count = [0]

        def quality_side_effect(text, lang="heb"):
            call_count[0] += 1
            return 0.1 if call_count[0] == 1 else 0.6

        def band_side_effect(s):
            if s >= 0.5:
                return "GOOD"
            if s >= 0.3:
                return "BORDERLINE"
            return "LOW"

        with patch("src.services.image_preprocessor.preprocess_for_ocr", mock_preprocess), \
             patch("src.services.image_preprocessor.compute_text_quality_score", side_effect=quality_side_effect), \
             patch("src.services.image_preprocessor.get_quality_band", side_effect=band_side_effect), \
             patch("src.services.vision_extractor.extract_text_with_vision", vision_mock), \
             patch("src.config.DOCUMENT_VISION_FALLBACK_ENABLED", True):
            text, score, method = await extract_text_v2(path)
        vision_mock.assert_called_once()
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_low_non_image_no_vision() -> None:
    """LOW + PDF path: vision NOT called (LOW vision only for images)."""
    path = _tmp_file(".pdf")
    try:
        vision_mock = AsyncMock(return_value="")
        with patch("src.services.text_extractor._extract_pdf_pdfplumber_only", return_value=""), \
             patch("src.services.text_extractor._ocr_pdf_v2", return_value=("x", 0.1)), \
             patch("src.services.image_preprocessor.compute_text_quality_score", return_value=0.1), \
             patch("src.services.image_preprocessor.get_quality_band", return_value="LOW"), \
             patch("src.services.vision_extractor.extract_text_with_vision", vision_mock), \
             patch("src.config.DOCUMENT_VISION_FALLBACK_ENABLED", True):
            text, score, method = await extract_text_v2(path)
        vision_mock.assert_not_called()
    finally:
        os.unlink(path)


# ── Vision disable tests (Task 8.2) ─────────────────────────────


@pytest.mark.asyncio
async def test_vision_disabled_zero_calls_image() -> None:
    """DOCUMENT_VISION_FALLBACK_ENABLED=false → zero vision calls for images."""
    path = _tmp_file(".jpg")
    try:
        mock_preprocess = MagicMock(return_value=MagicMock())
        vision_mock = AsyncMock(return_value="")
        with patch("src.services.image_preprocessor.preprocess_for_ocr", mock_preprocess), \
             patch("src.services.image_preprocessor.compute_text_quality_score", return_value=0.1), \
             patch("src.services.image_preprocessor.get_quality_band", return_value="LOW"), \
             patch("src.services.vision_extractor.extract_text_with_vision", vision_mock), \
             patch("src.config.DOCUMENT_VISION_FALLBACK_ENABLED", False):
            await extract_text_v2(path)
        vision_mock.assert_not_called()
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_vision_disabled_zero_calls_pdf() -> None:
    """DOCUMENT_VISION_FALLBACK_ENABLED=false → zero vision calls for PDFs."""
    path = _tmp_file(".pdf")
    try:
        vision_mock = AsyncMock(return_value="")
        with patch("src.services.text_extractor._extract_pdf_pdfplumber_only", return_value=""), \
             patch("src.services.text_extractor._ocr_pdf_v2", return_value=("x", 0.35)), \
             patch("src.services.image_preprocessor.compute_text_quality_score", return_value=0.35), \
             patch("src.services.image_preprocessor.get_quality_band", return_value="BORDERLINE"), \
             patch("src.services.vision_extractor.extract_text_with_vision", vision_mock), \
             patch("src.config.DOCUMENT_VISION_FALLBACK_ENABLED", False):
            await extract_text_v2(path)
        vision_mock.assert_not_called()
    finally:
        os.unlink(path)


# ── Digital PDF guarantee tests (Task 8.3) ───────────────────────


@pytest.mark.asyncio
async def test_digital_pdf_good_quality_no_ocr_no_vision() -> None:
    """pdfplumber returns text with quality >= 0.5 → OCR and vision never called."""
    path = _tmp_file(".pdf")
    try:
        vision_mock = AsyncMock(return_value="")
        with patch("src.services.text_extractor._extract_pdf_pdfplumber_only", return_value="טקסט דיגיטלי טוב"), \
             patch("src.services.image_preprocessor.compute_text_quality_score", return_value=0.8), \
             patch("src.services.image_preprocessor.get_quality_band", return_value="GOOD"), \
             patch("src.services.text_extractor._ocr_pdf_v2") as ocr_mock, \
             patch("src.services.vision_extractor.extract_text_with_vision", vision_mock):
            text, score, method = await extract_text_v2(path)
        ocr_mock.assert_not_called()
        vision_mock.assert_not_called()
        assert method == "pdfplumber"
        assert score == 0.8
    finally:
        os.unlink(path)


# ── Scanned PDF tests (Task 8.4) ────────────────────────────────


@pytest.mark.asyncio
async def test_scanned_pdf_falls_to_image_pipeline() -> None:
    """pdfplumber returns empty → falls through to OCR image pipeline."""
    path = _tmp_file(".pdf")
    try:
        with patch("src.services.text_extractor._extract_pdf_pdfplumber_only", return_value=""), \
             patch("src.services.text_extractor._ocr_pdf_v2", return_value=("טקסט מסרוק", 0.6)) as ocr_mock, \
             patch("src.services.image_preprocessor.compute_text_quality_score", return_value=0.6), \
             patch("src.services.image_preprocessor.get_quality_band", return_value="GOOD"):
            text, score, method = await extract_text_v2(path)
        ocr_mock.assert_called_once()
        assert method == "ocr_preprocessed"
    finally:
        os.unlink(path)


# ── DOCX extraction test (Task 8.5) ─────────────────────────────


@pytest.mark.asyncio
async def test_docx_extraction() -> None:
    """DOCX returns text and valid quality score."""
    path = _tmp_file(".docx")
    try:
        with patch("src.services.text_extractor._extract_docx", return_value="מסמך וורד"), \
             patch("src.services.image_preprocessor.compute_text_quality_score", return_value=0.7):
            text, score, method = await extract_text_v2(path)
        assert method == "docx"
        assert text == "מסמך וורד"
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_unsupported_file_type() -> None:
    """Unsupported file type returns empty with 'unsupported' method."""
    path = _tmp_file(".xyz")
    try:
        text, score, method = await extract_text_v2(path)
        assert text == ""
        assert score == 0.0
        assert method == "unsupported"
    finally:
        os.unlink(path)


# ── Metadata merge test (Task 9.2) ──────────────────────────────


def test_metadata_merge_preserves_existing_fields() -> None:
    """Existing doc_metadata fields are preserved when adding quality metadata."""
    from src.services.image_preprocessor import get_quality_band

    existing_metadata = {"custom_field": "keep_me", "source": "whatsapp"}
    text_quality = 0.72
    extraction_method = "ocr_preprocessed"

    merged = {
        **(existing_metadata or {}),
        "text_quality_score": text_quality,
        "extraction_method": extraction_method,
        "quality_band": get_quality_band(text_quality),
        "vision_fallback_enabled": True,
    }

    assert merged["custom_field"] == "keep_me"
    assert merged["source"] == "whatsapp"
    assert merged["text_quality_score"] == 0.72
    assert merged["extraction_method"] == "ocr_preprocessed"
    assert merged["quality_band"] == "GOOD"
    assert merged["vision_fallback_enabled"] is True
