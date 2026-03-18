"""Fortress 2.0 document service — document ingestion and processing."""

from uuid import UUID

from sqlalchemy.orm import Session

from src.models.schema import Document


async def process_document(
    db: Session,
    file_path: str,
    uploaded_by: UUID,
    source: str,
) -> Document:
    """Create a minimal document record.

    AI/OCR enrichment fields (ai_summary, raw_text, vendor, etc.) are left
    as None and will be populated by future processing stages.
    """
    doc = Document(
        file_path=file_path,
        uploaded_by=uploaded_by,
        source=source,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc
