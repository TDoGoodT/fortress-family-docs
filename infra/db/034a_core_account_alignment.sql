-- 034a_core_account_alignment.sql
--
-- Version Authority (explicit):
-- - fortress.core.account-domain.v1
-- - fortress.core.database-blueprint.v1
-- - fortress.project.version-governance.v1
-- - fortress.project.dependency-model.v2
--
-- Path A / Phase 2:
-- - Canonical Aggregate Schema Alignment
-- - Introduce core.account canonical write surface
-- - Minimal MVP aggregate

BEGIN;

CREATE TABLE IF NOT EXISTS core.account (
    account_id uuid PRIMARY KEY,
    household_id uuid NOT NULL,
    account_label text NOT NULL,
    account_kind text NOT NULL,
    created_at timestamptz NOT NULL
);

COMMENT ON TABLE core.account IS
'Canonical aggregate table for core.account MVP. Minimal identity-only account surface.';

INSERT INTO public.schema_migrations(version)
VALUES ('034a_core_account_alignment.sql');

COMMIT;
