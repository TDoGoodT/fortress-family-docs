"""Fortress Data Access Layer — clean read/write interface for agents.

Every function checks agent permissions before returning data.
Returns plain dicts (JSON-serializable), never ORM objects.
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from src.api.permissions import AccessLevel, check_access
from src.models.schema import (
    Contract,
    Document,
    DocumentFact,
    InsurancePolicy,
    SalarySlip,
    UtilityBill,
)

logger = logging.getLogger(__name__)


class PermissionDenied(Exception):
    """Raised when an agent lacks permission for the requested data."""
    def __init__(self, agent_role: str, table: str, required: str):
        self.agent_role = agent_role
        self.table = table
        self.required = required
        super().__init__(f"Agent '{agent_role}' lacks '{required}' access to '{table}'")


def _check(agent_role: str, table: str, level: AccessLevel) -> None:
    if not check_access(agent_role, table, level):
        raise PermissionDenied(agent_role, table, level.value)


def _decimal_to_float(val: Any) -> Any:
    if isinstance(val, Decimal):
        return float(val)
    return val


def _doc_to_metadata(doc: Document) -> dict[str, Any]:
    """Convert a Document to metadata-only dict (no raw_text, no full content)."""
    return {
        "id": str(doc.id),
        "doc_type": doc.doc_type,
        "vendor": doc.vendor,
        "amount": _decimal_to_float(doc.amount),
        "currency": doc.currency,
        "doc_date": doc.doc_date.isoformat() if doc.doc_date else None,
        "display_name": doc.display_name,
        "review_state": doc.review_state,
        "tags": doc.tags or [],
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
    }


def _doc_to_full(doc: Document) -> dict[str, Any]:
    """Convert a Document to full dict including raw_text and summary."""
    result = _doc_to_metadata(doc)
    result.update({
        "original_filename": doc.original_filename,
        "raw_text": doc.raw_text,
        "ai_summary": doc.ai_summary,
        "confidence": _decimal_to_float(doc.confidence),
        "source": doc.source,
    })
    return result


# ── Documents ────────────────────────────────────────────────────────────

def get_documents(
    db: Session,
    agent_role: str,
    *,
    doc_type: str | None = None,
    vendor: str | None = None,
    tag: str | None = None,
    review_state: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List documents with optional filters. Returns metadata or full based on permissions."""
    has_read = check_access(agent_role, "documents", AccessLevel.READ)
    has_meta = check_access(agent_role, "documents", AccessLevel.METADATA)
    if not has_meta:
        raise PermissionDenied(agent_role, "documents", "metadata")

    query = db.query(Document)
    if doc_type:
        query = query.filter(Document.doc_type == doc_type)
    if vendor:
        query = query.filter(Document.vendor.ilike(f"%{vendor}%"))
    if review_state:
        query = query.filter(Document.review_state == review_state)
    if tag:
        query = query.filter(Document.tags.contains([tag]))

    docs = query.order_by(Document.created_at.desc()).offset(offset).limit(limit).all()
    converter = _doc_to_full if has_read else _doc_to_metadata
    return [converter(doc) for doc in docs]


def get_document_by_id(
    db: Session,
    agent_role: str,
    doc_id: UUID,
) -> dict[str, Any] | None:
    """Get a single document by ID."""
    has_read = check_access(agent_role, "documents", AccessLevel.READ)
    has_meta = check_access(agent_role, "documents", AccessLevel.METADATA)
    if not has_meta:
        raise PermissionDenied(agent_role, "documents", "metadata")

    doc = db.query(Document).filter(Document.id == doc_id).first()
    if doc is None:
        return None
    return _doc_to_full(doc) if has_read else _doc_to_metadata(doc)


# ── Facts ────────────────────────────────────────────────────────────────

def search_facts(
    db: Session,
    agent_role: str,
    *,
    fact_key: str | None = None,
    fact_type: str | None = None,
    query_text: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Search extracted facts across all documents."""
    _check(agent_role, "document_facts", AccessLevel.READ)

    q = db.query(DocumentFact)
    if fact_key:
        q = q.filter(DocumentFact.fact_key == fact_key)
    if fact_type:
        q = q.filter(DocumentFact.fact_type == fact_type)
    if query_text:
        q = q.filter(DocumentFact.fact_value.ilike(f"%{query_text}%"))

    facts = q.order_by(DocumentFact.created_at.desc()).limit(limit).all()
    return [
        {
            "id": str(f.id),
            "document_id": str(f.document_id),
            "fact_type": f.fact_type,
            "fact_key": f.fact_key,
            "fact_value": f.fact_value,
            "confidence": _decimal_to_float(f.confidence),
            "source_excerpt": f.source_excerpt,
        }
        for f in facts
    ]


# ── Salary Slips ─────────────────────────────────────────────────────────

def get_salary_slips(
    db: Session,
    agent_role: str,
    *,
    year: int | None = None,
    employer: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Get salary slip records."""
    _check(agent_role, "salary_slips", AccessLevel.READ)

    q = db.query(SalarySlip)
    if year:
        q = q.filter(SalarySlip.pay_year == year)
    if employer:
        q = q.filter(SalarySlip.employer_name.ilike(f"%{employer}%"))

    slips = q.order_by(SalarySlip.pay_year.desc(), SalarySlip.pay_month.desc()).limit(limit).all()
    return [
        {
            "id": str(s.id),
            "document_id": str(s.document_id),
            "employee_name": s.employee_name,
            "employer_name": s.employer_name,
            "pay_year": s.pay_year,
            "pay_month": s.pay_month,
            "gross_salary": _decimal_to_float(s.gross_salary),
            "net_salary": _decimal_to_float(s.net_salary),
            "total_deductions": _decimal_to_float(s.total_deductions),
            "income_tax": _decimal_to_float(s.income_tax),
            "pension_employee": _decimal_to_float(s.pension_employee),
            "review_state": s.review_state,
        }
        for s in slips
    ]


# ── Utility Bills ────────────────────────────────────────────────────────

def get_utility_bills(
    db: Session,
    agent_role: str,
    *,
    service_type: str | None = None,
    provider: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Get utility bill records."""
    _check(agent_role, "utility_bills", AccessLevel.READ)

    q = db.query(UtilityBill)
    if service_type:
        q = q.filter(UtilityBill.service_type == service_type)
    if provider:
        q = q.filter(UtilityBill.provider_name.ilike(f"%{provider}%"))

    bills = q.order_by(UtilityBill.issue_date.desc()).limit(limit).all()
    return [
        {
            "id": str(b.id),
            "document_id": str(b.document_id),
            "provider_name": b.provider_name,
            "service_type": b.service_type,
            "amount_due": _decimal_to_float(b.amount_due),
            "currency": b.currency,
            "issue_date": b.issue_date.isoformat() if b.issue_date else None,
            "period_start": b.period_start.isoformat() if b.period_start else None,
            "period_end": b.period_end.isoformat() if b.period_end else None,
            "consumption_kwh": _decimal_to_float(b.consumption_kwh),
            "review_state": b.review_state,
        }
        for b in bills
    ]


# ── Contracts ────────────────────────────────────────────────────────────

def get_contracts(
    db: Session,
    agent_role: str,
    *,
    active_only: bool = False,
    contract_type: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Get contract records."""
    _check(agent_role, "contracts", AccessLevel.READ)

    q = db.query(Contract)
    if active_only:
        q = q.filter((Contract.end_date == None) | (Contract.end_date >= date.today()))
    if contract_type:
        q = q.filter(Contract.contract_type == contract_type)

    contracts = q.order_by(Contract.contract_date.desc()).limit(limit).all()
    return [
        {
            "id": str(c.id),
            "document_id": str(c.document_id),
            "contract_type": c.contract_type,
            "counterparty": c.counterparty,
            "parties": c.parties,
            "contract_date": c.contract_date.isoformat() if c.contract_date else None,
            "end_date": c.end_date.isoformat() if c.end_date else None,
            "amount": _decimal_to_float(c.amount),
            "currency": c.currency,
            "obligations": c.obligations,
            "renewal_terms": c.renewal_terms,
            "penalty_clause": c.penalty_clause,
            "governing_law": c.governing_law,
            "review_state": c.review_state,
        }
        for c in contracts
    ]


# ── Insurance Policies ───────────────────────────────────────────────────

def get_insurance_policies(
    db: Session,
    agent_role: str,
    *,
    active_only: bool = False,
    insurance_type: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Get insurance policy records."""
    _check(agent_role, "insurance_policies", AccessLevel.READ)

    q = db.query(InsurancePolicy)
    if active_only:
        q = q.filter((InsurancePolicy.end_date == None) | (InsurancePolicy.end_date >= date.today()))
    if insurance_type:
        q = q.filter(InsurancePolicy.insurance_type == insurance_type)

    policies = q.order_by(InsurancePolicy.policy_date.desc()).limit(limit).all()
    return [
        {
            "id": str(p.id),
            "document_id": str(p.document_id),
            "insurance_type": p.insurance_type,
            "insurer": p.insurer,
            "policy_number": p.policy_number,
            "insured_name": p.insured_name,
            "coverage_description": p.coverage_description,
            "premium_amount": _decimal_to_float(p.premium_amount),
            "deductible_amount": _decimal_to_float(p.deductible_amount),
            "start_date": p.start_date.isoformat() if p.start_date else None,
            "end_date": p.end_date.isoformat() if p.end_date else None,
            "review_state": p.review_state,
        }
        for p in policies
    ]


# ── Library Stats (for orchestrator/librarian) ──────────────────────────

def get_library_stats(db: Session, agent_role: str) -> dict[str, Any]:
    """Get high-level stats about the data library."""
    _check(agent_role, "documents", AccessLevel.METADATA)

    from sqlalchemy import func

    total_docs = db.query(Document).count()
    type_counts = (
        db.query(Document.doc_type, func.count(Document.id))
        .group_by(Document.doc_type)
        .all()
    )
    by_type = {(t or "other"): c for t, c in type_counts}
    needs_review = db.query(Document).filter(Document.review_state == "needs_review").count()

    return {
        "total_documents": total_docs,
        "documents_by_type": by_type,
        "needs_review": needs_review,
        "salary_slips": db.query(SalarySlip).count(),
        "utility_bills": db.query(UtilityBill).count(),
        "contracts": db.query(Contract).count(),
        "insurance_policies": db.query(InsurancePolicy).count(),
    }
