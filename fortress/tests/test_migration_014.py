"""Migration tests for 014_utility_bills.sql."""
from __future__ import annotations


def _read_migration() -> str:
    with open("migrations/014_utility_bills.sql", encoding="utf-8") as f:
        return f.read()


def test_migration_wrapped_in_transaction():
    sql = _read_migration()
    assert "BEGIN;" in sql
    assert "COMMIT;" in sql


def test_migration_creates_utility_bills_table():
    sql = _read_migration()
    assert "CREATE TABLE IF NOT EXISTS utility_bills" in sql


def test_migration_has_required_columns():
    sql = _read_migration()
    assert "document_id UUID NOT NULL UNIQUE REFERENCES documents(id)" in sql
    assert "provider_slug TEXT NOT NULL" in sql
    assert "service_type TEXT NOT NULL" in sql
    assert "account_number TEXT" in sql
    assert "bill_number TEXT" in sql
    assert "issue_date DATE" in sql
    assert "period_start DATE" in sql
    assert "period_end DATE" in sql
    assert "amount_due DECIMAL" in sql
    assert "review_state TEXT DEFAULT 'pending'" in sql


def test_migration_has_indexes():
    sql = _read_migration()
    assert "idx_utility_bills_document_id" in sql
    assert "idx_utility_bills_provider_service" in sql
    assert "idx_utility_bills_account_number" in sql


def test_orm_utility_bill_model_exists():
    from src.models.schema import UtilityBill

    assert hasattr(UtilityBill, "document_id")
    assert hasattr(UtilityBill, "provider_slug")
    assert hasattr(UtilityBill, "service_type")
    assert hasattr(UtilityBill, "account_number")
    assert hasattr(UtilityBill, "bill_number")
