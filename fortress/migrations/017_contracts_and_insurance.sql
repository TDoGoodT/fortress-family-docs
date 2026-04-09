BEGIN;

-- Canonical table for contracts (rental, employment, service, etc.)
CREATE TABLE IF NOT EXISTS contracts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    uploaded_by UUID NOT NULL REFERENCES family_members(id),
    source TEXT NOT NULL DEFAULT 'whatsapp',

    -- Core fields
    contract_type TEXT,              -- rental, employment, service, purchase, etc.
    counterparty TEXT,               -- the other party
    parties TEXT,                    -- all named parties, comma-separated
    contract_date DATE,              -- signing/issue date
    start_date DATE,                 -- effective start
    end_date DATE,                   -- expiration date
    amount DECIMAL,                  -- total value or periodic payment
    currency TEXT DEFAULT 'ILS',

    -- Clause extraction
    obligations TEXT,                -- key obligations summary
    renewal_terms TEXT,              -- auto-renewal conditions
    penalty_clause TEXT,             -- breach/early termination penalties
    termination_clause TEXT,         -- termination conditions
    governing_law TEXT,              -- jurisdiction

    -- Metadata
    document_reference TEXT,         -- contract number or reference
    confidence DECIMAL DEFAULT 0.0,
    review_state TEXT DEFAULT 'pending',
    raw_payload JSONB DEFAULT '{}',

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_contracts_document_id ON contracts(document_id);
CREATE INDEX IF NOT EXISTS idx_contracts_uploaded_by ON contracts(uploaded_by);
CREATE INDEX IF NOT EXISTS idx_contracts_end_date ON contracts(end_date);

-- Canonical table for insurance policies
CREATE TABLE IF NOT EXISTS insurance_policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    uploaded_by UUID NOT NULL REFERENCES family_members(id),
    source TEXT NOT NULL DEFAULT 'whatsapp',

    -- Core fields
    insurance_type TEXT,             -- health, car, home, life, travel, etc.
    insurer TEXT,                    -- insurance company name
    policy_number TEXT,              -- policy identifier
    insured_name TEXT,               -- who is insured
    beneficiary TEXT,                -- named beneficiary

    -- Coverage
    coverage_description TEXT,       -- what the policy covers
    coverage_limit DECIMAL,          -- max coverage amount
    premium_amount DECIMAL,          -- periodic premium
    premium_currency TEXT DEFAULT 'ILS',
    deductible_amount DECIMAL,       -- self-participation

    -- Dates
    policy_date DATE,                -- issue date
    start_date DATE,                 -- coverage start
    end_date DATE,                   -- coverage expiry

    -- Metadata
    confidence DECIMAL DEFAULT 0.0,
    review_state TEXT DEFAULT 'pending',
    raw_payload JSONB DEFAULT '{}',

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_insurance_policies_document_id ON insurance_policies(document_id);
CREATE INDEX IF NOT EXISTS idx_insurance_policies_uploaded_by ON insurance_policies(uploaded_by);
CREATE INDEX IF NOT EXISTS idx_insurance_policies_end_date ON insurance_policies(end_date);
CREATE INDEX IF NOT EXISTS idx_insurance_policies_policy_number ON insurance_policies(policy_number);

COMMIT;
