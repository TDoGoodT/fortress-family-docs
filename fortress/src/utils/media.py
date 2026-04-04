from __future__ import annotations
"""Fortress 2.0 media download and storage utilities."""

import logging
import os
import uuid
from datetime import datetime

import httpx

from src.config import STORAGE_PATH, WAHA_API_URL, WAHA_API_KEY

logger = logging.getLogger(__name__)


async def download_media(
    message_id: str,
    session: str = "default",
) -> tuple[bytes, str] | None:
    """Download media from WAHA API.

    Returns (file_bytes, mimetype) or None on failure.
    """
    try:
        headers: dict[str, str] = {}
        if WAHA_API_KEY:
            headers["X-Api-Key"] = WAHA_API_KEY
        async with httpx.AsyncClient(timeout=30.0) as client:
            url = f"{WAHA_API_URL}/api/{session}/messages/{message_id}/download"
            response = await client.get(url, headers=headers)
            if response.status_code != 200:
                logger.error("Media download failed: %s %s", response.status_code, response.text)
                return None
            mimetype = response.headers.get("content-type", "application/octet-stream")
            return response.content, mimetype
    except Exception:
        logger.exception("Error downloading media for message %s", message_id)
        return None


def save_media(
    file_bytes: bytes,
    original_filename: str,
    mimetype: str,
) -> str:
    """Save media bytes to STORAGE_PATH/{year}/{month}/{uuid}_{filename}.

    Creates directories as needed. Returns the saved file path.
    """
    now = datetime.now()
    directory = os.path.join(STORAGE_PATH, str(now.year), f"{now.month:02d}")
    os.makedirs(directory, exist_ok=True)

    safe_name = original_filename or "file"
    filename = f"{uuid.uuid4()}_{safe_name}"
    file_path = os.path.join(directory, filename)

    with open(file_path, "wb") as f:
        f.write(file_bytes)

    logger.info("Saved media: %s (%s, %d bytes)", file_path, mimetype, len(file_bytes))
    return file_path
