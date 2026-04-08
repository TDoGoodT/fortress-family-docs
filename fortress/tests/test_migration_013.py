"""Migration tests for 013_salary_slips.sql."""
from __future__ import annotations


def _read_migration() -> str:
    with open("migrations/013_salary_slips.sql", encoding="utf-8") as f:
        return f.read()


def test_migration_wrapped_in_transaction():
    sql = _read_migration()
    assert "BEGIN;" in sql
    assert "COMMIT;" in sql


def test_migration_creates_salary_slips_table():
    sql = _read_migration()
    assert "CREATE TABLE IF NOT EXISTS salary_slips" in sql


def test_migration_has_required_columns():
    sql = _read_migration()
    assert "document_id UUID NOT NULL UNIQUE REFERENCES documents(id)" in sql
    assert "family_member_id UUID REFERENCES family_members(id)" in sql
    assert "employee_name TEXT" in sql
    assert "employer_name TEXT" in sql
    assert "pay_year INTEGER" in sql
    assert "pay_month INTEGER" in sql
    assert "gross_salary DECIMAL" in sql
    assert "net_salary DECIMAL" in sql
    assert "review_state TEXT DEFAULT 'pending'" in sql
    assert "raw_payload JSONB DEFAULT '{}'" in sql


def test_migration_has_indexes():
    sql = _read_migration()
    assert "idx_salary_slips_document_id" in sql
    assert "idx_salary_slips_family_member_id" in sql
    assert "idx_salary_slips_pay_period" in sql


def test_orm_salary_slip_model_exists():
    from src.models.schema import SalarySlip

    assert hasattr(SalarySlip, "document_id")
    assert hasattr(SalarySlip, "family_member_id")
    assert hasattr(SalarySlip, "gross_salary")
    assert hasattr(SalarySlip, "net_salary")
    assert hasattr(SalarySlip, "raw_payload")
