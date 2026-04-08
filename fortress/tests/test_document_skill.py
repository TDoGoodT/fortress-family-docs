"""Unit tests for extended DocumentSkill — search, query, recent, P7 access control."""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.schema import Document, FamilyMember, Permission
from src.skills.base_skill import Command, Result
from src.skills.document_skill import DocumentSkill


def _make_member(role="parent", is_active=True) -> MagicMock:
    m = MagicMock(spec=FamilyMember)
    m.id = uuid.uuid4()
    m.name = "Test User"
    m.phone = "+972501234567"
    m.role = role
    m.is_active = is_active
    return m


def _make_doc(**kwargs) -> MagicMock:
    doc = MagicMock(spec=Document)
    doc.id = kwargs.get("id", uuid.uuid4())
    doc.original_filename = kwargs.get("original_filename", "test.pdf")
    doc.doc_type = kwargs.get("doc_type", "invoice")
    doc.vendor = kwargs.get("vendor", "Super-Pharm")
    doc.doc_date = kwargs.get("doc_date", "2026-03-15")
    doc.amount = kwargs.get("amount", Decimal("100.00"))
    doc.ai_summary = kwargs.get("ai_summary", "סיכום.")
    doc.raw_text = kwargs.get("raw_text", "invoice text")
    doc.created_at = kwargs.get("created_at", None)
    return doc


def _make_permission(can_read=True, can_write=True) -> MagicMock:
    p = MagicMock(spec=Permission)
    p.can_read = can_read
    p.can_write = can_write
    return p


def _make_db(docs=None, permission=None) -> MagicMock:
    db = MagicMock()
    perm = permission or _make_permission()
    db.query.return_value.filter.return_value.first.return_value = perm
    if docs is not None:
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.all.return_value = docs
        mock_q.first.return_value = docs[0] if docs else None
        db.query.return_value = mock_q
    return db


skill = DocumentSkill()


# ---------------------------------------------------------------------------
# _search: by type
# ---------------------------------------------------------------------------

def test_search_by_type_returns_results():
    doc = _make_doc(doc_type="invoice")
    db = MagicMock()

    # Permission check returns a permission with can_read=True
    perm = _make_permission(can_read=True)
    mock_q = MagicMock()
    mock_q.filter.return_value = mock_q
    mock_q.order_by.return_value = mock_q
    mock_q.limit.return_value = mock_q
    mock_q.all.return_value = [doc]
    mock_q.first.return_value = perm
    db.query.return_value = mock_q

    with patch("src.skills.document_skill.check_perm", return_value=None), \
         patch("src.skills.document_skill.search_documents", return_value=[doc]):
        cmd = Command(skill="document", action="search", params={"doc_type": "חשבוניות"})
        result = skill.execute(db, _make_member(), cmd)

    assert result.success
    assert "invoice" in result.message or "🧾" in result.message or "חשבונית" in result.message or "1." in result.message


def test_search_by_vendor_keyword():
    doc = _make_doc(vendor="Super-Pharm")
    with patch("src.skills.document_skill.check_perm", return_value=None), \
         patch("src.skills.document_skill.search_documents", return_value=[doc]):
        cmd = Command(skill="document", action="search", params={"keyword": "Super-Pharm"})
        result = skill.execute(MagicMock(), _make_member(), cmd)

    assert result.success


def test_search_empty_returns_empty_message():
    with patch("src.skills.document_skill.check_perm", return_value=None), \
         patch("src.skills.document_skill.search_documents", return_value=[]):
        cmd = Command(skill="document", action="search", params={"doc_type": "contract"})
        result = skill.execute(MagicMock(), _make_member(), cmd)

    assert result.success
    assert "לא נמצאו" in result.message


# ---------------------------------------------------------------------------
# _recent
# ---------------------------------------------------------------------------

def test_recent_returns_most_recent_document():
    doc = _make_doc()
    db = MagicMock()
    mock_q = MagicMock()
    mock_q.filter.return_value = mock_q
    mock_q.order_by.return_value = mock_q
    mock_q.first.return_value = doc
    db.query.return_value = mock_q

    with patch("src.skills.document_skill.check_perm", return_value=None):
        cmd = Command(skill="document", action="recent", params={})
        result = skill.execute(db, _make_member(), cmd)

    assert result.success
    assert result.entity_id == doc.id


def test_recent_empty_returns_empty_message():
    db = MagicMock()
    mock_q = MagicMock()
    mock_q.filter.return_value = mock_q
    mock_q.order_by.return_value = mock_q
    mock_q.first.return_value = None
    db.query.return_value = mock_q

    with patch("src.skills.document_skill.check_perm", return_value=None):
        cmd = Command(skill="document", action="recent", params={})
        result = skill.execute(db, _make_member(), cmd)

    assert result.success
    assert "אין" in result.message


def test_recent_feed_returns_latest_five():
    docs = [_make_doc(original_filename=f"doc-{i}.pdf") for i in range(5)]
    with patch("src.skills.document_skill.check_perm", return_value=None), \
         patch("src.skills.document_skill.get_recent_documents", return_value=docs):
        cmd = Command(skill="document", action="recent_feed", params={})
        result = skill.execute(MagicMock(), _make_member(), cmd)

    assert result.success
    assert "מסמכים אחרונים" in result.message
    assert "doc-0.pdf" in result.message


def test_tag_add_on_resolved_document():
    doc = _make_doc()
    doc.tags = ["insurance"]
    db = MagicMock()
    with patch("src.skills.document_skill.check_perm", return_value=None), \
         patch("src.skills.document_skill.resolve_document_reference", return_value=doc), \
         patch("src.skills.document_skill.update_state"):
        cmd = Command(skill="document", action="tag_add", params={"tag": "Tax-2025"})
        result = skill.execute(db, _make_member(), cmd)

    assert result.success
    assert "tax-2025" in doc.tags
    db.commit.assert_called_once()


def test_tag_remove_on_resolved_document():
    doc = _make_doc()
    doc.tags = ["insurance", "important"]
    db = MagicMock()
    with patch("src.skills.document_skill.check_perm", return_value=None), \
         patch("src.skills.document_skill.resolve_document_reference", return_value=doc):
        cmd = Command(skill="document", action="tag_remove", params={"tag": "important"})
        result = skill.execute(db, _make_member(), cmd)

    assert result.success
    assert "important" not in doc.tags


def test_tag_show():
    doc = _make_doc()
    doc.tags = ["insurance", "tax-2025"]
    with patch("src.skills.document_skill.check_perm", return_value=None), \
         patch("src.skills.document_skill.resolve_document_reference", return_value=doc):
        cmd = Command(skill="document", action="tag_show", params={})
        result = skill.execute(MagicMock(), _make_member(), cmd)
    assert result.success
    assert "#insurance" in result.message


def test_tag_search_uses_search_documents():
    doc = _make_doc()
    with patch("src.skills.document_skill.check_perm", return_value=None), \
         patch("src.skills.document_skill.search_documents", return_value=[doc]) as mock_search:
        cmd = Command(skill="document", action="tag_search", params={"tag": "rent"})
        result = skill.execute(MagicMock(), _make_member(), cmd)
    assert result.success
    mock_search.assert_called_once()


def test_predefined_view_needs_review():
    doc = _make_doc()
    with patch("src.skills.document_skill.check_perm", return_value=None), \
         patch("src.skills.document_skill.search_documents", return_value=[doc]) as mock_search:
        cmd = Command(skill="document", action="view_needs_review", params={})
        result = skill.execute(MagicMock(), _make_member(), cmd)
    assert result.success
    assert mock_search.call_args[0][2]["review_state"] == "needs_review"


# ---------------------------------------------------------------------------
# _query: resolves from conversation_state
# ---------------------------------------------------------------------------

def test_query_resolves_from_conversation_state():
    doc = _make_doc()
    with patch("src.skills.document_skill.check_perm", return_value=None), \
         patch("src.skills.document_skill.resolve_document_reference", return_value=doc), \
         patch("src.skills.document_skill.update_state"), \
         patch("src.skills.document_skill.answer_document_question", new_callable=AsyncMock) as mock_qa:
        from src.services.document_query_service import QAResult
        mock_qa.return_value = QAResult(answer_text="invoice", source="db_field", confidence=1.0, field_used="doc_type")
        cmd = Command(skill="document", action="query", params={"question": "מה סוג המסמך?"})
        result = skill.execute(MagicMock(), _make_member(), cmd)

    assert result.success
    assert result.entity_id == doc.id


def test_query_with_multiple_candidates_returns_clarification():
    docs = [_make_doc() for _ in range(3)]
    with patch("src.skills.document_skill.check_perm", return_value=None), \
         patch("src.skills.document_skill.resolve_document_reference", return_value=docs):
        cmd = Command(skill="document", action="query", params={"question": "מה הסכום?"})
        result = skill.execute(MagicMock(), _make_member(), cmd)

    assert result.success
    assert "מצאתי" in result.message or "1." in result.message


def test_query_no_documents_returns_empty_message():
    with patch("src.skills.document_skill.check_perm", return_value=None), \
         patch("src.skills.document_skill.resolve_document_reference", return_value=None):
        cmd = Command(skill="document", action="query", params={"question": "מה הסכום?"})
        result = skill.execute(MagicMock(), _make_member(), cmd)

    assert result.success
    assert "אין" in result.message


def test_doc_search_fallback_explicit_last_document_uses_resolver():
    doc = _make_doc(doc_type="salary_slip")
    with patch("src.skills.document_skill.check_perm", return_value=None), \
         patch("src.skills.document_skill.resolve_document_reference", return_value=doc), \
         patch("src.skills.document_skill.search_documents") as mock_search, \
         patch("src.skills.document_skill.update_state"), \
         patch("src.skills.document_skill.answer_document_question", new_callable=AsyncMock) as mock_qa:
        from src.services.document_query_service import QAResult
        mock_qa.return_value = QAResult(
            answer_text="12345.67",
            source="document_fact",
            confidence=0.9,
            field_used="net_salary",
        )
        cmd = Command(skill="document", action="doc_search_fallback", params={"raw_text": "מה השכר נטו במסמך האחרון?"})
        result = skill.execute(MagicMock(), _make_member(), cmd)

    assert result.success
    assert result.message == "12345.67"
    mock_search.assert_not_called()


# ---------------------------------------------------------------------------
# P7: Access Control Enforcement
# ---------------------------------------------------------------------------

def test_p7_search_denied_for_no_read_permission():
    """P7: search returns permission denied when user lacks read access."""
    from src.prompts.personality import TEMPLATES
    denied_result = Result(success=False, message=TEMPLATES["permission_denied"])
    with patch("src.skills.document_skill.check_perm", return_value=denied_result):
        cmd = Command(skill="document", action="search", params={"doc_type": "invoice"})
        result = skill.execute(MagicMock(), _make_member(role="child"), cmd)

    assert not result.success
    assert "הרשאה" in result.message


def test_p7_query_denied_for_no_read_permission():
    """P7: query returns permission denied when user lacks read access."""
    from src.prompts.personality import TEMPLATES
    denied_result = Result(success=False, message=TEMPLATES["permission_denied"])
    with patch("src.skills.document_skill.check_perm", return_value=denied_result):
        cmd = Command(skill="document", action="query", params={"question": "מה הסכום?"})
        result = skill.execute(MagicMock(), _make_member(role="child"), cmd)

    assert not result.success


def test_p7_recent_denied_for_no_read_permission():
    """P7: recent returns permission denied when user lacks read access."""
    from src.prompts.personality import TEMPLATES
    denied_result = Result(success=False, message=TEMPLATES["permission_denied"])
    with patch("src.skills.document_skill.check_perm", return_value=denied_result):
        cmd = Command(skill="document", action="recent", params={})
        result = skill.execute(MagicMock(), _make_member(role="child"), cmd)

    assert not result.success
