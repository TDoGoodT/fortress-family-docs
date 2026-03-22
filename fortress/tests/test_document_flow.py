"""Unit tests for the document flow — process_document, handlers, and intent."""

import os
import re
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from src.models.schema import Document, FamilyMember
from src.prompts.personality import TEMPLATES
from src.services.documents import _infer_doc_type


# ── _infer_doc_type ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("invoice.pdf", "document"),
        ("report.doc", "document"),
        ("report.docx", "document"),
        ("photo.jpg", "image"),
        ("photo.jpeg", "image"),
        ("photo.png", "image"),
        ("photo.heic", "image"),
        ("data.xls", "spreadsheet"),
        ("data.xlsx", "spreadsheet"),
        ("archive.zip", "other"),
        ("readme.txt", "other"),
        ("noext", "other"),
    ],
)
def test_infer_doc_type(filename: str, expected: str) -> None:
    assert _infer_doc_type(filename) == expected


# ── process_document ─────────────────────────────────────────────


@pytest.mark.asyncio
@patch("src.services.documents.shutil.copy2")
@patch("src.services.documents.os.makedirs")
async def test_process_document_creates_record_with_metadata(mock_makedirs, mock_copy2) -> None:
    """process_document should create a Document with correct metadata."""
    db = MagicMock(spec=Session)
    member_id = uuid4()

    from src.services.documents import process_document

    doc = await process_document(db, "/tmp/uploads/invoice.pdf", member_id, "whatsapp")

    db.add.assert_called_once()
    added_doc = db.add.call_args[0][0]
    assert added_doc.original_filename == "invoice.pdf"
    assert added_doc.doc_type == "document"
    assert added_doc.source == "whatsapp"
    assert added_doc.uploaded_by == member_id
    assert "invoice.pdf" in added_doc.file_path


@pytest.mark.asyncio
@patch("src.services.documents.shutil.copy2")
@patch("src.services.documents.os.makedirs")
async def test_process_document_creates_storage_directories(mock_makedirs, mock_copy2) -> None:
    """process_document should create year/month directories."""
    db = MagicMock(spec=Session)

    from src.services.documents import process_document

    await process_document(db, "/tmp/photo.jpg", uuid4(), "whatsapp")

    mock_makedirs.assert_called_once()
    call_args = mock_makedirs.call_args
    storage_dir = call_args[0][0]
    # Should contain year/month pattern
    assert re.search(r"\d{4}[\\/]\d{2}$", storage_dir)
    assert call_args[1].get("exist_ok") is True


@pytest.mark.asyncio
@patch("src.services.documents.shutil.copy2")
@patch("src.services.documents.os.makedirs")
async def test_process_document_storage_path_format(mock_makedirs, mock_copy2) -> None:
    """Storage path should match {STORAGE_PATH}/{year}/{month}/{uuid}_{filename}."""
    db = MagicMock(spec=Session)

    from src.services.documents import process_document

    await process_document(db, "/tmp/report.xlsx", uuid4(), "whatsapp")

    added_doc = db.add.call_args[0][0]
    # Path should end with {hex}_{filename}
    basename = os.path.basename(added_doc.file_path)
    assert re.match(r"[a-f0-9]+_report\.xlsx$", basename)


@pytest.mark.asyncio
@patch("src.services.documents.shutil.copy2")
@patch("src.services.documents.os.makedirs")
async def test_process_document_copies_file(mock_makedirs, mock_copy2) -> None:
    """process_document should copy the source file to storage."""
    db = MagicMock(spec=Session)

    from src.services.documents import process_document

    await process_document(db, "/tmp/file.pdf", uuid4(), "whatsapp")

    mock_copy2.assert_called_once()
    src_path = mock_copy2.call_args[0][0]
    assert src_path == "/tmp/file.pdf"



# ── _handle_list_documents ───────────────────────────────────────


def _make_mock_doc(filename: str, doc_type: str, created_at: str = "2026-03-01") -> MagicMock:
    """Build a mock Document object."""
    doc = MagicMock(spec=Document)
    doc.original_filename = filename
    doc.doc_type = doc_type
    doc.created_at = created_at
    return doc


@pytest.mark.asyncio
async def test_handle_list_documents_returns_formatted_list() -> None:
    """_handle_list_documents should return personality-formatted list."""
    from src.services.workflow_engine import _handle_list_documents

    db = MagicMock(spec=Session)
    member = MagicMock(spec=FamilyMember)
    member.id = uuid4()

    mock_docs = [
        _make_mock_doc("invoice.pdf", "document"),
        _make_mock_doc("photo.jpg", "image"),
    ]
    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.order_by.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.all.return_value = mock_docs
    db.query.return_value = mock_query

    result = await _handle_list_documents(db, member, "", MagicMock(), None, "list_documents")

    assert "invoice.pdf" in result
    assert "photo.jpg" in result
    assert TEMPLATES["document_list_header"].strip() in result


@pytest.mark.asyncio
async def test_handle_list_documents_empty() -> None:
    """_handle_list_documents should return empty template when no docs."""
    from src.services.workflow_engine import _handle_list_documents

    db = MagicMock(spec=Session)
    member = MagicMock(spec=FamilyMember)
    member.id = uuid4()

    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.order_by.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.all.return_value = []
    db.query.return_value = mock_query

    result = await _handle_list_documents(db, member, "", MagicMock(), None, "list_documents")

    assert result == TEMPLATES["document_list_empty"]


# ── _handle_upload_document ──────────────────────────────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.log_action")
@patch("src.services.workflow_engine.process_document", new_callable=AsyncMock)
async def test_handle_upload_document_success(mock_process, mock_log) -> None:
    """Successful upload should return personality template confirmation."""
    from src.services.workflow_engine import _handle_upload_document

    mock_doc = MagicMock()
    mock_doc.original_filename = "invoice.pdf"
    mock_process.return_value = mock_doc

    db = MagicMock(spec=Session)
    member = MagicMock(spec=FamilyMember)
    member.id = uuid4()
    member.phone = "+972501234567"

    result = await _handle_upload_document(
        db, member, "", MagicMock(), "/tmp/invoice.pdf", "upload_document"
    )

    assert "invoice.pdf" in result
    assert "✅" in result


@pytest.mark.asyncio
@patch("src.services.workflow_engine.log_action")
@patch("src.services.workflow_engine.process_document", new_callable=AsyncMock)
async def test_handle_upload_document_failure(mock_process, mock_log) -> None:
    """Failed upload should return error_fallback template."""
    from src.services.workflow_engine import _handle_upload_document

    mock_process.side_effect = Exception("disk full")

    db = MagicMock(spec=Session)
    member = MagicMock(spec=FamilyMember)
    member.id = uuid4()
    member.phone = "+972501234567"

    result = await _handle_upload_document(
        db, member, "", MagicMock(), "/tmp/invoice.pdf", "upload_document"
    )

    assert result == TEMPLATES["error_fallback"]



# ── Intent classification ────────────────────────────────────────


from src.services.intent_detector import detect_intent


def test_intent_mah_hamismachim_sheli() -> None:
    """'מה המסמכים שלי?' should classify as list_documents."""
    assert detect_intent("מה המסמכים שלי?", False) == "list_documents"


def test_intent_tareh_mismachim() -> None:
    """'תראה מסמכים' should classify as list_documents."""
    assert detect_intent("תראה מסמכים", False) == "list_documents"


def test_intent_mismachim_standalone() -> None:
    """'מסמכים' standalone should classify as list_documents."""
    assert detect_intent("מסמכים", False) == "list_documents"
