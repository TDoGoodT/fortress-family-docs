"""Fortress document query service — Q&A, search, and document reference resolution."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Union
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session

from src.models.schema import Document, DocumentFact, FamilyMember
from src.services.conversation_state import get_state, update_state
from src.services.llm_dispatch import llm_generate

logger = logging.getLogger(__name__)

# Question intent keywords → physical DB field
_FIELD_QUESTION_MAP: dict[str, str] = {
    # type questions
    "סוג": "doc_type", "type": "doc_type", "what type": "doc_type", "מה סוג": "doc_type",
    # amount questions
    "סכום": "amount", "amount": "amount", "כמה": "amount", "עולה": "amount",
    # counterparty questions
    "ספק": "vendor", "vendor": "vendor", "counterparty": "vendor", "מי": "vendor",
    # date questions
    "תאריך": "doc_date", "date": "doc_date", "מתי": "doc_date",
    # summary questions
    "סיכום": "ai_summary", "summary": "ai_summary", "תקציר": "ai_summary",
}


@dataclass
class QAResult:
    """Structured result from document Q&A for observability and testing."""
    answer_text: str
    source: str          # "db_field" | "document_fact" | "llm_grounded" | "not_found"
    confidence: float
    field_used: str | None


def normalize_tag(tag: str) -> str:
    """Normalize a user/system tag to storage format."""
    if not tag:
        return ""
    cleaned = tag.strip().lower()
    if cleaned.startswith("#"):
        cleaned = cleaned[1:]
    return cleaned


def normalize_tags(tags: list[str] | None) -> list[str]:
    """Normalize a list of tags to lowercase + deduplicated values."""
    if not tags:
        return []
    normalized: list[str] = []
    for tag in tags:
        value = normalize_tag(str(tag))
        if value and value not in normalized:
            normalized.append(value)
    return normalized


def merge_tags(existing: list[str] | None, additions: list[str] | None) -> list[str]:
    """Merge tags deterministically while keeping insertion order."""
    merged: list[str] = []
    for tag in normalize_tags(existing) + normalize_tags(additions):
        if tag not in merged:
            merged.append(tag)
    return merged


def get_recent_documents(
    db: Session,
    member_id: UUID,
    limit: int = 5,
) -> list[Document]:
    """Return the most recent documents for a member."""
    safe_limit = min(max(limit, 1), 20)
    return (
        db.query(Document)
        .filter(Document.uploaded_by == member_id)
        .order_by(Document.created_at.desc())
        .limit(safe_limit)
        .all()
    )


_PREDEFINED_VIEWS: dict[str, dict] = {
    "active_contracts": {"doc_type": "contract"},
    "insurance_documents": {"doc_type": "insurance"},
    "recent_invoices": {"doc_type": "invoice", "recent": True, "limit": 10},
    "needs_review": {"review_state": "needs_review"},
}


def get_view_filters(view_name: str) -> dict:
    """Map lightweight saved-search style views to deterministic filters."""
    return _PREDEFINED_VIEWS.get(view_name, {}).copy()


def _format_field_value(field: str, value) -> str:
    """Format a DB field value for WhatsApp display."""
    if value is None:
        return ""
    if field == "doc_type":
        return str(value)
    if field == "amount":
        return str(value)
    if field == "doc_date":
        return str(value)
    return str(value)


async def answer_document_question(
    db: Session,
    member: FamilyMember,
    question: str,
    doc: Document,
) -> QAResult:
    """Answer a question about a specific document.

    Priority: DB fields → document_facts → LLM grounded extraction → not_found.
    Returns structured QAResult; skill layer extracts answer_text for WhatsApp.
    LLM is used only for grounded phrasing/extraction from raw_text, never free-form.
    """
    question_lower = question.lower()

    # 1. Check if question maps to a known DB field
    matched_field = None
    for keyword, field in _FIELD_QUESTION_MAP.items():
        if keyword.lower() in question_lower:
            matched_field = field
            break

    if matched_field:
        value = getattr(doc, matched_field, None)
        if value is not None and str(value).strip():
            formatted = _format_field_value(matched_field, value)
            return QAResult(
                answer_text=formatted,
                source="db_field",
                confidence=1.0,
                field_used=matched_field,
            )

    # 2. Check document_facts for matching fact_key
    try:
        facts = db.query(DocumentFact).filter(DocumentFact.document_id == doc.id).all()
        for fact in facts:
            if fact.fact_key in question_lower or question_lower in fact.fact_key:
                return QAResult(
                    answer_text=fact.fact_value,
                    source="document_fact",
                    confidence=float(fact.confidence or 0.5),
                    field_used=fact.fact_key,
                )
    except Exception as exc:
        logger.warning("query_service: fact lookup failed doc=%s error=%s", doc.id, exc)

    # 3. LLM grounded extraction from raw_text (haiku tier)
    if doc.raw_text and doc.raw_text.strip():
        try:
            prompt = (
                f"Answer this question about the document using only the text provided.\n"
                f"Question: {question}\n\n"
                f"Document text (first 2000 chars):\n{doc.raw_text[:2000]}\n\n"
                f"If the answer is not in the text, respond with: לא נמצא מידע\n"
                f"Answer in Hebrew, 1-2 sentences only."
            )
            system = "You are a document assistant. Answer only from the provided text. Never invent information."
            answer = await llm_generate(prompt, system, "haiku")
            if answer and answer.strip() and "לא נמצא מידע" not in answer:
                return QAResult(
                    answer_text=answer.strip(),
                    source="llm_grounded",
                    confidence=0.6,
                    field_used=None,
                )
        except Exception as exc:
            logger.warning("query_service: LLM grounded extraction failed doc=%s error=%s", doc.id, exc)

    # 4. Not found
    return QAResult(
        answer_text="המידע הזה לא זמין במסמך",
        source="not_found",
        confidence=0.0,
        field_used=None,
    )


def search_documents(
    db: Session,
    member_id: UUID,
    filters: dict,
) -> list[Document]:
    """Search documents with filters.

    Supported filters:
    - doc_type (str): exact match against physical doc_type column
    - vendor (str): case-insensitive partial match against physical vendor column
    - keyword (str): case-insensitive partial match against original_filename and raw_text
    - review_state (str): exact match against review_state
    - tag (str): filter by a single normalized tag in JSONB tags array
    - recent (bool): order by created_at descending
    - limit (int): max results (default 20)
    """
    query = db.query(Document).filter(Document.uploaded_by == member_id)

    doc_type = filters.get("doc_type")
    if doc_type:
        query = query.filter(Document.doc_type == doc_type)

    vendor = filters.get("vendor")
    if vendor:
        query = query.filter(Document.vendor.ilike(f"%{vendor}%"))

    keyword = filters.get("keyword")
    if keyword:
        query = query.filter(
            or_(
                Document.original_filename.ilike(f"%{keyword}%"),
                Document.raw_text.ilike(f"%{keyword}%"),
            )
        )

    review_state = filters.get("review_state")
    if review_state:
        query = query.filter(Document.review_state == review_state)

    tag = normalize_tag(filters.get("tag", ""))
    if tag:
        query = query.filter(Document.tags.contains([tag]))

    query = query.order_by(Document.created_at.desc())
    limit = filters.get("limit", 20)
    return query.limit(limit).all()


def resolve_document_reference(
    db: Session,
    member: FamilyMember,
    question: str,
) -> Union[Document, list[Document], None]:
    """Resolve which document the user is asking about.

    Resolution order:
    1. conversation_state.last_entity_type == "document" with valid last_entity_id
    2. Most recently uploaded document (if question implies recency or single match)
    3. Return list of up to 5 candidates for disambiguation

    Returns:
    - Document: single resolved document
    - list[Document]: multiple candidates (caller should ask for clarification)
    - None: no documents found
    """
    # 1. Check conversation state
    try:
        state = get_state(db, member.id)
        if state.last_entity_type == "document" and state.last_entity_id:
            doc = db.query(Document).filter(
                Document.id == state.last_entity_id,
                Document.uploaded_by == member.id,
            ).first()
            if doc:
                logger.info("query_service: resolved from conversation_state doc=%s", doc.id)
                return doc
    except Exception as exc:
        logger.warning("query_service: conversation_state lookup failed error=%s", exc)

    # 2. Get recent documents for this member
    recent = (
        db.query(Document)
        .filter(Document.uploaded_by == member.id)
        .order_by(Document.created_at.desc())
        .limit(5)
        .all()
    )

    if not recent:
        return None

    if len(recent) == 1:
        return recent[0]

    # Check if question implies "most recent"
    recency_keywords = ["אחרון", "last", "latest", "recent", "האחרון"]
    if any(kw in question.lower() for kw in recency_keywords):
        return recent[0]

    # Return candidates for disambiguation
    return recent
