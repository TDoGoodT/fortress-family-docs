BEGIN;

CREATE TABLE canonical_facts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_member_id UUID REFERENCES family_members(id),
    location_key TEXT,
    fact_key TEXT NOT NULL,
    fact_value TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN (
        'basic_personal', 'household_access', 'financial', 'health'
    )),
    created_by UUID REFERENCES family_members(id),
    is_active BOOLEAN DEFAULT true,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_canonical_facts_subject_key ON canonical_facts(subject_member_id, fact_key, created_at DESC);
CREATE INDEX idx_canonical_facts_location_key ON canonical_facts(location_key, fact_key, created_at DESC);

COMMIT;
