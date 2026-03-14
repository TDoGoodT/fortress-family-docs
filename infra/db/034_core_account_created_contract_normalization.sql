-- 034_core_account_created_contract_normalization.sql
--
-- Version Authority (explicit):
-- - fortress.core.account-domain.v1
-- - fortress.core.event-ledger.v1
-- - fortress.project.version-governance.v1
-- - fortress.project.dependency-model.v2
--
-- Path A / Phase 2:
-- - normalize core.account contract surface to canonical envelope doctrine
-- - read-only contract view only
-- - no direct aggregate mutation
-- - no event emission

BEGIN;

DROP VIEW IF EXISTS core.ledger_projection_account_created;
DROP VIEW IF EXISTS core.ledger_contract_account_created;

CREATE OR REPLACE VIEW core.ledger_contract_account_created AS
SELECT
    'core.account'::text AS aggregate_type,
    q.target_entity_id AS aggregate_id,
    'core.account.created'::text AS event_type,
    jsonb_build_object(
        'account_id', q.target_entity_id,
        'handoff_request_id', q.handoff_request_id,
        'normalized_record_id', q.normalized_record_id,
        'run_id', q.run_id,
        'source_id', q.source_id,
        'household_id', q.handoff_payload ->> 'household_id',
        'account_label', q.handoff_payload ->> 'account_label',
        'account_kind', q.handoff_payload ->> 'account_kind',
        'schema_version', q.schema_version
    ) AS payload,
    'system'::text AS actor_type,
    '00000000-0000-7000-8000-00000000000c'::uuid AS actor_id,
    'ZONE_A'::text AS zone_context,
    q.run_id AS correlation_id,
    q.handoff_request_id AS causation_id,
    q.requested_at AS event_timestamp,
    NULL::timestamptz AS valid_timestamp,
    encode(
        digest(
            concat_ws(
                '|',
                q.run_id::text,
                'core.account',
                q.target_entity_id::text,
                'core.account.created',
                md5(
                    jsonb_build_object(
                        'account_id', q.target_entity_id,
                        'handoff_request_id', q.handoff_request_id,
                        'normalized_record_id', q.normalized_record_id,
                        'run_id', q.run_id,
                        'source_id', q.source_id,
                        'household_id', q.handoff_payload ->> 'household_id',
                        'account_label', q.handoff_payload ->> 'account_label',
                        'account_kind', q.handoff_payload ->> 'account_kind',
                        'schema_version', q.schema_version
                    )::text
                )
            ),
            'sha256'
        ),
        'hex'
    ) AS emit_dedup_key
FROM core.canonical_handoff_processing_queue q
WHERE q.already_receipted = false
  AND q.target_entity_id IS NOT NULL
  AND lower(q.target_entity_type) IN ('account', 'core.account')
  AND NULLIF(q.handoff_payload ->> 'household_id', '') IS NOT NULL
  AND NULLIF(q.handoff_payload ->> 'account_label', '') IS NOT NULL
  AND (q.handoff_payload ->> 'account_kind') IN (
      'cash_account',
      'investment_account',
      'retirement_account'
  )
  AND q.schema_version IS NOT NULL;

COMMENT ON VIEW core.ledger_contract_account_created IS
'Contract: proposed event_ledger row(s) for core.account.created. Read-only. Emits canonical envelope and account payload under Path A normalization.';

INSERT INTO public.schema_migrations(version)
VALUES ('034_core_account_created_contract_normalization.sql');

COMMIT;
