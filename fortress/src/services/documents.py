"""Fortress 2.0 document service — document ingestion and processing."""

import logging
import os
import shutil
import uuid as uuid_mod
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from src.config import STORAGE_PATH
from src.models.schema import Document

logger = logging.getLogger(__name__)

_EXTENSION_MAP: dict[str, str] = {
    ".pdf": "document",
    ".doc": "document",
    ".docx": "document",
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
    ".heic": "image",
    ".xls": "spreadsheet",
    ".xlsx": "spreadsheet",
}


def _infer_doc_type(filename: str) -> str:
    """Infer document type from file extension."""
    _, ext = os.path.splitext(filename)
    return _EXTENSION_MAP.get(ext.lower(), "other")


async def process_document(
    db: Session,
    file_path: str,
    uploaded_by: UUID,
    source: str,
) -> Document:
    """Process and store a document with metadata.

    Extracts original_filename, infers doc_type from extension,
    creates year/month storage directories, copies the file,
    and saves a Document record with all metadata populated.
    """
    original_filename = os.path.basename(file_path)
    doc_type = _infer_doc_type(original_filename)

    now = datetime.now(timezone.utc)
    unique_id = uuid_mod.uuid4().hex[:8]
    storage_dir = os.path.join(STORAGE_PATH, str(now.year), f"{now.month:02d}")
    os.makedirs(storage_dir, exist_ok=True)

    storage_filename = f"{unique_id}_{original_filename}"
    storage_path = os.path.join(storage_dir, storage_filename)

    shutil.copy2(file_path, storage_path)

    doc = Document(
        file_path=storage_path,
        original_filename=original_filename,
        doc_type=doc_type,
        uploaded_by=uploaded_by,
        source=source,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc
