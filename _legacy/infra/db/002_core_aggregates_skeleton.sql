-- Core aggregates skeleton (Phase 1)
-- NOTE: All IDs MUST be UUIDv7 generated app-side in Phase 1 (no DB defaults)

CREATE TABLE IF NOT EXISTS person (
  person_id UUID PRIMARY KEY,
  display_name TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS household (
  household_id UUID PRIMARY KEY,
  display_name TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS account (
  account_id UUID PRIMARY KEY,
  household_id UUID REFERENCES household(household_id),
  account_type TEXT,
  display_name TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS asset (
  asset_id UUID PRIMARY KEY,
  household_id UUID REFERENCES household(household_id),
  asset_type TEXT,
  display_name TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS liability (
  liability_id UUID PRIMARY KEY,
  household_id UUID REFERENCES household(household_id),
  liability_type TEXT,
  display_name TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS transaction (
  transaction_id UUID PRIMARY KEY,
  account_id UUID REFERENCES account(account_id),
  occurred_at TIMESTAMPTZ,
  amount NUMERIC,
  currency TEXT,
  description TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS document (
  document_id UUID PRIMARY KEY,
  household_id UUID REFERENCES household(household_id),
  document_type TEXT,
  title TEXT,
  source_uri TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS contract (
  contract_id UUID PRIMARY KEY,
  household_id UUID REFERENCES household(household_id),
  contract_type TEXT,
  title TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Relationship skeleton (generic edge)
CREATE TABLE IF NOT EXISTS relationship (
  relationship_id UUID PRIMARY KEY,
  from_entity_type TEXT NOT NULL,
  from_entity_id UUID NOT NULL,
  to_entity_type TEXT NOT NULL,
  to_entity_id UUID NOT NULL,
  relationship_type TEXT NOT NULL,
  valid_from TIMESTAMPTZ,
  valid_to TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
