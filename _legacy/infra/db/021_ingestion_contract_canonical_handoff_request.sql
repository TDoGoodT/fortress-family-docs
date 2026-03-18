-- 021_ingestion_contract_canonical_handoff_request.sql
--
-- Version Authority (explicit):
-- - fortress.ingestion.pipeline-architecture.v3
-- - fortress.core.event-ledger.v1
-- - fortress.project.version-governance.v1
-- - fortress.project.dependency-model.v2
--
-- Scope:
-- - Views only (read-only contract). No triggers, no functions, no schema changes.
-- - No event writes, only defines "what should be written".
--
-- Naming:
-- - ingestion.ledger_contract_* : contract surfaces (what-to-write) for event_ledger.

BEGIN;

CREATE OR REPLACE VIEW ingestion.ledger_contract_canonical_handoff_request_created AS
SELECT
  'ingestion.canonical_handoff_request'::text          AS aggregate_type,
  chr.handoff_request_id                               AS aggregate_id,
  'ingestion.canonical_handoff_request.created'::text  AS event_type,

  jsonb_build_object(
    'handoff_request_id', chr.handoff_request_id,
    'run_id', chr.run_id,
    'normalized_record_id', chr.normalized_record_id,
    'target_entity_type', chr.target_entity_type,
    'target_entity_id', chr.target_entity_id,
    'handoff_sha256', encode(chr.handoff_sha256, 'hex'),
    'handoff_payload', chr.handoff_payload
  )                                                    AS payload,

  'system'::text                                       AS actor_type,
  chr.run_id                                           AS actor_id,
  'ingestion'::text                                    AS zone_context,
  chr.run_id                                           AS correlation_id,
  NULL::uuid                                           AS causation_id,
  chr.created_at                                       AS event_timestamp,
  NULL::timestamptz                                    AS valid_timestamp
FROM ingestion.canonical_handoff_request chr;

COMMENT ON VIEW ingestion.ledger_contract_canonical_handoff_request_created IS
'Contract: proposed event_ledger row(s) for ingestion.canonical_handoff_request creation. Read-only.';

INSERT INTO public.schema_migrations(version)
VALUES ('021_ingestion_contract_canonical_handoff_request.sql');

COMMIT;
