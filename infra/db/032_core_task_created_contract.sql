-- 032_core_task_created_contract.sql
--
-- Version Authority (explicit):
-- - fortress.core.task-domain.v1
-- - fortress.core.database-blueprint.v1
-- - fortress.core.event-ledger.v1
-- - fortress.project.version-governance.v1
-- - fortress.project.dependency-model.v2
--
-- Phase 5B:
-- - core.task.created contract
-- - MVP event only
--
-- Scope:
-- - Read-only contract view
-- - Deterministic payload
-- - Status enforced as 'open'

BEGIN;

CREATE OR REPLACE VIEW core.ledger_contract_task_created AS
SELECT
    'core.task'::text AS aggregate_type,
    q.target_entity_id AS aggregate_id,
    'core.task.created'::text AS event_type,

    jsonb_build_object(
        'task_id', q.target_entity_id,
        'handoff_request_id', q.handoff_request_id,
        'normalized_record_id', q.normalized_record_id,
        'run_id', q.run_id,
        'source_id', q.source_id,
        'household_id', q.handoff_payload ->> 'household_id',
        'title', q.handoff_payload ->> 'title',
        'status', 'open',
        'canonical_record_type', q.canonical_record_type,
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
                'core.task',
                q.target_entity_id::text,
                'core.task.created',
                md5(
                    jsonb_build_object(
                        'task_id', q.target_entity_id,
                        'handoff_request_id', q.handoff_request_id,
                        'normalized_record_id', q.normalized_record_id,
                        'run_id', q.run_id,
                        'source_id', q.source_id,
                        'household_id', q.handoff_payload ->> 'household_id',
                        'title', q.handoff_payload ->> 'title',
                        'status', 'open',
                        'canonical_record_type', q.canonical_record_type,
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
  AND lower(q.target_entity_type) IN ('task','core.task');

COMMENT ON VIEW core.ledger_contract_task_created IS
'Contract surface proposing core.task.created events for eligible task handoffs.';

INSERT INTO public.schema_migrations(version)
VALUES ('032_core_task_created_contract.sql');

COMMIT;
