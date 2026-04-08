"""Unit tests for document_query_service — Q&A, search, reference resolution, P6/P7."""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.schema import Document, DocumentFact, FamilyMember, ConversationState
from src.services.document_query_service import (
    QAResult,
    answer_document_question,
    get_recent_documents,
    get_view_filters,
    merge_tags,
    normalize_tag,
    normalize_tags,
    resolve_document_reference,
    search_documents,
)


def _make_doc(**kwargs) -> MagicMock:
    doc = MagicMock(spec=Document)
    doc.id = kwargs.get("id", uuid.uuid4())
    doc.doc_type = kwargs.get("doc_type", "invoice")
    doc.vendor = kwargs.get("vendor", "Super-Pharm")
    doc.doc_date = kwargs.get("doc_date", "2026-03-15")
    doc.amount = kwargs.get("amount", Decimal("428.50"))
    doc.ai_summary = kwargs.get("ai_summary", "חשבונית מס לחודש מרץ.")
    doc.raw_text = kwargs.get("raw_text", "Invoice total ₪428.50 from Super-Pharm")
    doc.uploaded_by = kwargs.get("uploaded_by", uuid.uuid4())
    doc.created_at = kwargs.get("created_at", None)
    return doc


def _make_member() -> MagicMock:
    m = MagicMock(spec=FamilyMember)
    m.id = uuid.uuid4()
    m.role = "parent"
    return m


def _make_fact(key: str, value: str, confidence: str = "0.9") -> MagicMock:
    fact = MagicMock(spec=DocumentFact)
    fact.fact_key = key
    fact.fact_value = value
    fact.confidence = Decimal(confidence)
    return fact


# ---------------------------------------------------------------------------
# DB field-based answers
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_answer_doc_type_from_db_field():
    db = MagicMock()
    doc = _make_doc(doc_type="invoice")
    member = _make_member()
    result = await answer_document_question(db, member, "מה סוג המסמך?", doc)
    assert result.source == "db_field"
    assert result.field_used == "doc_type"
    assert result.answer_text == "invoice"
    assert result.confidence == 1.0


@pytest.mark.asyncio
async def test_answer_amount_from_db_field():
    db = MagicMock()
    doc = _make_doc(amount=Decimal("500.00"))
    member = _make_member()
    result = await answer_document_question(db, member, "כמה עולה?", doc)
    assert result.source == "db_field"
    assert result.field_used == "amount"
    assert "500" in result.answer_text


@pytest.mark.asyncio
async def test_answer_summary_from_db_field():
    db = MagicMock()
    doc = _make_doc(ai_summary="חשבונית מס לחודש מרץ.")
    member = _make_member()
    result = await answer_document_question(db, member, "תן לי סיכום", doc)
    assert result.source == "db_field"
    assert result.field_used == "ai_summary"


# ---------------------------------------------------------------------------
# Fact-based answers
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_answer_from_document_fact():
    db = MagicMock()
    # Use a doc with no amount/vendor/date/summary so DB field check fails
    doc = _make_doc(doc_type="insurance", amount=None, vendor=None, doc_date=None, ai_summary=None)
    member = _make_member()

    fact = _make_fact("policy_number", "POL-12345")
    db.query.return_value.filter.return_value.all.return_value = [fact]

    # Question contains "policy_number" to match fact_key
    result = await answer_document_question(db, member, "policy_number", doc)
    assert result.source == "document_fact"
    assert result.answer_text == "POL-12345"
    assert result.field_used == "policy_number"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("question", "fact_key", "fact_value"),
    [
        ("מה השכר נטו במסמך האחרון?", "net_salary", "12345.67"),
        ("מה השכר ברוטו במסמך האחרון?", "gross_salary", "16789.00"),
        ("מי המעסיק במסמך האחרון?", "employer_name", "חברת בדיקה בע\"מ"),
        ("לאיזה חודש התלוש שייך?", "pay_month", "2026-03"),
        ("מה הניכויים במסמך האחרון?", "total_deductions", "4443.33"),
    ],
)
async def test_salary_slip_questions_resolved_from_document_facts(question: str, fact_key: str, fact_value: str):
    db = MagicMock()
    doc = _make_doc(doc_type="salary_slip", amount=Decimal("999.99"))
    member = _make_member()

    db.query.return_value.filter.return_value.all.return_value = [_make_fact(fact_key, fact_value)]

    result = await answer_document_question(db, member, question, doc)

    assert result.source == "document_fact"
    assert result.field_used == fact_key
    assert result.answer_text == fact_value


@pytest.mark.asyncio
async def test_salary_slip_question_does_not_fallback_to_document_amount():
    db = MagicMock()
    doc = _make_doc(doc_type="salary_slip", amount=Decimal("500.00"))
    member = _make_member()
    db.query.return_value.filter.return_value.all.return_value = []

    result = await answer_document_question(db, member, "מה השכר נטו במסמך האחרון?", doc)

    assert result.source == "not_found"
    assert result.field_used == "net_salary"
    assert result.answer_text == "המידע הזה לא זמין במסמך"


# ---------------------------------------------------------------------------
# LLM grounded fallback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_answer_llm_grounded_when_no_field_or_fact():
    db = MagicMock()
    # No DB fields that match, no facts, but has raw_text
    doc = _make_doc(doc_type="contract", amount=None, ai_summary=None, vendor=None, doc_date=None)
    member = _make_member()
    db.query.return_value.filter.return_value.all.return_value = []

    with patch("src.services.document_query_service.llm_generate", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = "תאריך סיום החוזה הוא 31 בינואר 2027."
        # Use a question that doesn't match any DB field keyword
        result = await answer_document_question(db, member, "contract_end_date", doc)

    assert result.source == "llm_grounded"
    assert result.confidence == 0.6
    mock_llm.assert_called_once()


# ---------------------------------------------------------------------------
# Not found
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_answer_not_found_when_no_data():
    db = MagicMock()
    doc = _make_doc(doc_type="other", amount=None, ai_summary=None, raw_text="")
    member = _make_member()
    db.query.return_value.filter.return_value.all.return_value = []

    result = await answer_document_question(db, member, "מה מספר הפוליסה?", doc)
    assert result.source == "not_found"
    assert result.answer_text == "המידע הזה לא זמין במסמך"
    assert result.confidence == 0.0


# ---------------------------------------------------------------------------
# P6: QA Groundedness — LLM not called when DB field is sufficient
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_p6_llm_not_called_when_db_field_sufficient():
    """P6: LLM is not invoked when a DB field answers the question."""
    db = MagicMock()
    doc = _make_doc(doc_type="invoice")
    member = _make_member()

    with patch("src.services.document_query_service.llm_generate", new_callable=AsyncMock) as mock_llm:
        result = await answer_document_question(db, member, "מה סוג המסמך?", doc)

    mock_llm.assert_not_called()
    assert result.source == "db_field"


# ---------------------------------------------------------------------------
# search_documents
# ---------------------------------------------------------------------------

def test_search_by_doc_type():
    db = MagicMock()
    member_id = uuid.uuid4()
    mock_docs = [_make_doc(doc_type="invoice")]

    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.order_by.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.all.return_value = mock_docs
    db.query.return_value = mock_query

    results = search_documents(db, member_id, {"doc_type": "invoice"})
    assert results == mock_docs


def test_search_empty_results():
    db = MagicMock()
    member_id = uuid.uuid4()

    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.order_by.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.all.return_value = []
    db.query.return_value = mock_query

    results = search_documents(db, member_id, {"doc_type": "contract"})
    assert results == []


def test_search_by_tag_and_review_state():
    db = MagicMock()
    member_id = uuid.uuid4()
    docs = [_make_doc(doc_type="insurance")]

    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.order_by.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.all.return_value = docs
    db.query.return_value = mock_query

    results = search_documents(
        db,
        member_id,
        {"tag": "#important", "review_state": "needs_review", "limit": 5},
    )
    assert results == docs


def test_get_recent_documents_uses_limit():
    db = MagicMock()
    member_id = uuid.uuid4()
    docs = [_make_doc() for _ in range(3)]
    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.order_by.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.all.return_value = docs
    db.query.return_value = mock_query

    results = get_recent_documents(db, member_id, limit=10)
    assert results == docs
    mock_query.limit.assert_called_once_with(10)


def test_view_filters_mapping():
    assert get_view_filters("active_contracts")["doc_type"] == "contract"
    assert get_view_filters("needs_review")["review_state"] == "needs_review"
    assert get_view_filters("unknown") == {}


def test_tag_normalization_and_merge():
    assert normalize_tag("#Tax-2025") == "tax-2025"
    assert normalize_tags(["#Tax", "tax", "INSURANCE"]) == ["tax", "insurance"]
    assert merge_tags(["tax", "home"], ["#Tax", "insurance"]) == ["tax", "home", "insurance"]


# ---------------------------------------------------------------------------
# resolve_document_reference
# ---------------------------------------------------------------------------

def test_resolve_from_conversation_state():
    db = MagicMock()
    member = _make_member()
    doc_id = uuid.uuid4()

    state = MagicMock(spec=ConversationState)
    state.last_entity_type = "document"
    state.last_entity_id = doc_id

    doc = _make_doc(id=doc_id, uploaded_by=member.id)

    with patch("src.services.document_query_service.get_state", return_value=state):
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = doc
        db.query.return_value = mock_query

        result = resolve_document_reference(db, member, "מה הסכום?")

    assert result == doc


def test_resolve_returns_most_recent_when_single():
    db = MagicMock()
    member = _make_member()

    state = MagicMock(spec=ConversationState)
    state.last_entity_type = None
    state.last_entity_id = None

    doc = _make_doc(uploaded_by=member.id)

    with patch("src.services.document_query_service.get_state", return_value=state):
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [doc]
        db.query.return_value = mock_query

        result = resolve_document_reference(db, member, "מה הסכום?")

    assert result == doc


def test_resolve_explicit_this_document_returns_recent_when_multiple():
    db = MagicMock()
    member = _make_member()

    state = MagicMock(spec=ConversationState)
    state.last_entity_type = None
    state.last_entity_id = None

    docs = [_make_doc(uploaded_by=member.id) for _ in range(3)]

    with patch("src.services.document_query_service.get_state", return_value=state):
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = docs
        db.query.return_value = mock_query

        result = resolve_document_reference(db, member, "מה השכר נטו במסמך הזה?")

    assert result == docs[0]


def test_resolve_returns_list_when_multiple_candidates():
    db = MagicMock()
    member = _make_member()

    state = MagicMock(spec=ConversationState)
    state.last_entity_type = None
    state.last_entity_id = None

    docs = [_make_doc(uploaded_by=member.id) for _ in range(3)]

    with patch("src.services.document_query_service.get_state", return_value=state):
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = docs
        db.query.return_value = mock_query

        result = resolve_document_reference(db, member, "מה הסכום?")

    assert isinstance(result, list)
    assert len(result) == 3


def test_resolve_returns_none_when_no_documents():
    db = MagicMock()
    member = _make_member()

    state = MagicMock(spec=ConversationState)
    state.last_entity_type = None
    state.last_entity_id = None

    with patch("src.services.document_query_service.get_state", return_value=state):
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        db.query.return_value = mock_query

        result = resolve_document_reference(db, member, "מה הסכום?")

    assert result is None
