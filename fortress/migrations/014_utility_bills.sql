BEGIN;

CREATE TABLE IF NOT EXISTS utility_bills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL UNIQUE REFERENCES documents(id) ON DELETE CASCADE,
    family_member_id UUID REFERENCES family_members(id),
    provider_slug TEXT NOT NULL,
    provider_name TEXT,
    service_type TEXT NOT NULL,
    account_number TEXT,
    bill_number TEXT,
    issue_date DATE,
    period_start DATE,
    period_end DATE,
    amount_due DECIMAL,
    currency TEXT DEFAULT 'ILS',
    extraction_confidence DECIMAL DEFAULT 0.0,
    review_state TEXT DEFAULT 'pending',
    review_reason TEXT,
    source_channel TEXT,
    raw_payload JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_utility_bills_document_id
    ON utility_bills(document_id);

CREATE INDEX IF NOT EXISTS idx_utility_bills_provider_service
    ON utility_bills(provider_slug, service_type);

CREATE INDEX IF NOT EXISTS idx_utility_bills_account_number
    ON utility_bills(account_number);

COMMIT;
