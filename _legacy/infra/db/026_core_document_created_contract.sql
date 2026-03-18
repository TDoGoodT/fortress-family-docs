-- 026_core_document_created_contract.sql
--
-- Version Authority (explicit):
-- - fortress.core.document-domain.v1
-- - fortress.core.database-blueprint.v1
-- - fortress.core.event-ledger.v1
-- - fortress.project.version-governance.v1
-- - fortress.project.dependency-model.v2
--
-- Phase 4B2:
-- - First canonical write contract
-- - Document create-only
-- - Views only (read-only contract)
--
-- Scope:
-- - Define contract surface for core.document.created
-- - Deterministic mapping from core.canonical_handoff_processing_queue
-- - No runtime processor code
-- - No direct inserts into core.document
-- - No receipt mutation
-- - No update semantics
-- - No non-Document targets
-- - No triggers
-- - No functions
--
-- Contract rule:
-- - Only handoffs explicitly targeting Document are eligible
-- - target_entity_id must be present; document_id is never invented here

BEGIN;

CREATE OR REPLACE VIEW core.ledger_contract_document_created AS
SELECT
    'core.document'::text AS aggregate_type,
    q.target_entity_id AS aggregate_id,
    'core.document.created'::text AS event_type,
    jsonb_build_object(
        'document_id', q.target_entity_id,
        'handoff_request_id', q.handoff_request_id,
        'normalized_record_id', q.normalized_record_id,
        'run_id', q.run_id,
        'source_id', q.source_id,
        'document_type', q.handoff_payload ->> 'document_type',
        'title', q.handoff_payload ->> 'title',
        'source_uri', q.handoff_payload ->> 'source_uri',
        'household_id', q.handoff_payload ->> 'household_id',
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
                'core.document',
                q.target_entity_id::text,
                'core.document.created',
                md5(
                    jsonb_build_object(
                        'document_id', q.target_entity_id,
                        'handoff_request_id', q.handoff_request_id,
                        'normalized_record_id', q.normalized_record_id,
                        'run_id', q.run_id,
                        'source_id', q.source_id,
                        'document_type', q.handoff_payload ->> 'document_type',
                        'title', q.handoff_payload ->> 'title',
                        'source_uri', q.handoff_payload ->> 'source_uri',
                        'household_id', q.handoff_payload ->> 'household_id',
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
  AND lower(q.target_entity_type) IN ('document', 'core.document');

COMMENT ON VIEW core.ledger_contract_document_created IS
'Contract: proposed event_ledger row(s) for core.document.created. Read-only. Document create-only. Filters only explicit Document handoffs with non-null target_entity_id.';

INSERT INTO public.schema_migrations(version)
VALUES ('026_core_document_created_contract.sql');

COMMIT;
