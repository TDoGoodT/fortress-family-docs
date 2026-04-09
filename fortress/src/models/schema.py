from __future__ import annotations
"""Fortress 2.0 ORM models — SQLAlchemy 2.0 mapped_column style."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    ForeignKey,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class FamilyMember(Base):
    __tablename__ = "family_members"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    is_admin: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


    # Relationships
    documents: Mapped[list["Document"]] = relationship(back_populates="uploader")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="actor")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="family_member")
    assigned_tasks: Mapped[list["Task"]] = relationship(
        back_populates="assignee", foreign_keys="[Task.assigned_to]"
    )
    created_tasks: Mapped[list["Task"]] = relationship(
        back_populates="creator", foreign_keys="[Task.created_by]"
    )
    assigned_patterns: Mapped[list["RecurringPattern"]] = relationship(
        back_populates="assignee", foreign_keys="[RecurringPattern.assigned_to]"
    )
    memories: Mapped[list["Memory"]] = relationship(back_populates="family_member")
    bug_reports: Mapped[list["BugReport"]] = relationship(back_populates="reporter")
    conversation_state: Mapped[Optional["ConversationState"]] = relationship(back_populates="family_member", uselist=False)
    salary_slips: Mapped[list["SalarySlip"]] = relationship(back_populates="family_member")
    utility_bills: Mapped[list["UtilityBill"]] = relationship(back_populates="family_member")


class Permission(Base):
    __tablename__ = "permissions"
    __table_args__ = (UniqueConstraint("role", "resource_type"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    resource_type: Mapped[str] = mapped_column(Text, nullable=False)
    can_read: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    can_write: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    uploaded_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("family_members.id"), nullable=True
    )
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    doc_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    vendor: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    amount: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(Text, server_default=text("'ILS'"))
    doc_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    display_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    doc_metadata: Mapped[Optional[dict]] = mapped_column(
        "metadata", JSONB, server_default=text("'{}'")
    )
    # Sprint 1: new columns (doc_type, vendor, doc_date, ai_summary, raw_text already exist)
    tags: Mapped[Optional[list]] = mapped_column(JSONB, server_default=text("'[]'"))
    confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric, server_default=text("0.0"))
    review_state: Mapped[Optional[str]] = mapped_column(Text, server_default=text("'pending'"))
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    # Relationships
    uploader: Mapped[Optional["FamilyMember"]] = relationship(back_populates="documents")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="document")
    tasks: Mapped[list["Task"]] = relationship(back_populates="source_document")
    facts: Mapped[list["DocumentFact"]] = relationship(back_populates="document", cascade="all, delete-orphan")
    salary_slip: Mapped[Optional["SalarySlip"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        uselist=False,
    )
    utility_bill: Mapped[Optional["UtilityBill"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        uselist=False,
    )
    contract: Mapped[Optional["Contract"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        uselist=False,
    )
    insurance_policy: Mapped[Optional["InsurancePolicy"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        uselist=False,
    )

    # Logical-to-physical property aliases (service/API layer names → physical columns)
    @property
    def document_type(self) -> Optional[str]:
        return self.doc_type

    @property
    def counterparty(self) -> Optional[str]:
        return self.vendor

    @property
    def source_date(self):
        return self.doc_date

    @property
    def summary(self) -> Optional[str]:
        return self.ai_summary


class DocumentFact(Base):
    """Flexible structured fact extracted from a document during ingestion."""
    __tablename__ = "document_facts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False
    )
    fact_type: Mapped[str] = mapped_column(Text, nullable=False)
    fact_key: Mapped[str] = mapped_column(Text, nullable=False)
    fact_value: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric, server_default=text("0.0"))
    source_excerpt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    # Relationships
    document: Mapped["Document"] = relationship(back_populates="facts")


class SalarySlip(Base):
    """Canonical typed salary-slip row derived from a raw document."""
    __tablename__ = "salary_slips"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, unique=True
    )
    family_member_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("family_members.id"), nullable=True
    )
    employee_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    employer_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pay_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pay_month: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(Text, server_default=text("'ILS'"))
    gross_salary: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    net_salary: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    net_to_pay: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    total_deductions: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    income_tax: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    national_insurance: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    health_tax: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    pension_employee: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    pension_employer: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    extraction_confidence: Mapped[Optional[Decimal]] = mapped_column(
        Numeric, server_default=text("0.0")
    )
    review_state: Mapped[Optional[str]] = mapped_column(Text, server_default=text("'pending'"))
    review_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_channel: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSONB, server_default=text("'{}'"))
    # Extended fields for richer agent context
    employee_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    employer_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tax_file_number: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    department: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    job_start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    job_percentage: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    bank_account: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bank_branch: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bank_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tax_bracket_percent: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    tax_credit_points: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    gross_for_tax: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    gross_for_national_insurance: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    marital_status: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    health_fund: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pension_fund_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    education_fund_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    employee_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    # Relationships
    document: Mapped["Document"] = relationship(back_populates="salary_slip")
    family_member: Mapped[Optional["FamilyMember"]] = relationship(back_populates="salary_slips")


class UtilityBill(Base):
    """Canonical typed utility-bill row derived from a raw document."""
    __tablename__ = "utility_bills"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, unique=True
    )
    family_member_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("family_members.id"), nullable=True
    )
    provider_slug: Mapped[str] = mapped_column(Text, nullable=False)
    provider_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    service_type: Mapped[str] = mapped_column(Text, nullable=False)
    account_number: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bill_number: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    issue_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    period_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    period_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    amount_due: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(Text, server_default=text("'ILS'"))
    extraction_confidence: Mapped[Optional[Decimal]] = mapped_column(
        Numeric, server_default=text("0.0")
    )
    review_state: Mapped[Optional[str]] = mapped_column(Text, server_default=text("'pending'"))
    review_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_channel: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSONB, server_default=text("'{}'"))
    # Extended fields for richer agent context
    total_with_vat: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    vat_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    consumption_kwh: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    payment_due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    payment_method: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    meter_number: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tariff_plan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    contract_number: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fixed_charges: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    kva_charge: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    savings_this_bill: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    savings_cumulative: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    service_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    document: Mapped["Document"] = relationship(back_populates="utility_bill")
    family_member: Mapped[Optional["FamilyMember"]] = relationship(back_populates="utility_bills")


class Contract(Base):
    """Canonical typed contract row derived from a raw document."""
    __tablename__ = "contracts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, unique=True
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("family_members.id"), nullable=False
    )
    source: Mapped[Optional[str]] = mapped_column(Text, server_default=text("'whatsapp'"))
    contract_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    counterparty: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parties: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    contract_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    amount: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(Text, server_default=text("'ILS'"))
    obligations: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    renewal_terms: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    penalty_clause: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    termination_clause: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    governing_law: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    document_reference: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric, server_default=text("0.0"))
    review_state: Mapped[Optional[str]] = mapped_column(Text, server_default=text("'pending'"))
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSONB, server_default=text("'{}'"))

    document: Mapped["Document"] = relationship(back_populates="contract")


class InsurancePolicy(Base):
    """Canonical typed insurance policy row derived from a raw document."""
    __tablename__ = "insurance_policies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, unique=True
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("family_members.id"), nullable=False
    )
    source: Mapped[Optional[str]] = mapped_column(Text, server_default=text("'whatsapp'"))
    insurance_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    insurer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    policy_number: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    insured_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    beneficiary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    coverage_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    coverage_limit: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    premium_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    premium_currency: Mapped[Optional[str]] = mapped_column(Text, server_default=text("'ILS'"))
    deductible_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric, nullable=True)
    policy_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric, server_default=text("0.0"))
    review_state: Mapped[Optional[str]] = mapped_column(Text, server_default=text("'pending'"))
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSONB, server_default=text("'{}'"))

    document: Mapped["Document"] = relationship(back_populates="insurance_policy")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True
    )
    category: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    currency: Mapped[Optional[str]] = mapped_column(Text, server_default=text("'ILS'"))
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    transaction_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    # Relationships
    document: Mapped[Optional["Document"]] = relationship(back_populates="transactions")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("family_members.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    resource_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resource_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    details: Mapped[Optional[dict]] = mapped_column(JSONB, server_default=text("'{}'"))
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    # Relationships
    actor: Mapped[Optional["FamilyMember"]] = relationship(back_populates="audit_logs")


class RecurringPattern(Base):
    __tablename__ = "recurring_patterns"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    assigned_to: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("family_members.id"), nullable=True
    )
    frequency: Mapped[str] = mapped_column(Text, nullable=False)
    day_of_month: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    month_of_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    next_due_date: Mapped[date] = mapped_column(Date, nullable=False)
    auto_create_days_before: Mapped[Optional[int]] = mapped_column(
        Integer, server_default=text("7")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    pattern_metadata: Mapped[Optional[dict]] = mapped_column(
        "metadata", JSONB, server_default=text("'{}'")
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    # Relationships
    assignee: Mapped[Optional["FamilyMember"]] = relationship(
        back_populates="assigned_patterns", foreign_keys=[assigned_to]
    )
    tasks: Mapped[list["Task"]] = relationship(back_populates="recurring_pattern")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'open'")
    )
    assigned_to: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("family_members.id"), nullable=True
    )
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("family_members.id"), nullable=True
    )
    source_document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True
    )
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(
        Text, server_default=text("'normal'")
    )
    recurring_pattern_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recurring_patterns.id"), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    task_metadata: Mapped[Optional[dict]] = mapped_column(
        "metadata", JSONB, server_default=text("'{}'")
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    # Relationships
    assignee: Mapped[Optional["FamilyMember"]] = relationship(
        back_populates="assigned_tasks", foreign_keys=[assigned_to]
    )
    creator: Mapped[Optional["FamilyMember"]] = relationship(
        back_populates="created_tasks", foreign_keys=[created_by]
    )
    source_document: Mapped[Optional["Document"]] = relationship(
        back_populates="tasks"
    )
    recurring_pattern: Mapped[Optional["RecurringPattern"]] = relationship(
        back_populates="tasks"
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    family_member_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("family_members.id"), nullable=True
    )
    message_in: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    message_out: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    intent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    conv_metadata: Mapped[Optional[dict]] = mapped_column(
        "metadata", JSONB, server_default=text("'{}'")
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    # Relationships
    family_member: Mapped[Optional["FamilyMember"]] = relationship(
        back_populates="conversations"
    )


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    family_member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("family_members.id"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    memory_type: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[Decimal] = mapped_column(Numeric, server_default=text("1.0"))
    last_accessed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    access_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    memory_metadata: Mapped[Optional[dict]] = mapped_column(
        "metadata", JSONB, server_default=text("'{}'")
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    # Relationships
    family_member: Mapped["FamilyMember"] = relationship(back_populates="memories")


class MemoryExclusion(Base):
    __tablename__ = "memory_exclusions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    pattern: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    exclusion_type: Mapped[str] = mapped_column(Text, nullable=False)
    family_member_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("family_members.id"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    # Relationships
    family_member: Mapped[Optional["FamilyMember"]] = relationship()


class BugReport(Base):
    __tablename__ = "bug_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    reported_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("family_members.id"), nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'open'")
    )
    priority: Mapped[str] = mapped_column(Text, server_default=text("'normal'"))
    bug_metadata: Mapped[Optional[dict]] = mapped_column(
        "metadata", JSONB, server_default=text("'{}'")
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    reporter: Mapped["FamilyMember"] = relationship(back_populates="bug_reports")


class ConversationState(Base):
    __tablename__ = "conversation_state"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    family_member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("family_members.id"), unique=True, nullable=False)
    last_intent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_entity_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    last_action: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pending_confirmation: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    pending_action: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    context: Mapped[Optional[dict]] = mapped_column(JSONB, server_default=text("'{}'"))
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    family_member: Mapped["FamilyMember"] = relationship(back_populates="conversation_state", uselist=False)


class CanonicalFact(Base):
    __tablename__ = "canonical_facts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    subject_member_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("family_members.id"), nullable=True
    )
    location_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fact_key: Mapped[str] = mapped_column(Text, nullable=False)
    fact_value: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("family_members.id"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    fact_metadata: Mapped[Optional[dict]] = mapped_column(
        "metadata", JSONB, server_default=text("'{}'")
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
