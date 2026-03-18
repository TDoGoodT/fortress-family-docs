-- 035_core_account_projection_normalization.sql
--
-- Version Authority (explicit):
-- - fortress.core.account-domain.v1
-- - fortress.core.event-ledger.v1
-- - fortress.project.version-governance.v1
--
-- Path A / Phase 2:
-- - define forward-only normalized account projection helper
-- - ledger-derived only
-- - historical compatibility is handled separately

BEGIN;

CREATE OR REPLACE VIEW core.ledger_projection_account_created_normalized_forward AS
SELECT
    el.event_id,
    el.event_timestamp,
    el.aggregate_id AS account_id,
    CASE
        WHEN NULLIF(el.payload ->> 'household_id', '') IS NULL THEN NULL::uuid
        ELSE (el.payload ->> 'household_id')::uuid
    END AS household_id,
    NULLIF(el.payload ->> 'account_label', '') AS account_label,
    NULLIF(el.payload ->> 'account_kind', '') AS account_kind,
    el.event_timestamp AS created_at
FROM public.event_ledger el
WHERE el.aggregate_type = 'core.account'
  AND el.event_type = 'core.account.created'
  AND el.causation_id IS NOT NULL
  AND NULLIF(el.payload ->> 'handoff_request_id', '') IS NOT NULL
  AND NULLIF(el.payload ->> 'normalized_record_id', '') IS NOT NULL
  AND NULLIF(el.payload ->> 'schema_version', '') IS NOT NULL
  AND NULLIF(el.payload ->> 'canonical_record_type', '') IS NULL
  AND (
      NULLIF(el.payload ->> 'account_id', '') IS NULL
      OR (el.payload ->> 'account_id')::uuid = el.aggregate_id
  )
  AND NULLIF(el.payload ->> 'household_id', '') IS NOT NULL
  AND NULLIF(el.payload ->> 'account_label', '') IS NOT NULL
  AND (el.payload ->> 'account_kind') IN (
      'cash_account',
      'investment_account',
      'retirement_account'
  );

COMMENT ON VIEW core.ledger_projection_account_created_normalized_forward IS
'Forward-only Path A helper: derive normalized core.account create rows from public.event_ledger only. Historical compatibility is excluded from this helper.';

INSERT INTO public.schema_migrations(version)
VALUES ('035_core_account_projection_normalization.sql');

COMMIT;
