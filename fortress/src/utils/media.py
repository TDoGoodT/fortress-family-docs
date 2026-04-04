from __future__ import annotations
"""Fortress 2.0 media download and storage utilities."""

import logging
import os
import uuid
from datetime import datetime

import httpx

from src.config import STORAGE_PATH, WAHA_API_URL, WAHA_API_KEY

logger = logging.getLogger(__name__)


async def download_media_url(
    url: str,
) -> tuple[bytes, str] | None:
    """Download media directly from a WAHA media URL.

    WAHA builds media URLs using WHATSAPP_API_HOSTNAME which may not
    match the Docker-internal address the app should use.  We extract
    the path portion (e.g. /api/files/...) and prepend WAHA_API_URL.

    Returns (file_bytes, mimetype) or None on failure.
    """
    try:
        # WAHA builds media URLs using WHATSAPP_API_HOSTNAME which can
        # produce malformed URLs like http://http://host:8000:3000/api/files/...
        # We extract the /api/... path and prepend WAHA_API_URL.
        api_idx = url.find("/api/")
        if api_idx != -1:
            path = url[api_idx:]
        else:
            # Last resort: take everything after the third slash
            from urllib.parse import urlparse
            path = urlparse(url).path or "/"
        resolved_url = f"{WAHA_API_URL.rstrip('/')}{path}"
        logger.info("Media URL resolved: %s -> %s", url, resolved_url)

        headers: dict[str, str] = {}
        if WAHA_API_KEY:
            headers["X-Api-Key"] = WAHA_API_KEY
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(resolved_url, headers=headers)
            if response.status_code != 200:
                logger.error("Media URL download failed: %s %s", response.status_code, response.text)
                return None
            mimetype = response.headers.get("content-type", "application/octet-stream")
            return response.content, mimetype
    except Exception:
        logger.exception("Error downloading media from URL %s", url)
        return None


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
