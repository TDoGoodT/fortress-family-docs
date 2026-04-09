"""Document browse queries — data layer for waterfall browsing.

Provides category counts, period lists, and detail views
by querying canonical tables (salary_slips, utility_bills) and documents.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.models.schema import Document, SalarySlip, UtilityBill
from src.services.document_namer import HEBREW_MONTHS, DOC_TYPE_LABEL_MAP

logger = logging.getLogger(__name__)

# Emoji per doc_type for WhatsApp display
_DOC_TYPE_EMOJI: dict[str, str] = {
    "salary_slip": "💰",
    "electricity_bill": "⚡",
    "water_bill": "💧",
    "invoice": "🧾",
    "receipt": "🧾",
    "contract": "📝",
    "bank_statement": "🏦",
    "credit_card_statement": "💳",
    "insurance": "🛡️",
    "warranty": "📋",
    "official_letter": "📨",
    "recipe": "🍳",
    "other": "📄",
}

# Hebrew plural labels for categories (different from singular in DOC_TYPE_LABEL_MAP)
_CATEGORY_LABELS: dict[str, str] = {
    "salary_slip": "תלושי שכר",
    "electricity_bill": "חשבונות חשמל",
    "water_bill": "חשבונות מים",
    "invoice": "חשבוניות",
    "receipt": "קבלות",
    "contract": "חוזים",
    "bank_statement": "דפי חשבון",
    "credit_card_statement": "כרטיסי אשראי",
    "insurance": "ביטוחים",
    "warranty": "אחריות",
    "official_letter": "מכתבים רשמיים",
    "recipe": "מתכונים",
    "other": "מסמכים אחרים",
}


@dataclass
class CategoryItem:
    doc_type: str
    label: str
    count: int
    emoji: str = "📄"


@dataclass
class PeriodItem:
    period_key: str   # "2025-03"
    label: str        # "מרץ 2025"
    count: int = 1


@dataclass
class DetailItem:
    document_id: UUID
    display_name: str
    display_fields: dict[str, str] = field(default_factory=dict)


def _month_label(year: int, month: int) -> str:
    return f"{HEBREW_MONTHS.get(month, str(month))} {year}"


def _period_key(year: int, month: int) -> str:
    return f"{year}-{month:02d}"


def get_categories(db: Session, member_id: UUID) -> list[CategoryItem]:
    """Count documents per doc_type for a member."""
    rows = (
        db.query(Document.doc_type, func.count(Document.id))
        .filter(Document.uploaded_by == member_id)
        .group_by(Document.doc_type)
        .all()
    )
    categories = []
    for doc_type, count in sorted(rows, key=lambda r: -r[1]):
        if not doc_type or count == 0:
            continue
        categories.append(CategoryItem(
            doc_type=doc_type,
            label=_CATEGORY_LABELS.get(doc_type, DOC_TYPE_LABEL_MAP.get(doc_type, doc_type)),
            count=count,
            emoji=_DOC_TYPE_EMOJI.get(doc_type, "📄"),
        ))
    return categories


def get_periods(db: Session, member_id: UUID, doc_type: str) -> list[PeriodItem]:
    """Get available periods for a doc_type, reverse chronological."""
    period_counts: dict[str, int] = {}

    if doc_type == "salary_slip":
        rows = (
            db.query(SalarySlip.pay_year, SalarySlip.pay_month, func.count(SalarySlip.id))
            .filter(SalarySlip.family_member_id == member_id)
            .group_by(SalarySlip.pay_year, SalarySlip.pay_month)
            .all()
        )
        for year, month, count in rows:
            if year and month:
                key = _period_key(year, month)
                period_counts[key] = count

    elif doc_type in ("electricity_bill", "water_bill"):
        service_map = {"electricity_bill": "electricity", "water_bill": "water"}
        stype = service_map.get(doc_type)
        rows = (
            db.query(UtilityBill.period_start, UtilityBill.issue_date, func.count(UtilityBill.id))
            .filter(UtilityBill.family_member_id == member_id)
            .filter(UtilityBill.service_type == stype)
            .group_by(UtilityBill.period_start, UtilityBill.issue_date)
            .all()
        )
        for period_start, issue_date, count in rows:
            d = period_start or issue_date
            if d:
                key = _period_key(d.year, d.month)
                period_counts[key] = period_counts.get(key, 0) + count

    else:
        rows = (
            db.query(Document.doc_date, func.count(Document.id))
            .filter(Document.uploaded_by == member_id, Document.doc_type == doc_type)
            .group_by(Document.doc_date)
            .all()
        )
        for doc_date, count in rows:
            if doc_date:
                key = _period_key(doc_date.year, doc_date.month)
                period_counts[key] = period_counts.get(key, 0) + count
            else:
                period_counts["unknown"] = period_counts.get("unknown", 0) + count

    # Build sorted list (reverse chronological)
    periods = []
    for key in sorted(period_counts.keys(), reverse=True):
        if key == "unknown":
            periods.append(PeriodItem(period_key=key, label="ללא תאריך", count=period_counts[key]))
        else:
            parts = key.split("-")
            year, month = int(parts[0]), int(parts[1])
            periods.append(PeriodItem(period_key=key, label=_month_label(year, month), count=period_counts[key]))
    return periods


def get_details(db: Session, member_id: UUID, doc_type: str, period_key: str) -> list[DetailItem]:
    """Get document details for a specific type + period."""
    if period_key == "unknown":
        year, month = None, None
    else:
        parts = period_key.split("-")
        year, month = int(parts[0]), int(parts[1])

    details: list[DetailItem] = []

    if doc_type == "salary_slip" and year and month:
        slips = (
            db.query(SalarySlip)
            .filter(SalarySlip.family_member_id == member_id,
                    SalarySlip.pay_year == year, SalarySlip.pay_month == month)
            .all()
        )
        for s in slips:
            fields = {}
            if s.employer_name:
                fields["מעסיק"] = s.employer_name
            if s.gross_salary is not None:
                fields["ברוטו"] = f"₪{s.gross_salary:,.2f}"
            if s.net_salary is not None:
                fields["נטו"] = f"₪{s.net_salary:,.2f}"
            if s.total_deductions is not None:
                fields["ניכויים"] = f"₪{s.total_deductions:,.2f}"
            if s.net_to_pay is not None:
                fields["נטו לתשלום"] = f"₪{s.net_to_pay:,.2f}"
            details.append(DetailItem(
                document_id=s.document_id,
                display_name=f"תלוש שכר {_month_label(year, month)}",
                display_fields=fields,
            ))

    elif doc_type in ("electricity_bill", "water_bill") and year and month:
        from datetime import date
        service_map = {"electricity_bill": "electricity", "water_bill": "water"}
        stype = service_map.get(doc_type)
        bills = (
            db.query(UtilityBill)
            .filter(UtilityBill.family_member_id == member_id,
                    UtilityBill.service_type == stype)
            .all()
        )
        for b in bills:
            d = b.period_start or b.issue_date
            if d and d.year == year and d.month == month:
                fields = {}
                if b.provider_name:
                    fields["ספק"] = b.provider_name
                if b.amount_due is not None:
                    fields["סכום"] = f"₪{b.amount_due:,.2f}"
                if b.total_with_vat is not None:
                    fields["כולל מע\"מ"] = f"₪{b.total_with_vat:,.2f}"
                if b.period_start and b.period_end:
                    fields["תקופה"] = f"{b.period_start} - {b.period_end}"
                label = DOC_TYPE_LABEL_MAP.get(doc_type, doc_type)
                details.append(DetailItem(
                    document_id=b.document_id,
                    display_name=f"{label} {_month_label(year, month)}",
                    display_fields=fields,
                ))

    else:
        # Generic documents
        query = db.query(Document).filter(
            Document.uploaded_by == member_id, Document.doc_type == doc_type)
        if year and month:
            from datetime import date
            query = query.filter(
                func.extract("year", Document.doc_date) == year,
                func.extract("month", Document.doc_date) == month,
            )
        else:
            query = query.filter(Document.doc_date.is_(None))
        docs = query.all()
        for d in docs:
            fields = {}
            if d.vendor:
                fields["ספק"] = d.vendor
            if d.amount is not None:
                fields["סכום"] = f"₪{d.amount:,.2f}"
            if d.doc_date:
                fields["תאריך"] = str(d.doc_date)
            details.append(DetailItem(
                document_id=d.id,
                display_name=d.display_name or d.original_filename or "מסמך",
                display_fields=fields,
            ))

    return details
