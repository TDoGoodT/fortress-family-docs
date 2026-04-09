"""AWS Bedrock Vision processor — Claude vision for document extraction.

Wraps the existing vision_extractor as a processor backend.
Used as fallback when Google Document AI is unavailable, or for
document types where LLM reasoning adds value over pure OCR.
"""
from __future__ import annotations

import logging
import os

from src.services.document_processors.base_processor import BaseProcessor, ProcessorResult

logger = logging.getLogger(__name__)

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".heic"}


class BedrockVisionProcessor(BaseProcessor):
    """AWS Bedrock Claude Vision — LLM-based document understanding."""

    name = "bedrock_vision"

    def is_available(self) -> bool:
        from src.config import DOCUMENT_VISION_FALLBACK_ENABLED
        if not DOCUMENT_VISION_FALLBACK_ENABLED:
            return False
        try:
            from src.services.bedrock_client import BedrockClient  # noqa: F401
            return True
        except ImportError:
            return False

    async def process(self, file_path: str, mime_type: str = "") -> ProcessorResult:
        from src.services.vision_extractor import extract_text_with_vision

        _, ext = os.path.splitext(file_path)
        if ext.lower() not in _IMAGE_EXTENSIONS and ext.lower() != ".pdf":
            return ProcessorResult(processor_name=self.name, extraction_method="unsupported")

        try:
            text = await extract_text_with_vision(file_path)
        except Exception as exc:
            logger.error("bedrock_vision: failed %s: %s", os.path.basename(file_path), exc)
            return ProcessorResult(processor_name=self.name, extraction_method="error")

        if not text:
            return ProcessorResult(processor_name=self.name, extraction_method="empty")

        logger.info("bedrock_vision: extracted %d chars from %s", len(text), os.path.basename(file_path))

        return ProcessorResult(
            raw_text=text,
            confidence=0.6,  # vision extraction is decent but not as reliable as dedicated OCR
            processor_name=self.name,
            extraction_method="bedrock_vision",
        )
