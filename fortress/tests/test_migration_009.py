"""Migration tests for 009_document_intake.sql — P8 schema backward compatibility."""
from __future__ import annotations

import re


def _read_migration() -> str:
    with open("migrations/009_document_intake.sql", encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Migration SQL structure
# ---------------------------------------------------------------------------

def test_migration_wrapped_in_transaction():
    sql = _read_migration()
    assert "BEGIN;" in sql
    assert "COMMIT;" in sql


def test_migration_uses_if_not_exists_for_idempotency():
    sql = _read_migration()
    # All ADD COLUMN and CREATE TABLE statements use IF NOT EXISTS
    assert "ADD COLUMN IF NOT EXISTS tags" in sql
    assert "ADD COLUMN IF NOT EXISTS confidence" in sql
    assert "ADD COLUMN IF NOT EXISTS review_state" in sql
    assert "CREATE TABLE IF NOT EXISTS document_facts" in sql


# ---------------------------------------------------------------------------
# P8: Schema Backward Compatibility — no drops or renames
# ---------------------------------------------------------------------------

def test_p8_no_drop_column_statements():
    """P8: Migration must not drop any existing columns."""
    sql = _read_migration().upper()
    assert "DROP COLUMN" not in sql


def test_p8_no_rename_column_statements():
    """P8: Migration must not rename any existing columns."""
    sql = _read_migration().upper()
    assert "RENAME COLUMN" not in sql


def test_p8_no_alter_type_statements():
    """P8: Migration must not alter the type of existing columns."""
    sql = _read_migration().upper()
    assert "ALTER COLUMN" not in sql


def test_p8_no_drop_table_statements():
    """P8: Migration must not drop any existing tables."""
    sql = _read_migration().upper()
    assert "DROP TABLE" not in sql


# ---------------------------------------------------------------------------
# New columns have correct defaults
# ---------------------------------------------------------------------------

def test_tags_column_has_empty_array_default():
    sql = _read_migration()
    assert "tags JSONB DEFAULT '[]'" in sql


def test_confidence_column_has_zero_default():
    sql = _read_migration()
    assert "confidence DECIMAL DEFAULT 0.0" in sql


def test_review_state_column_has_pending_default():
    sql = _read_migration()
    assert "review_state TEXT DEFAULT 'pending'" in sql


# ---------------------------------------------------------------------------
# document_facts table schema
# ---------------------------------------------------------------------------

def test_document_facts_has_uuid_primary_key():
    sql = _read_migration()
    assert "id UUID PRIMARY KEY DEFAULT gen_random_uuid()" in sql


def test_document_facts_has_foreign_key_to_documents():
    sql = _read_migration()
    assert "document_id UUID NOT NULL REFERENCES documents(id)" in sql


def test_document_facts_has_required_columns():
    sql = _read_migration()
    assert "fact_type TEXT NOT NULL" in sql
    assert "fact_key TEXT NOT NULL" in sql
    assert "fact_value TEXT NOT NULL" in sql
    assert "confidence DECIMAL DEFAULT 0.0" in sql
    assert "source_excerpt TEXT" in sql
    assert "created_at TIMESTAMPTZ DEFAULT now()" in sql


# ---------------------------------------------------------------------------
# Indexes
# ---------------------------------------------------------------------------

def test_index_on_document_facts_document_id():
    sql = _read_migration()
    assert "idx_document_facts_document_id ON document_facts(document_id)" in sql


def test_index_on_document_facts_fact_key():
    sql = _read_migration()
    assert "idx_document_facts_fact_key ON document_facts(fact_key)" in sql


# ---------------------------------------------------------------------------
# ORM model consistency
# ---------------------------------------------------------------------------

def test_orm_document_has_new_columns():
    """Document ORM model should have tags, confidence, review_state columns."""
    from src.models.schema import Document
    assert hasattr(Document, "tags")
    assert hasattr(Document, "confidence")
    assert hasattr(Document, "review_state")


def test_orm_document_has_property_aliases():
    """Document ORM model should have logical property aliases."""
    from src.models.schema import Document
    assert hasattr(Document, "document_type")
    assert hasattr(Document, "counterparty")
    assert hasattr(Document, "source_date")
    assert hasattr(Document, "summary")


def test_orm_document_fact_model_exists():
    """DocumentFact ORM model should exist with correct attributes."""
    from src.models.schema import DocumentFact
    assert hasattr(DocumentFact, "id")
    assert hasattr(DocumentFact, "document_id")
    assert hasattr(DocumentFact, "fact_type")
    assert hasattr(DocumentFact, "fact_key")
    assert hasattr(DocumentFact, "fact_value")
    assert hasattr(DocumentFact, "confidence")
    assert hasattr(DocumentFact, "source_excerpt")


def test_orm_document_has_facts_relationship():
    """Document should have a facts relationship to DocumentFact."""
    from src.models.schema import Document
    assert hasattr(Document, "facts")
