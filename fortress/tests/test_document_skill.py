"""Unit tests for DocumentSkill — save, list, verify, dual registration."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from src.models.schema import Document, FamilyMember
from src.prompts.personality import TEMPLATES
from src.skills.base_skill import Command, Result
from src.skills.document_skill import DocumentSkill


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _member(**overrides) -> MagicMock:
    m = MagicMock(spec=FamilyMember)
    m.id = overrides.get("id", uuid.uuid4())
    m.name = overrides.get("name", "Test Parent")
    m.phone = overrides.get("phone", "+972501234567")
    m.role = overrides.get("role", "parent")
    m.is_active = True
    return m


def _document(**overrides) -> MagicMock:
    d = MagicMock(spec=Document)
    d.id = overrides.get("id", uuid.uuid4())
    d.original_filename = overrides.get("original_filename", "invoice.pdf")
    d.doc_type = overrides.get("doc_type", "document")
    d.created_at = overrides.get("created_at", datetime.now(timezone.utc))
    d.uploaded_by = overrides.get("uploaded_by", uuid.uuid4())
    return d


# ---------------------------------------------------------------------------
# Structure tests
# ---------------------------------------------------------------------------

class TestDocumentSkillStructure:
    def test_name(self):
        assert DocumentSkill().name == "document"

    def test_description_is_hebrew(self):
        desc = DocumentSkill().description
        assert "מסמכים" in desc

    def test_commands_count(self):
        # Only "list" command — save is triggered by media detection, not regex
        assert len(DocumentSkill().commands) == 1

    def test_commands_list_action(self):
        skill = DocumentSkill()
        _, action = skill.commands[0]
        assert action == "list"

    def test_get_help_returns_string(self):
        help_text = DocumentSkill().get_help()
        assert isinstance(help_text, str)
        assert len(help_text) > 0


# ---------------------------------------------------------------------------
# _save
# ---------------------------------------------------------------------------

class TestSave:
    @patch("src.skills.document_skill.documents.process_document", new_callable=AsyncMock)
    @patch("src.skills.document_skill.check_perm", return_value=None)
    def test_save_happy_path(self, _perm, mock_process, mock_db: MagicMock):
        doc = _document(original_filename="receipt.jpg")
        mock_process.return_value = doc

        skill = DocumentSkill()
        member = _member()
        cmd = Command(skill="document", action="save", params={"file_path": "/tmp/receipt.jpg"})
        result = skill.execute(mock_db, member, cmd)

        assert result.success
        assert result.entity_type == "document"
        assert result.entity_id == doc.id
        assert result.action == "saved"

    @patch("src.skills.document_skill.documents.process_document", new_callable=AsyncMock)
    @patch("src.skills.document_skill.check_perm", return_value=None)
    def test_save_calls_process_document_with_correct_args(self, _perm, mock_process, mock_db: MagicMock):
        doc = _document()
        mock_process.return_value = doc

        skill = DocumentSkill()
        member = _member()
        cmd = Command(skill="document", action="save", params={"file_path": "/tmp/doc.pdf"})
        skill.execute(mock_db, member, cmd)

        mock_process.assert_called_once_with(mock_db, "/tmp/doc.pdf", member.id, "whatsapp")

    @patch("src.skills.document_skill.documents.process_document", new_callable=AsyncMock)
    @patch("src.skills.document_skill.check_perm", return_value=None)
    def test_save_uses_template(self, _perm, mock_process, mock_db: MagicMock):
        doc = _document(original_filename="scan.pdf")
        mock_process.return_value = doc

        skill = DocumentSkill()
        member = _member()
        cmd = Command(skill="document", action="save", params={"file_path": "/tmp/scan.pdf"})
        result = skill.execute(mock_db, member, cmd)

        assert "scan.pdf" in result.message
        assert "✅" in result.message

    @patch("src.skills.document_skill.check_perm")
    def test_save_permission_denied(self, mock_perm, mock_db: MagicMock):
        mock_perm.return_value = Result(success=False, message=TEMPLATES["permission_denied"])

        skill = DocumentSkill()
        member = _member()
        cmd = Command(skill="document", action="save", params={"file_path": "/tmp/doc.pdf"})
        result = skill.execute(mock_db, member, cmd)

        assert not result.success
        assert TEMPLATES["permission_denied"] in result.message


# ---------------------------------------------------------------------------
# _list
# ---------------------------------------------------------------------------

class TestList:
    @patch("src.skills.document_skill.check_perm", return_value=None)
    def test_list_with_documents(self, _perm, mock_db: MagicMock):
        d1 = _document(original_filename="invoice.pdf", doc_type="document")
        d2 = _document(original_filename="photo.jpg", doc_type="image")
        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [d1, d2]

        skill = DocumentSkill()
        member = _member()
        cmd = Command(skill="document", action="list", params={})
        result = skill.execute(mock_db, member, cmd)

        assert result.success
        assert "invoice.pdf" in result.message
        assert "photo.jpg" in result.message

    @patch("src.skills.document_skill.check_perm", return_value=None)
    def test_list_empty_returns_template(self, _perm, mock_db: MagicMock):
        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

        skill = DocumentSkill()
        member = _member()
        cmd = Command(skill="document", action="list", params={})
        result = skill.execute(mock_db, member, cmd)

        assert result.success
        assert result.message == TEMPLATES["document_list_empty"]

    @patch("src.skills.document_skill.check_perm")
    def test_list_permission_denied(self, mock_perm, mock_db: MagicMock):
        mock_perm.return_value = Result(success=False, message=TEMPLATES["permission_denied"])

        skill = DocumentSkill()
        member = _member()
        cmd = Command(skill="document", action="list", params={})
        result = skill.execute(mock_db, member, cmd)

        assert not result.success
        assert TEMPLATES["permission_denied"] in result.message


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------

class TestVerify:
    def test_verify_saved_document_exists(self, mock_db: MagicMock):
        doc_id = uuid.uuid4()
        mock_doc = _document(id=doc_id)
        mock_db.query.return_value.filter.return_value.first.return_value = mock_doc

        skill = DocumentSkill()
        result = Result(
            success=True, message="ok",
            entity_type="document", entity_id=doc_id, action="saved",
        )
        assert skill.verify(mock_db, result) is True

    def test_verify_not_found_returns_false(self, mock_db: MagicMock):
        doc_id = uuid.uuid4()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        skill = DocumentSkill()
        result = Result(
            success=True, message="ok",
            entity_type="document", entity_id=doc_id, action="saved",
        )
        assert skill.verify(mock_db, result) is False

    def test_verify_no_entity_id_returns_true(self, mock_db: MagicMock):
        skill = DocumentSkill()
        result = Result(success=True, message="ok")
        assert skill.verify(mock_db, result) is True


# ---------------------------------------------------------------------------
# Dual registration
# ---------------------------------------------------------------------------

class TestDualRegistration:
    def test_media_and_document_are_same_object(self):
        from src.skills.registry import registry

        doc_skill = registry.get("document")
        media_skill = registry.get("media")
        assert doc_skill is media_skill
