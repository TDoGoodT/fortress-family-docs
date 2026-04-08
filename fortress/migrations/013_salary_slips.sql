BEGIN;

CREATE TABLE IF NOT EXISTS salary_slips (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL UNIQUE REFERENCES documents(id) ON DELETE CASCADE,
    family_member_id UUID REFERENCES family_members(id),
    employee_name TEXT,
    employer_name TEXT,
    pay_year INTEGER,
    pay_month INTEGER,
    currency TEXT DEFAULT 'ILS',
    gross_salary DECIMAL,
    net_salary DECIMAL,
    net_to_pay DECIMAL,
    total_deductions DECIMAL,
    income_tax DECIMAL,
    national_insurance DECIMAL,
    health_tax DECIMAL,
    pension_employee DECIMAL,
    pension_employer DECIMAL,
    extraction_confidence DECIMAL DEFAULT 0.0,
    review_state TEXT DEFAULT 'pending',
    review_reason TEXT,
    source_channel TEXT,
    raw_payload JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_salary_slips_document_id
    ON salary_slips(document_id);

CREATE INDEX IF NOT EXISTS idx_salary_slips_family_member_id
    ON salary_slips(family_member_id);

CREATE INDEX IF NOT EXISTS idx_salary_slips_pay_period
    ON salary_slips(pay_year, pay_month);

CREATE INDEX IF NOT EXISTS idx_salary_slips_employer_name
    ON salary_slips(employer_name);

COMMIT;
