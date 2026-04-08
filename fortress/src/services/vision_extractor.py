"""Bedrock Vision Extractor — extract text from images using Claude haiku vision.

Gated by DOCUMENT_VISION_FALLBACK_ENABLED config flag.
Returns empty string on any failure — never raises.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re

logger = logging.getLogger(__name__)

# Max image size for Bedrock inline images (4MB to be safe under 5MB limit)
_MAX_IMAGE_BYTES = 4 * 1024 * 1024

_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".bmp": "image/bmp",
    ".tiff": "image/tiff",
    ".heic": "image/jpeg",  # convert HEIC to JPEG before sending
}


def _resize_image_if_needed(image_path: str) -> bytes:
    """Read image bytes, resizing if > 4MB."""
    from PIL import Image
    import io

    raw = open(image_path, "rb").read()
    if len(raw) <= _MAX_IMAGE_BYTES:
        return raw

    logger.info("vision_extractor: image %s is %d bytes, resizing", os.path.basename(image_path), len(raw))
    img = Image.open(image_path)
    # Reduce dimensions until under limit
    quality = 85
    while quality >= 30:
        buf = io.BytesIO()
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.save(buf, format="JPEG", quality=quality)
        if buf.tell() <= _MAX_IMAGE_BYTES:
            return buf.getvalue()
        quality -= 15

    # Last resort: scale down
    img.thumbnail((1600, 1600))
    buf = io.BytesIO()
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    img.save(buf, format="JPEG", quality=60)
    return buf.getvalue()


async def extract_text_with_vision(
    image_path: str,
    doc_type_hint: str | None = None,
) -> str:
    """Extract text from an image using Bedrock vision model (Claude haiku).

    Returns empty string immediately if DOCUMENT_VISION_FALLBACK_ENABLED is false.
    Returns extracted text or empty string on any failure — never raises.
    Uses haiku tier to keep costs reasonable.
    """
    from src.config import DOCUMENT_VISION_FALLBACK_ENABLED

    if not DOCUMENT_VISION_FALLBACK_ENABLED:
        return ""

    try:
        from src.services.bedrock_client import BedrockClient

        image_bytes = _resize_image_if_needed(image_path)
        b64_image = base64.b64encode(image_bytes).decode("utf-8")

        _, ext = os.path.splitext(image_path)
        media_type = _MEDIA_TYPES.get(ext.lower(), "image/jpeg")

        # Build Hebrew-focused extraction prompt
        type_hint = f" This appears to be a {doc_type_hint}." if doc_type_hint else ""
        system_prompt = (
            "You are a document text extraction assistant. "
            "Extract ALL text from the provided image accurately. "
            "The document is likely in Hebrew. Preserve the original language, "
            "layout structure, and line breaks as much as possible. "
            "Return ONLY the extracted text, no commentary."
            f"{type_hint}"
        )

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "image": {
                            "format": media_type.split("/")[-1],
                            "source": {"bytes": b64_image},
                        }
                    },
                    {"text": "Extract all text from this document image."},
                ],
            }
        ]

        client = BedrockClient()
        response = await client.converse(
            messages=messages,
            system_prompt=system_prompt,
            model="haiku",
            max_tokens=4096,
        )

        text = (response.text or "").strip()
        logger.info(
            "vision_extractor: extracted %d chars from %s",
            len(text), os.path.basename(image_path),
        )
        return text

    except Exception:
        logger.exception("vision_extractor: failed for %s", image_path)
        return ""


async def extract_structured_with_vision(image_path: str) -> dict:
    """Extract salary-slip structured fields from an image via Bedrock haiku.

    Returns parsed JSON dict with strict expected keys.
    Returns {} on any failure.
    """
    expected_keys = {
        "employee_name": None,
        "employer_name": None,
        "pay_month": None,
        "gross_salary": None,
        "net_salary": None,
        "net_to_pay": None,
        "total_deductions": None,
        "income_tax": None,
        "national_insurance": None,
        "health_tax": None,
        "pension_employee": None,
        "pension_employer": None,
        "confidence": 0.0,
    }
    try:
        from src.services.bedrock_client import BedrockClient

        image_bytes = _resize_image_if_needed(image_path)
        b64_image = base64.b64encode(image_bytes).decode("utf-8")
        _, ext = os.path.splitext(image_path)
        media_type = _MEDIA_TYPES.get(ext.lower(), "image/jpeg")

        system_prompt = "You extract structured data from salary slips."
        user_prompt = (
            "Return ONLY valid JSON.\n"
            "Do not include any explanation.\n"
            "Do not include text before or after the JSON.\n"
            "If you are unsure about a field, return null.\n"
            "All numbers must be numeric, not strings.\n\n"
            "JSON format:\n"
            "{\n"
            '  "employee_name": string | null,\n'
            '  "employer_name": string | null,\n'
            '  "pay_month": string | null,\n'
            '  "gross_salary": number | null,\n'
            '  "net_salary": number | null,\n'
            '  "net_to_pay": number | null,\n'
            '  "total_deductions": number | null,\n'
            '  "income_tax": number | null,\n'
            '  "national_insurance": number | null,\n'
            '  "health_tax": number | null,\n'
            '  "pension_employee": number | null,\n'
            '  "pension_employer": number | null,\n'
            '  "confidence": number\n'
            "}"
        )
        messages = [{
            "role": "user",
            "content": [
                {
                    "image": {
                        "format": media_type.split("/")[-1],
                        "source": {"bytes": b64_image},
                    }
                },
                {"text": user_prompt},
            ],
        }]
        client = BedrockClient()
        response = await client.converse(
            messages=messages,
            system_prompt=system_prompt,
            model="haiku",
            max_tokens=1200,
        )
        logger.info("VISION STRUCTURED RAW RESPONSE: %s", response.text)
        raw = (response.text or "").strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            # tolerate wrappers/noise and extract first JSON object block
            match = re.search(r"\{[\s\S]*\}", raw)
            if not match:
                return {}
            try:
                parsed = json.loads(match.group(0).strip())
            except json.JSONDecodeError:
                return {}
        if not isinstance(parsed, dict):
            return {}

        result = dict(expected_keys)
        for key in expected_keys:
            if key not in parsed:
                continue
            val = parsed.get(key)
            if key in {"employee_name", "employer_name", "pay_month"}:
                result[key] = str(val).strip() if val is not None else None
            elif key == "confidence":
                try:
                    result[key] = max(0.0, min(1.0, float(val)))
                except (TypeError, ValueError):
                    result[key] = 0.0
            else:
                try:
                    result[key] = float(val) if val is not None else None
                except (TypeError, ValueError):
                    result[key] = None
        return result
    except Exception:
        logger.exception("vision_extractor: structured extraction failed for %s", image_path)
        return {}
