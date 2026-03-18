-- 036_core_account_historical_compatibility_bridge.sql
--
-- Version Authority (explicit):
-- - fortress.core.account-domain.v1
-- - fortress.core.event-ledger.v1
-- - fortress.project.version-governance.v1
--
-- Path A / Phase 2:
-- - explicit historical-only compatibility bridge
-- - additive, read-only, deterministic
-- - for pre-normalization account history only

BEGIN;

CREATE OR REPLACE VIEW core.ledger_account_created_historical_compatibility_evidence AS
SELECT
    created_event.event_id AS created_event_id,
    created_event.aggregate_id AS account_id,
    created_event.event_timestamp,
    backfill_event.event_id AS backfill_event_id,
    backfill_event.causation_id AS reconstructed_causation_id,
    ARRAY_REMOVE(ARRAY[
        CASE WHEN created_event.causation_id IS NULL THEN 'null_causation_id' END,
        CASE WHEN backfill_event.event_id IS NOT NULL THEN 'causation_backfill_linked' END,
        CASE
            WHEN NULLIF(created_event.payload ->> 'account_id', '') IS NULL
            THEN 'payload_account_id_missing'
        END,
        CASE
            WHEN NULLIF(created_event.payload ->> 'canonical_record_type', '') IS NOT NULL
            THEN 'legacy_canonical_record_type_present'
        END
    ], NULL) AS compatibility_reasons
FROM public.event_ledger created_event
LEFT JOIN public.event_ledger backfill_event
    ON backfill_event.aggregate_type = 'core.account'
   AND backfill_event.event_type = 'core.account.causation_backfill'
   AND backfill_event.aggregate_id = created_event.aggregate_id
   AND backfill_event.payload ->> 'original_event_id' = created_event.event_id::text
WHERE created_event.aggregate_type = 'core.account'
  AND created_event.event_type = 'core.account.created'
  AND created_event.causation_id IS NULL
  AND backfill_event.event_id IS NOT NULL
  AND NULLIF(created_event.payload ->> 'household_id', '') IS NOT NULL
  AND NULLIF(created_event.payload ->> 'account_label', '') IS NOT NULL
  AND (created_event.payload ->> 'account_kind') IN (
      'cash_account',
      'investment_account',
      'retirement_account'
  )
  AND NULLIF(created_event.payload ->> 'schema_version', '') IS NOT NULL;

COMMENT ON VIEW core.ledger_account_created_historical_compatibility_evidence IS
'Historical-only compatibility evidence for pre-normalization core.account.created rows that require explicit read-only interpretation under Path A.';

CREATE OR REPLACE VIEW core.ledger_projection_account_created_historical_compatibility AS
SELECT
    created_event.event_id,
    created_event.event_timestamp,
    created_event.aggregate_id AS account_id,
    CASE
        WHEN NULLIF(created_event.payload ->> 'household_id', '') IS NULL THEN NULL::uuid
        ELSE (created_event.payload ->> 'household_id')::uuid
    END AS household_id,
    NULLIF(created_event.payload ->> 'account_label', '') AS account_label,
    NULLIF(created_event.payload ->> 'account_kind', '') AS account_kind,
    created_event.event_timestamp AS created_at
FROM public.event_ledger created_event
INNER JOIN core.ledger_account_created_historical_compatibility_evidence compat
    ON compat.created_event_id = created_event.event_id;

COMMENT ON VIEW core.ledger_projection_account_created_historical_compatibility IS
'Historical-only compatibility bridge for pre-normalization core.account.created rows. Read-only, additive, and excluded from forward account processing.';

INSERT INTO public.schema_migrations(version)
VALUES ('036_core_account_historical_compatibility_bridge.sql');

COMMIT;
