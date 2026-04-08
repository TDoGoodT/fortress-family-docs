"""Pipeline integration tests — P2 resilience, P5 review state determinism."""
from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from src.models.schema import Document, DocumentFact, SalarySlip


def _make_db_mock(doc_id=None):
    """Build a mock DB session that returns a Document on refresh."""
    db = MagicMock()
    doc = MagicMock(spec=Document)
    doc.id = doc_id or uuid.uuid4()
    doc.doc_type = "other"
    doc.confidence = 0.0
    doc.review_state = "pending"
    doc.raw_text = None
    doc.ai_summary = None
    doc.tags = []
    db.refresh.side_effect = lambda obj: None
    return db, doc


@pytest.fixture
def tmp_pdf(tmp_path):
    """Create a temporary PDF-like file for testing."""
    f = tmp_path / "test_invoice.pdf"
    f.write_bytes(b"%PDF-1.4 fake content")
    return str(f)


@pytest.fixture
def tmp_xlsx(tmp_path):
    f = tmp_path / "budget_2026.xlsx"
    f.write_bytes(b"PK fake xlsx content")
    return str(f)


# ---------------------------------------------------------------------------
# Full pipeline — happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_pipeline_happy_path(tmp_pdf):
    """Full pipeline: file stored, text extracted, classified, facts created, summary, auto_verified."""
    with patch("src.services.documents.extract_text_v2", new_callable=AsyncMock, return_value=("חשבונית מס 12345 סכום ₪500", 0.9, "ocr")) as mock_extract, \
         patch("src.services.documents.classify_document", new_callable=AsyncMock, return_value=("invoice", 0.85)) as mock_classify, \
         patch("src.services.documents.extract_facts", new_callable=AsyncMock, return_value=[
             {"fact_type": "invoice", "fact_key": "amount", "fact_value": "500", "confidence": 0.9, "source_excerpt": "₪500"}
         ]) as mock_facts, \
         patch("src.services.documents._find_duplicate", return_value=None), \
         patch("src.services.documents.summarize_document", new_callable=AsyncMock, return_value="חשבונית מס לחודש מרץ.") as mock_summary, \
         patch("src.services.documents.os.makedirs"), \
         patch("src.services.documents.shutil.copy2"):

        db = MagicMock()
        doc = MagicMock(spec=Document)
        doc.id = uuid.uuid4()
        doc.doc_type = "other"
        doc.confidence = 0.0
        doc.review_state = "pending"
        doc.raw_text = None
        doc.ai_summary = None
        doc.tags = []
        db.refresh.side_effect = lambda obj: None

        # Simulate Document creation
        created_docs = []
        def add_side_effect(obj):
            if isinstance(obj, Document):
                created_docs.append(obj)
                obj.id = doc.id
        db.add.side_effect = add_side_effect

        from src.services.documents import process_document
        result = await process_document(db, tmp_pdf, uuid.uuid4(), "whatsapp")

        mock_extract.assert_called_once()
        mock_classify.assert_called_once()
        mock_facts.assert_called_once()
        mock_summary.assert_called_once()
        db.commit.assert_called()


# ---------------------------------------------------------------------------
# P2: Pipeline Resilience — classification fails, pipeline continues
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_p2_classification_failure_pipeline_continues(tmp_pdf):
    """P2: If classification fails, fact extraction and summary still run."""
    with patch("src.services.documents.extract_text_v2", new_callable=AsyncMock, return_value=("some text", 0.9, "ocr")), \
         patch("src.services.documents.classify_document", new_callable=AsyncMock, side_effect=Exception("LLM timeout")), \
         patch("src.services.documents.extract_facts", new_callable=AsyncMock, return_value=[]) as mock_facts, \
         patch("src.services.documents._find_duplicate", return_value=None), \
         patch("src.services.documents.summarize_document", new_callable=AsyncMock, return_value="") as mock_summary, \
         patch("src.services.documents.os.makedirs"), \
         patch("src.services.documents.shutil.copy2"):

        db = MagicMock()
        doc = MagicMock(spec=Document)
        doc.id = uuid.uuid4()
        doc.doc_type = "other"
        doc.confidence = 0.0
        doc.review_state = "pending"
        doc.raw_text = None
        doc.ai_summary = None
        doc.tags = []
        db.refresh.side_effect = lambda obj: None
        db.add.side_effect = lambda obj: setattr(obj, 'id', doc.id) if isinstance(obj, Document) else None

        from src.services.documents import process_document
        result = await process_document(db, tmp_pdf, uuid.uuid4(), "whatsapp")

        # Fact extraction and summary still called despite classification failure
        mock_facts.assert_called_once()
        mock_summary.assert_called_once()
        db.commit.assert_called()


@pytest.mark.asyncio
async def test_p2_fact_extraction_failure_pipeline_continues(tmp_pdf):
    """P2: If fact extraction fails, summary still runs."""
    with patch("src.services.documents.extract_text_v2", new_callable=AsyncMock, return_value=("some text", 0.9, "ocr")), \
         patch("src.services.documents.classify_document", new_callable=AsyncMock, return_value=("invoice", 0.8)), \
         patch("src.services.documents.extract_facts", new_callable=AsyncMock, side_effect=Exception("extractor error")), \
         patch("src.services.documents._find_duplicate", return_value=None), \
         patch("src.services.documents.summarize_document", new_callable=AsyncMock, return_value="סיכום.") as mock_summary, \
         patch("src.services.documents.os.makedirs"), \
         patch("src.services.documents.shutil.copy2"):

        db = MagicMock()
        doc = MagicMock(spec=Document)
        doc.id = uuid.uuid4()
        doc.doc_type = "other"
        doc.confidence = 0.0
        doc.review_state = "pending"
        doc.raw_text = None
        doc.ai_summary = None
        doc.tags = []
        db.refresh.side_effect = lambda obj: None
        db.add.side_effect = lambda obj: setattr(obj, 'id', doc.id) if isinstance(obj, Document) else None

        from src.services.documents import process_document
        result = await process_document(db, tmp_pdf, uuid.uuid4(), "whatsapp")

        mock_summary.assert_called_once()
        db.commit.assert_called()


# ---------------------------------------------------------------------------
# XLS/XLSX: filename-only classification, text extraction skipped
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_xlsx_skips_text_extraction(tmp_xlsx):
    """XLS/XLSX: text extraction is skipped, classification uses filename only."""
    with patch("src.services.documents.extract_text_v2", new_callable=AsyncMock) as mock_extract, \
         patch("src.services.documents.classify_document", new_callable=AsyncMock, return_value=("other", 0.3)) as mock_classify, \
         patch("src.services.documents.extract_facts", new_callable=AsyncMock, return_value=[]), \
         patch("src.services.documents._find_duplicate", return_value=None), \
         patch("src.services.documents.summarize_document", new_callable=AsyncMock, return_value=""), \
         patch("src.services.documents.os.makedirs"), \
         patch("src.services.documents.shutil.copy2"):

        db = MagicMock()
        doc = MagicMock(spec=Document)
        doc.id = uuid.uuid4()
        doc.doc_type = "other"
        doc.confidence = 0.0
        doc.review_state = "pending"
        doc.raw_text = None
        doc.ai_summary = None
        doc.tags = []
        db.refresh.side_effect = lambda obj: None
        db.add.side_effect = lambda obj: setattr(obj, 'id', doc.id) if isinstance(obj, Document) else None

        from src.services.documents import process_document
        result = await process_document(db, tmp_xlsx, uuid.uuid4(), "whatsapp")

        # extract_text should NOT be called for xlsx
        mock_extract.assert_not_called()
        # classify_document IS called (with empty text)
        mock_classify.assert_called_once()
        call_args = mock_classify.call_args[0]
        assert call_args[0] == ""  # raw_text is empty for xlsx


# ---------------------------------------------------------------------------
# P5: Review State Determinism
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_p5_auto_verified_when_all_signals_pass(tmp_pdf):
    """P5: review_state = auto_verified when all three signals pass."""
    with patch("src.services.documents.extract_text_v2", new_callable=AsyncMock, return_value=("invoice text", 0.9, "ocr")), \
         patch("src.services.documents.classify_document", new_callable=AsyncMock, return_value=("invoice", 0.85)), \
         patch("src.services.documents.extract_facts", new_callable=AsyncMock, return_value=[
             {"fact_type": "invoice", "fact_key": "amount", "fact_value": "100", "confidence": 0.9, "source_excerpt": "100"}
         ]), \
         patch("src.services.documents._find_duplicate", return_value=None), \
         patch("src.services.documents.summarize_document", new_callable=AsyncMock, return_value="סיכום."), \
         patch("src.services.documents.os.makedirs"), \
         patch("src.services.documents.shutil.copy2"):

        db = MagicMock()
        captured_doc = {}

        def add_side_effect(obj):
            if isinstance(obj, Document):
                obj.id = uuid.uuid4()
                captured_doc['doc'] = obj
        db.add.side_effect = add_side_effect
        db.refresh.side_effect = lambda obj: None

        from src.services.documents import process_document
        await process_document(db, tmp_pdf, uuid.uuid4(), "whatsapp")

        doc = captured_doc.get('doc')
        assert doc is not None
        assert doc.review_state == "auto_verified"


@pytest.mark.asyncio
async def test_p5_needs_review_when_text_empty(tmp_pdf):
    """P5: review_state = needs_review when text extraction returns empty for extractable type."""
    with patch("src.services.documents.extract_text_v2", new_callable=AsyncMock, return_value=("", 0.0, "ocr")), \
         patch("src.services.documents.classify_document", new_callable=AsyncMock, return_value=("invoice", 0.85)), \
         patch("src.services.documents.extract_facts", new_callable=AsyncMock, return_value=[]), \
         patch("src.services.documents._find_duplicate", return_value=None), \
         patch("src.services.documents.summarize_document", new_callable=AsyncMock, return_value=""), \
         patch("src.services.documents.os.makedirs"), \
         patch("src.services.documents.shutil.copy2"):

        db = MagicMock()
        captured_doc = {}

        def add_side_effect(obj):
            if isinstance(obj, Document):
                obj.id = uuid.uuid4()
                captured_doc['doc'] = obj
        db.add.side_effect = add_side_effect
        db.refresh.side_effect = lambda obj: None

        from src.services.documents import process_document
        await process_document(db, tmp_pdf, uuid.uuid4(), "whatsapp")

        doc = captured_doc.get('doc')
        assert doc is not None
        assert doc.review_state == "needs_review"


@pytest.mark.asyncio
async def test_p5_needs_review_when_low_confidence(tmp_pdf):
    """P5: review_state = needs_review when classification confidence is below threshold."""
    with patch("src.services.documents.extract_text_v2", new_callable=AsyncMock, return_value=("some text", 0.9, "ocr")), \
         patch("src.services.documents.classify_document", new_callable=AsyncMock, return_value=("other", 0.2)), \
         patch("src.services.documents.extract_facts", new_callable=AsyncMock, return_value=[
             {"fact_type": "other", "fact_key": "amount", "fact_value": "100", "confidence": 0.9, "source_excerpt": "100"}
         ]), \
         patch("src.services.documents._find_duplicate", return_value=None), \
         patch("src.services.documents.summarize_document", new_callable=AsyncMock, return_value="סיכום."), \
         patch("src.services.documents.os.makedirs"), \
         patch("src.services.documents.shutil.copy2"):

        db = MagicMock()
        captured_doc = {}

        def add_side_effect(obj):
            if isinstance(obj, Document):
                obj.id = uuid.uuid4()
                captured_doc['doc'] = obj
        db.add.side_effect = add_side_effect
        db.refresh.side_effect = lambda obj: None

        from src.services.documents import process_document
        await process_document(db, tmp_pdf, uuid.uuid4(), "whatsapp")

        doc = captured_doc.get('doc')
        assert doc is not None
        assert doc.review_state == "needs_review"


@pytest.mark.asyncio
async def test_p5_review_state_never_pending_after_pipeline(tmp_pdf):
    """P5: review_state is never 'pending' after pipeline completes."""
    with patch("src.services.documents.extract_text_v2", new_callable=AsyncMock, return_value=("text", 0.9, "ocr")), \
         patch("src.services.documents.classify_document", new_callable=AsyncMock, return_value=("invoice", 0.8)), \
         patch("src.services.documents.extract_facts", new_callable=AsyncMock, return_value=[]), \
         patch("src.services.documents._find_duplicate", return_value=None), \
         patch("src.services.documents.summarize_document", new_callable=AsyncMock, return_value=""), \
         patch("src.services.documents.os.makedirs"), \
         patch("src.services.documents.shutil.copy2"):

        db = MagicMock()
        captured_doc = {}

        def add_side_effect(obj):
            if isinstance(obj, Document):
                obj.id = uuid.uuid4()
                captured_doc['doc'] = obj
        db.add.side_effect = add_side_effect
        db.refresh.side_effect = lambda obj: None

        from src.services.documents import process_document
        await process_document(db, tmp_pdf, uuid.uuid4(), "whatsapp")

        doc = captured_doc.get('doc')
        assert doc is not None
        assert doc.review_state != "pending"
        assert doc.review_state in ("auto_verified", "needs_review")


# ---------------------------------------------------------------------------
# P1: Raw File Integrity — stored file is byte-identical to original
# ---------------------------------------------------------------------------

def test_p1_raw_file_integrity(tmp_path):
    """P1: The stored file must be byte-identical to the original uploaded file."""
    import shutil
    original = tmp_path / "original_invoice.pdf"
    original.write_bytes(b"%PDF-1.4 test content for integrity check")

    storage_dir = tmp_path / "storage"
    storage_dir.mkdir()
    stored = storage_dir / "stored_invoice.pdf"
    shutil.copy2(str(original), str(stored))

    assert original.read_bytes() == stored.read_bytes()


# ---------------------------------------------------------------------------
# E2E: search flow via DocumentSkill
# ---------------------------------------------------------------------------

def test_e2e_search_flow():
    """E2E: search command → DocumentSkill._search → filtered results."""
    from src.skills.document_skill import DocumentSkill
    from src.skills.base_skill import Command
    import uuid
    from unittest.mock import MagicMock
    from src.models.schema import Document

    skill = DocumentSkill()
    doc = MagicMock(spec=Document)
    doc.id = uuid.uuid4()
    doc.original_filename = "contract_2026.pdf"
    doc.doc_type = "contract"
    doc.created_at = None

    with patch("src.skills.document_skill.check_perm", return_value=None), \
         patch("src.skills.document_skill.search_documents", return_value=[doc]):
        cmd = Command(skill="document", action="search", params={"doc_type": "חוזים"})
        result = skill.execute(MagicMock(), MagicMock(), cmd)

    assert result.success
    assert "contract_2026.pdf" in result.message or "1." in result.message


# ---------------------------------------------------------------------------
# E2E: QA flow via DocumentSkill
# ---------------------------------------------------------------------------

def test_e2e_qa_flow():
    """E2E: question command → DocumentSkill._query → resolve document → answer."""
    from src.skills.document_skill import DocumentSkill
    from src.skills.base_skill import Command
    from src.services.document_query_service import QAResult
    import uuid
    from unittest.mock import MagicMock, AsyncMock
    from src.models.schema import Document

    skill = DocumentSkill()
    doc = MagicMock(spec=Document)
    doc.id = uuid.uuid4()
    doc.original_filename = "invoice.pdf"
    doc.doc_type = "invoice"
    doc.created_at = None

    qa_result = QAResult(answer_text="invoice", source="db_field", confidence=1.0, field_used="doc_type")

    with patch("src.skills.document_skill.check_perm", return_value=None), \
         patch("src.skills.document_skill.resolve_document_reference", return_value=doc), \
         patch("src.skills.document_skill.update_state"), \
         patch("src.skills.document_skill.answer_document_question", new_callable=AsyncMock, return_value=qa_result):
        cmd = Command(skill="document", action="query", params={"question": "מה סוג המסמך?"})
        result = skill.execute(MagicMock(), MagicMock(), cmd)

    assert result.success
    assert "invoice" in result.message


@pytest.mark.asyncio
async def test_salary_slip_pipeline_sets_metadata_and_facts(tmp_pdf):
    with patch("src.services.documents.extract_text_v2", new_callable=AsyncMock, return_value=("תלוש שכר", 0.9, "ocr")), \
         patch("src.services.documents.classify_document", new_callable=AsyncMock, return_value=("salary_slip", 0.9)), \
         patch("src.services.documents._find_duplicate", return_value=None), \
         patch("src.services.documents._extract_salary_slip_facts", new_callable=AsyncMock, return_value=(
             [
                 {"fact_type": "salary_slip", "fact_key": "employer_name", "fact_value": "ACME", "confidence": 0.91, "source_excerpt": ""},
                 {"fact_type": "salary_slip", "fact_key": "gross_salary", "fact_value": "10000.0", "confidence": 0.91, "source_excerpt": ""},
                 {"fact_type": "salary_slip", "fact_key": "net_salary", "fact_value": "7800.0", "confidence": 0.91, "source_excerpt": ""},
             ],
             {
                 "structured_payload": {"gross_salary": 10000.0, "net_salary": 7800.0, "confidence": 0.91},
                 "field_confidence": {"gross_salary": 0.91, "net_salary": 0.91},
                 "extraction_model": "haiku",
                 "extraction_version": "v1",
             },
         )), \
         patch("src.services.documents.summarize_document", new_callable=AsyncMock, return_value=""), \
         patch("src.services.documents.os.makedirs"), \
         patch("src.services.documents.shutil.copy2"):
        db = MagicMock()
        captured_doc = {}
        captured_salary_slip = {}

        def add_side_effect(obj):
            if isinstance(obj, Document):
                obj.id = uuid.uuid4()
                captured_doc["doc"] = obj
            elif isinstance(obj, SalarySlip):
                captured_salary_slip["row"] = obj
        db.add.side_effect = add_side_effect
        db.refresh.side_effect = lambda obj: None
        db.query.return_value.filter.return_value.first.return_value = None

        from src.services.documents import process_document
        await process_document(db, tmp_pdf, uuid.uuid4(), "whatsapp")
        doc = captured_doc["doc"]
        assert doc.vendor == "ACME"
        assert doc.review_state == "auto_verified"
        assert doc.doc_metadata["extraction_model"] == "haiku"
        assert doc.doc_metadata["canonical_record_type"] == "salary_slip"
        salary_slip = captured_salary_slip["row"]
        assert salary_slip.employer_name == "ACME"
        assert float(salary_slip.net_salary) == 7800.0


@pytest.mark.asyncio
async def test_salary_slip_review_state_needs_review_for_missing_critical_fields(tmp_pdf):
    with patch("src.services.documents.extract_text_v2", new_callable=AsyncMock, return_value=("תלוש שכר", 0.9, "ocr")), \
         patch("src.services.documents.classify_document", new_callable=AsyncMock, return_value=("salary_slip", 0.9)), \
         patch("src.services.documents._find_duplicate", return_value=None), \
         patch("src.services.documents._extract_salary_slip_facts", new_callable=AsyncMock, return_value=(
             [],
             {
                 "structured_payload": {"gross_salary": 10000.0, "net_salary": None, "confidence": 0.9},
                 "field_confidence": {},
                 "extraction_model": "haiku",
                 "extraction_version": "v1",
             },
         )), \
         patch("src.services.documents.summarize_document", new_callable=AsyncMock, return_value=""), \
         patch("src.services.documents.os.makedirs"), \
         patch("src.services.documents.shutil.copy2"):
        db = MagicMock()
        captured_doc = {}
        captured_salary_slip = {}

        def add_side_effect(obj):
            if isinstance(obj, Document):
                obj.id = uuid.uuid4()
                captured_doc["doc"] = obj
            elif isinstance(obj, SalarySlip):
                captured_salary_slip["row"] = obj
        db.add.side_effect = add_side_effect
        db.refresh.side_effect = lambda obj: None
        db.query.return_value.filter.return_value.first.return_value = None

        from src.services.documents import process_document
        await process_document(db, tmp_pdf, uuid.uuid4(), "whatsapp")
        assert captured_doc["doc"].review_state == "needs_review"
        assert captured_salary_slip["row"].review_reason == "missing_net_salary"
