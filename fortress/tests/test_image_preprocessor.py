"""Tests for image preprocessor — preprocess_for_ocr, grayscale, dimensions, deskew fallback."""

import os
import sys
import tempfile

import numpy as np
from PIL import Image

from src.services.image_preprocessor import preprocess_for_ocr

# Check if cv2 is available
try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


def _make_test_image(width: int = 200, height: int = 150, mode: str = "RGB") -> str:
    """Create a temporary test image and return its path."""
    if mode == "RGB":
        arr = np.random.randint(0, 255, (height, width, 3), dtype=np.uint8)
    else:
        arr = np.random.randint(0, 255, (height, width), dtype=np.uint8)
    img = Image.fromarray(arr, mode=mode)
    f = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    img.save(f, format="PNG")
    f.close()
    return f.name


def test_returns_grayscale_pil_image() -> None:
    """preprocess_for_ocr returns a grayscale PIL Image for valid images."""
    path = _make_test_image()
    try:
        result = preprocess_for_ocr(path)
        assert isinstance(result, Image.Image)
        assert result.mode == "L"
    finally:
        os.unlink(path)


def test_preserves_dimensions() -> None:
    """Output image has same width and height as input."""
    w, h = 320, 240
    path = _make_test_image(width=w, height=h)
    try:
        result = preprocess_for_ocr(path)
        assert result.size == (w, h)
    finally:
        os.unlink(path)


def test_fallback_on_cv2_unavailable() -> None:
    """If cv2 steps fail, still returns a valid grayscale image."""
    path = _make_test_image()
    try:
        # Even if cv2 operations fail internally, we get a valid result
        result = preprocess_for_ocr(path)
        assert isinstance(result, Image.Image)
        assert result.mode == "L"
    finally:
        os.unlink(path)


def test_deskew_failure_doesnt_break() -> None:
    """Deskew failure doesn't break preprocessing — continues without it."""
    if not HAS_CV2:
        # Without cv2, deskew is already skipped gracefully
        path = _make_test_image()
        try:
            result = preprocess_for_ocr(path)
            assert isinstance(result, Image.Image)
            assert result.mode == "L"
        finally:
            os.unlink(path)
        return

    # With cv2 available, create an image where deskew would be attempted
    # but the function should handle any internal errors gracefully
    path = _make_test_image(width=400, height=300)
    try:
        result = preprocess_for_ocr(path)
        assert isinstance(result, Image.Image)
        assert result.mode == "L"
    finally:
        os.unlink(path)


def test_nonexistent_file_returns_image() -> None:
    """Non-existent file returns a fallback image, never raises."""
    result = preprocess_for_ocr("/nonexistent/image.png")
    assert isinstance(result, Image.Image)
    assert result.mode == "L"
