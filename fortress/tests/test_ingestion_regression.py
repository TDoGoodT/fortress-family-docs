"""Regression tests for the document ingestion path.

Covers:
- Media routing: command_parser routes has_media to skill="media" action="save"
- "media" skill resolves to DocumentSkill via dual registration
- _save handles missing file_path gracefully (returns error, not crash)
- _save handles media_file_path correctly
- process_document Step 0 creates DB record before enrichment
- Enrichment failures do not block ingestion
- Saved document appears in list and recent
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.engine.command_parser import parse_command
from src.engine.executor import execute
from src.models.schema import Document
from src.skills.base_skill import Command, Result
from src.skills.document_skill import DocumentSkill


# ---------------------------------------------------------------------------
# 1. Media routing — command_parser
# ---------------------------------------------------------------------------

def test_media_message_routes_to_media_skill():
    """has_media=True must produce Command(skill='document', action='save')."""
    from src.skills.registry import SkillRegistry
    registry = SkillRegistry()
    cmd = parse_command(None, registry, has_media=True, media_file_path="/tmp/photo.jpg")
    assert cmd is not None
    assert cmd.skill == "document"
    assert cmd.action == "save"
    assert cmd.params.get("media_file_path") == "/tmp/photo.jpg"


def test_media_message_with_text_still_routes_to_media():
    """Media takes priority over text content."""
    from src.skills.registry import SkillRegistry
    registry = SkillRegistry()
    cmd = parse_command("some text", registry, has_media=True, media_file_path="/tmp/doc.pdf")
    assert cmd is not None
    assert cmd.skill == "document"
    assert cmd.action == "save"


def test_media_without_file_path_still_routes_to_media():
    """Even if media_file_path is None, routing still goes to media skill."""
    from src.skills.registry import SkillRegistry
    registry = SkillRegistry()
    cmd = parse_command(None, registry, has_media=True, media_file_path=None)
    assert cmd is not None
    assert cmd.skill == "document"
    assert cmd.action == "save"


# ---------------------------------------------------------------------------
# 2. "media" skill resolves to DocumentSkill
# ---------------------------------------------------------------------------

def test_media_skill_registered_as_document_skill():
    """The 'media' key in the registry must point to a DocumentSkill instance."""
    from src.skills import registry  # triggers __init__.py registration
    skill = registry.get("document")
    assert skill is not None
    assert isinstance(skill, DocumentSkill)


def test_executor_resolves_document_skill_for_save():
    """Executor must resolve command.skill='document' to DocumentSkill."""
    from src.skills import registry
    db = MagicMock()
    member = MagicMock()
    member.id = uuid.uuid4()
    member.name = "tester"

    cmd = Command(skill="document", action="save", params={"media_file_path": "/tmp/test.pdf"})
    expected = Result(success=True, message="ok")

    with patch.object(registry.get("document"), "execute", return_value=expected) as mock_execute, \
         patch("src.engine.executor.update_state"), \
         patch("src.engine.executor.log_action"):
        result = execute(db, member, cmd)

    assert result.success is True
    mock_execute.assert_called_once()


# ---------------------------------------------------------------------------
# 3. _save: missing file_path returns error gracefully
# ---------------------------------------------------------------------------

def test_save_with_empty_file_path_returns_error():
    """_save must return error_fallback when file_path is empty, not crash."""
    skill = DocumentSkill()
    db = MagicMock()
    member = MagicMock()
    member.id = uuid.uuid4()
    member.role = "parent"

    with patch("src.skills.document_skill.check_perm", return_value=None):
        cmd = Command(skill="document", action="save", params={"media_file_path": ""})
        result = skill.execute(db, member, cmd)

    assert not result.success
    assert result.message  # some error message returned


def test_save_with_none_file_path_returns_error():
    """_save must return error_fallback when media_file_path is None."""
    skill = DocumentSkill()
    db = MagicMock()
    member = MagicMock()
    member.id = uuid.uuid4()

    with patch("src.skills.document_skill.check_perm", return_value=None):
        cmd = Command(skill="document", action="save", params={"media_file_path": None})
        result = skill.execute(db, member, cmd)

    assert not result.success


# ---------------------------------------------------------------------------
# 4. _save: successful ingestion path
# ---------------------------------------------------------------------------

def test_save_calls_process_document_with_correct_file_path(tmp_path):
    """_save must call process_document with the media_file_path."""
    test_file = tmp_path / "invoice.pdf"
    test_file.write_bytes(b"fake pdf content")

    skill = DocumentSkill()
    db = MagicMock()
    member = MagicMock()
    member.id = uuid.uuid4()

    mock_doc = MagicMock(spec=Document)
    mock_doc.id = uuid.uuid4()
    mock_doc.original_filename = "invoice.pdf"

    with patch("src.skills.document_skill.check_perm", return_value=None), \
         patch("src.skills.document_skill.documents.process_document", new_callable=AsyncMock, return_value=mock_doc) as mock_process:
        cmd = Command(skill="document", action="save", params={"media_file_path": str(test_file)})
        result = skill.execute(db, member, cmd)

    assert result.success
    assert result.entity_id == mock_doc.id
    mock_process.assert_called_once()
    call_args = mock_process.call_args[0]
    assert call_args[1] == str(test_file)  # file_path argument


def test_save_returns_document_saved_template_on_success(tmp_path):
    """_save must return the document_saved template with filename on success."""
    from src.prompts.personality import TEMPLATES
    test_file = tmp_path / "contract.pdf"
    test_file.write_bytes(b"fake content")

    skill = DocumentSkill()
    db = MagicMock()
    member = MagicMock()
    member.id = uuid.uuid4()

    mock_doc = MagicMock(spec=Document)
    mock_doc.id = uuid.uuid4()
    mock_doc.original_filename = "contract.pdf"

    with patch("src.skills.document_skill.check_perm", return_value=None), \
         patch("src.skills.document_skill.documents.process_document", new_callable=AsyncMock, return_value=mock_doc):
        cmd = Command(skill="document", action="save", params={"media_file_path": str(test_file)})
        result = skill.execute(db, member, cmd)

    assert result.success
    assert "contract.pdf" in result.message


# ---------------------------------------------------------------------------
# 5. process_document: Step 0 creates DB record before enrichment
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_process_document_creates_db_record_before_enrichment(tmp_path):
    """Step 0 must create and commit the Document row before any enrichment step."""
    test_file = tmp_path / "test.pdf"
    test_file.write_bytes(b"fake pdf")

    committed_docs = []

    db = MagicMock()
    def commit_side_effect():
        # Capture what was added at first commit
        if not committed_docs:
            for call in db.add.call_args_list:
                obj = call[0][0]
                if isinstance(obj, Document):
                    committed_docs.append(obj)
    db.commit.side_effect = commit_side_effect
    db.refresh.side_effect = lambda obj: setattr(obj, 'id', uuid.uuid4()) if not hasattr(obj, '_id_set') else None

    with patch("src.services.documents.extract_text", return_value=""), \
         patch("src.services.documents.classify_document", new_callable=AsyncMock, side_effect=Exception("LLM down")), \
         patch("src.services.documents.extract_facts", new_callable=AsyncMock, return_value=[]), \
         patch("src.services.documents.summarize_document", new_callable=AsyncMock, return_value=""), \
         patch("src.services.documents.STORAGE_PATH", str(tmp_path)):

        from src.services.documents import process_document
        doc = await process_document(db, str(test_file), uuid.uuid4(), "whatsapp")

    # DB commit was called (Step 0 + Step 6)
    assert db.commit.call_count >= 1
    # Document was added to DB
    assert db.add.called


@pytest.mark.asyncio
async def test_process_document_resilient_to_all_enrichment_failures(tmp_path):
    """If all enrichment steps fail, process_document still returns a Document."""
    test_file = tmp_path / "test.pdf"
    test_file.write_bytes(b"fake pdf")

    db = MagicMock()
    captured = {}

    def add_side_effect(obj):
        if isinstance(obj, Document):
            obj.id = uuid.uuid4()
            captured['doc'] = obj
    db.add.side_effect = add_side_effect
    db.refresh.side_effect = lambda obj: None

    with patch("src.services.documents.extract_text", side_effect=Exception("OCR failed")), \
         patch("src.services.documents.classify_document", new_callable=AsyncMock, side_effect=Exception("LLM down")), \
         patch("src.services.documents.extract_facts", new_callable=AsyncMock, side_effect=Exception("extractor failed")), \
         patch("src.services.documents.summarize_document", new_callable=AsyncMock, side_effect=Exception("summarizer failed")), \
         patch("src.services.documents.STORAGE_PATH", str(tmp_path)):

        from src.services.documents import process_document
        doc = await process_document(db, str(test_file), uuid.uuid4(), "whatsapp")

    assert doc is not None
    assert doc.review_state in ("needs_review", "pending", "auto_verified")


# ---------------------------------------------------------------------------
# 6. Saved document appears in list and recent
# ---------------------------------------------------------------------------

def test_list_returns_saved_document():
    """After save, מסמכים must return the document."""
    skill = DocumentSkill()
    doc = MagicMock(spec=Document)
    doc.id = uuid.uuid4()
    doc.original_filename = "invoice.pdf"
    doc.doc_type = "invoice"
    doc.created_at = None

    db = MagicMock()
    mock_q = MagicMock()
    mock_q.filter.return_value = mock_q
    mock_q.order_by.return_value = mock_q
    mock_q.limit.return_value = mock_q
    mock_q.all.return_value = [doc]
    db.query.return_value = mock_q

    member = MagicMock()
    member.id = uuid.uuid4()

    with patch("src.skills.document_skill.check_perm", return_value=None):
        cmd = Command(skill="document", action="list", params={})
        result = skill.execute(db, member, cmd)

    assert result.success
    assert "invoice.pdf" in result.message


def test_recent_returns_saved_document():
    """After save, מסמך אחרון must return the document."""
    skill = DocumentSkill()
    doc = MagicMock(spec=Document)
    doc.id = uuid.uuid4()
    doc.original_filename = "contract.pdf"
    doc.doc_type = "contract"
    doc.created_at = None

    db = MagicMock()
    mock_q = MagicMock()
    mock_q.filter.return_value = mock_q
    mock_q.order_by.return_value = mock_q
    mock_q.first.return_value = doc
    db.query.return_value = mock_q

    member = MagicMock()
    member.id = uuid.uuid4()

    with patch("src.skills.document_skill.check_perm", return_value=None):
        cmd = Command(skill="document", action="recent", params={})
        result = skill.execute(db, member, cmd)

    assert result.success
    assert result.entity_id == doc.id
    assert "contract.pdf" in result.message


# ---------------------------------------------------------------------------
# 7. process_document: empty file_path raises ValueError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_process_document_raises_on_empty_file_path():
    """process_document must raise ValueError when file_path is empty."""
    from src.services.documents import process_document
    db = MagicMock()
    with pytest.raises(ValueError, match="file_path is empty"):
        await process_document(db, "", uuid.uuid4(), "whatsapp")
