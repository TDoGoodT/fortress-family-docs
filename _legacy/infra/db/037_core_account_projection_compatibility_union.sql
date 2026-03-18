-- 037_core_account_projection_compatibility_union.sql
--
-- Version Authority (explicit):
-- - fortress.core.account-domain.v1
-- - fortress.core.event-ledger.v1
-- - fortress.project.version-governance.v1
--
-- Path A / Phase 2:
-- - final canonical account projection
-- - stable canonical object name
-- - forward normalized rows + explicit historical-only compatibility rows

BEGIN;

CREATE OR REPLACE VIEW core.ledger_projection_account_created AS
SELECT
    event_id,
    event_timestamp,
    account_id,
    household_id,
    account_label,
    account_kind,
    created_at
FROM core.ledger_projection_account_created_normalized_forward

UNION ALL

SELECT
    event_id,
    event_timestamp,
    account_id,
    household_id,
    account_label,
    account_kind,
    created_at
FROM core.ledger_projection_account_created_historical_compatibility;

COMMENT ON VIEW core.ledger_projection_account_created IS
'Canonical Path A projection for core.account.created. Forward rows derive from normalized ledger-only events; historical-only rows derive from explicit read-only compatibility bridge.';

INSERT INTO public.schema_migrations(version)
VALUES ('037_core_account_projection_compatibility_union.sql');

COMMIT;
