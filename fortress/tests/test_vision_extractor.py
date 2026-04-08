"""Tests for vision extractor — flag disable, API call, failure handling, resize."""

import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from src.services.vision_extractor import extract_text_with_vision, extract_structured_with_vision


def _make_test_image() -> str:
    """Create a test image file."""
    img = Image.fromarray(np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8))
    f = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    img.save(f, format="JPEG")
    f.close()
    return f.name


def _mock_bedrock_client(response_text: str = "", side_effect=None):
    """Create a mock BedrockClient class that returns a mock instance."""
    mock_response = MagicMock()
    mock_response.text = response_text
    mock_instance = MagicMock()
    if side_effect:
        mock_instance.converse = AsyncMock(side_effect=side_effect)
    else:
        mock_instance.converse = AsyncMock(return_value=mock_response)
    mock_class = MagicMock(return_value=mock_instance)
    return mock_class, mock_instance


@pytest.mark.asyncio
async def test_flag_false_returns_empty_no_api_call() -> None:
    """Flag false → returns empty string immediately (no API call)."""
    path = _make_test_image()
    try:
        with patch("src.config.DOCUMENT_VISION_FALLBACK_ENABLED", False):
            result = await extract_text_with_vision(path)
        assert result == ""
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_flag_true_calls_bedrock() -> None:
    """Flag true → calls Bedrock haiku with image."""
    path = _make_test_image()
    try:
        mock_class, mock_instance = _mock_bedrock_client("טקסט שחולץ")
        with patch("src.config.DOCUMENT_VISION_FALLBACK_ENABLED", True), \
             patch("src.services.bedrock_client.BedrockClient", mock_class):
            result = await extract_text_with_vision(path)

        assert result == "טקסט שחולץ"
        mock_instance.converse.assert_called_once()
        call_kwargs = mock_instance.converse.call_args
        assert call_kwargs.kwargs.get("model") == "haiku"
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_api_failure_returns_empty() -> None:
    """API failure → returns empty string."""
    path = _make_test_image()
    try:
        mock_class, _ = _mock_bedrock_client(side_effect=RuntimeError("API down"))
        with patch("src.config.DOCUMENT_VISION_FALLBACK_ENABLED", True), \
             patch("src.services.bedrock_client.BedrockClient", mock_class):
            result = await extract_text_with_vision(path)

        assert result == ""
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_large_image_resized() -> None:
    """Image > 4MB → resized before send."""
    big_img = Image.fromarray(np.random.randint(0, 255, (3000, 3000, 3), dtype=np.uint8))
    f = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    big_img.save(f, format="PNG")
    f.close()
    path = f.name

    try:
        mock_class, mock_instance = _mock_bedrock_client("resized text")
        with patch("src.config.DOCUMENT_VISION_FALLBACK_ENABLED", True), \
             patch("src.services.bedrock_client.BedrockClient", mock_class):
            result = await extract_text_with_vision(path)

        assert result == "resized text"
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_extract_structured_with_vision_valid_dict() -> None:
    path = _make_test_image()
    try:
        response = (
            '{"employee_name":"דנה כהן","employer_name":"חברת דוגמה","pay_month":"2026-03",'
            '"gross_salary":10000.0,"net_salary":7800.0,"net_to_pay":7800.0,'
            '"total_deductions":2200.0,"income_tax":900.0,"national_insurance":500.0,'
            '"health_tax":300.0,"pension_employee":300.0,"pension_employer":200.0,"confidence":0.92}'
        )
        mock_class, _ = _mock_bedrock_client(response)
        with patch("src.services.bedrock_client.BedrockClient", mock_class):
            result = await extract_structured_with_vision(path)
        assert result["employee_name"] == "דנה כהן"
        assert result["gross_salary"] == 10000.0
        assert result["confidence"] == 0.92
    finally:
        os.unlink(path)


@pytest.mark.asyncio
async def test_extract_structured_with_vision_failure_returns_empty() -> None:
    path = _make_test_image()
    try:
        mock_class, _ = _mock_bedrock_client(side_effect=RuntimeError("API down"))
        with patch("src.services.bedrock_client.BedrockClient", mock_class):
            result = await extract_structured_with_vision(path)
        assert result == {}
    finally:
        os.unlink(path)
