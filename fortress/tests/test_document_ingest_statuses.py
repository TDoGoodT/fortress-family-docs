from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from src.models.schema import Document
from src.skills.document_skill import DocumentSkill, _process_document_with_retry


class IntegrityError(Exception):
    """Test-local IntegrityError shim (name-based retry check)."""


def _make_member() -> MagicMock:
    member = MagicMock()
    member.id = uuid.uuid4()
    member.role = "parent"
    return member


def _make_doc(*, duplicate: bool = False) -> MagicMock:
    doc = MagicMock(spec=Document)
    doc.id = uuid.uuid4()
    doc.original_filename = "test.pdf"
    doc.display_name = "test"
    doc._is_duplicate = duplicate
    return doc


def test_document_save_media_returns_ingested_status() -> None:
    skill = DocumentSkill()
    member = _make_member()
    doc = _make_doc(duplicate=False)

    with patch("src.skills.document_skill.check_perm", return_value=None), patch(
        "src.skills.document_skill._process_document_with_retry", return_value=doc
    ), patch("src.skills.document_skill.update_state"):
        result = skill._save(MagicMock(), member, {"media_file_path": "/tmp/test.pdf"})

    assert result.success is True
    assert result.message == "received\ningested"
    assert result.action == "saved"


def test_document_save_media_returns_duplicate_status() -> None:
    skill = DocumentSkill()
    member = _make_member()
    doc = _make_doc(duplicate=True)

    with patch("src.skills.document_skill.check_perm", return_value=None), patch(
        "src.skills.document_skill._process_document_with_retry", return_value=doc
    ), patch("src.skills.document_skill.update_state"):
        result = skill._save(MagicMock(), member, {"media_file_path": "/tmp/test.pdf"})

    assert result.success is True
    assert result.action == "duplicate"
    assert result.message == "received\nduplicate\nDocument already exists in the library"


def test_document_save_media_returns_failed_status_on_error() -> None:
    skill = DocumentSkill()
    member = _make_member()

    with patch("src.skills.document_skill.check_perm", return_value=None), patch(
        "src.skills.document_skill._process_document_with_retry", side_effect=ValueError("boom")
    ):
        result = skill._save(MagicMock(), member, {"media_file_path": "/tmp/test.pdf"})

    assert result.success is False
    assert result.action == "failed"
    assert result.message == "received\nfailed\nPipeline error: ValueError"


def test_process_document_with_retry_retries_once_for_integrity_error() -> None:
    doc = _make_doc()
    with patch(
        "src.skills.document_skill._run_process_document_in_thread",
        side_effect=[IntegrityError("constraint"), doc],
    ) as mock_run:
        out = _process_document_with_retry(MagicMock(), "/tmp/test.pdf", uuid.uuid4())

    assert out is doc
    assert mock_run.call_count == 2
