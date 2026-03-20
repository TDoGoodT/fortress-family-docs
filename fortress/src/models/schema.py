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
    source: Mapped[str] = mapped_column(Text, nullable=False)
    doc_metadata: Mapped[Optional[dict]] = mapped_column(
        "metadata", JSONB, server_default=text("'{}'")
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )

    # Relationships
    uploader: Mapped[Optional["FamilyMember"]] = relationship(back_populates="documents")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="document")
    tasks: Mapped[list["Task"]] = relationship(back_populates="source_document")


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
