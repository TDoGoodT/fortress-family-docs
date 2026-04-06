"""Image preprocessing and text quality scoring for OCR pipeline.

Provides image preprocessing (grayscale, CLAHE, denoise, deskew, threshold)
and text quality scoring for Hebrew documents.
"""
from __future__ import annotations

import logging
import re

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


def preprocess_for_ocr(file_path: str) -> Image.Image:
    """Apply preprocessing pipeline to an image for OCR.

    Steps: grayscale → CLAHE contrast → bilateral denoise → deskew → adaptive threshold.
    On any failure in a step, continues with what we have.
    On total failure, returns original image in grayscale.
    Never raises, never returns None. Preserves dimensions.
    """
    try:
        original = Image.open(file_path)
    except Exception:
        logger.exception("preprocess_for_ocr: failed to open %s", file_path)
        # Return a 1x1 grayscale image as absolute fallback
        return Image.new("L", (1, 1), 128)

    try:
        gray = original.convert("L")
    except Exception:
        logger.exception("preprocess_for_ocr: grayscale conversion failed")
        return original.convert("L") if original.mode != "L" else original

    img_array = np.array(gray)

    # CLAHE contrast enhancement
    try:
        import cv2
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        img_array = clahe.apply(img_array)
    except Exception:
        logger.warning("preprocess_for_ocr: CLAHE failed, continuing")

    # Bilateral denoise
    try:
        import cv2
        img_array = cv2.bilateralFilter(img_array, d=9, sigmaColor=75, sigmaSpace=75)
    except Exception:
        logger.warning("preprocess_for_ocr: bilateral denoise failed, continuing")

    # Deskew (best-effort)
    try:
        import cv2
        coords = np.column_stack(np.where(img_array < 128))
        if len(coords) > 50:
            angle = cv2.minAreaRect(coords)[-1]
            if angle < -45:
                angle = -(90 + angle)
            else:
                angle = -angle
            if abs(angle) > 0.5 and abs(angle) < 15:
                h, w = img_array.shape
                center = (w // 2, h // 2)
                M = cv2.getRotationMatrix2D(center, angle, 1.0)
                img_array = cv2.warpAffine(
                    img_array, M, (w, h),
                    flags=cv2.INTER_CUBIC,
                    borderMode=cv2.BORDER_REPLICATE,
                )
    except Exception:
        logger.warning("preprocess_for_ocr: deskew failed, continuing without it")

    # Adaptive threshold
    try:
        import cv2
        img_array = cv2.adaptiveThreshold(
            img_array, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=11, C=2,
        )
    except Exception:
        logger.warning("preprocess_for_ocr: adaptive threshold failed, continuing")

    return Image.fromarray(img_array).convert("L")


# ── Hebrew character ranges ──────────────────────────────────────────

_HEBREW_PATTERN = re.compile(r"[\u0590-\u05FF]")
_GIBBERISH_PATTERN = re.compile(r"[bcdfghjklmnpqrstvwxyz]{5,}", re.IGNORECASE)


def compute_text_quality_score(raw_text: str, lang: str = "heb") -> float:
    """Score extracted text quality from 0.0 to 1.0.

    Heuristics:
    - Hebrew character ratio (expect > 0.3 for Hebrew docs)
    - Average word length (Hebrew words avg 4-6 chars)
    - Gibberish detection (consecutive consonants)
    - Line structure (expect some line breaks)

    Returns 0.0 for empty/whitespace input.
    """
    if not raw_text or not raw_text.strip():
        return 0.0

    text = raw_text.strip()
    total_chars = len(text)
    if total_chars == 0:
        return 0.0

    scores: list[float] = []

    # 1. Hebrew character ratio (weight: high for Hebrew docs)
    hebrew_chars = len(_HEBREW_PATTERN.findall(text))
    alpha_chars = sum(1 for c in text if c.isalpha())
    if alpha_chars > 0:
        heb_ratio = hebrew_chars / alpha_chars
    else:
        heb_ratio = 0.0

    if lang == "heb":
        if heb_ratio >= 0.4:
            scores.append(1.0)
        elif heb_ratio >= 0.2:
            scores.append(0.6)
        elif heb_ratio >= 0.05:
            scores.append(0.3)
        else:
            scores.append(0.1)
    else:
        scores.append(0.5)  # neutral for non-Hebrew

    # 2. Average word length
    words = text.split()
    if words:
        avg_len = sum(len(w) for w in words) / len(words)
        if 2.5 <= avg_len <= 10:
            scores.append(1.0)
        elif 1.5 <= avg_len <= 15:
            scores.append(0.5)
        else:
            scores.append(0.1)
    else:
        scores.append(0.0)

    # 3. Gibberish detection (long consonant runs = bad OCR)
    gibberish_matches = _GIBBERISH_PATTERN.findall(text)
    gibberish_chars = sum(len(m) for m in gibberish_matches)
    gibberish_ratio = gibberish_chars / total_chars if total_chars > 0 else 0
    if gibberish_ratio < 0.05:
        scores.append(1.0)
    elif gibberish_ratio < 0.15:
        scores.append(0.5)
    else:
        scores.append(0.1)

    # 4. Line structure (some line breaks expected, not one giant blob)
    lines = text.split("\n")
    num_lines = len(lines)
    if num_lines >= 3:
        scores.append(1.0)
    elif num_lines >= 2:
        scores.append(0.7)
    else:
        # Single line — could be fine for short text
        if total_chars < 100:
            scores.append(0.6)
        else:
            scores.append(0.3)

    # Weighted average
    weights = [0.4, 0.2, 0.25, 0.15]
    score = sum(s * w for s, w in zip(scores, weights))
    return max(0.0, min(1.0, score))


def get_quality_band(score: float) -> str:
    """Return quality band label for a given score.

    Single source of truth for threshold logic:
    - "GOOD" when score >= 0.5
    - "BORDERLINE" when 0.3 <= score < 0.5
    - "LOW" when score < 0.3
    """
    if score >= 0.5:
        return "GOOD"
    if score >= 0.3:
        return "BORDERLINE"
    return "LOW"
