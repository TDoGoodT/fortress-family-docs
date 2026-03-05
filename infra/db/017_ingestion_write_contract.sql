-- 017_ingestion_write_contract.sql
--
-- Version Authority (explicit):
-- - fortress.ingestion.pipeline-architecture.v3
-- - fortress.core.event-ledger.v1
-- - fortress.project.version-governance.v1
-- - fortress.project.dependency-model.v2
--
-- Scope / Out of Scope:
-- - Views only (read-only contract). No materialized views.
-- - No triggers, no functions, no schema changes, no data fixes.
-- - No event writes, only defines "what should be written".
--
-- Ordering / Time Semantics:
-- - event_timestamp is semantic time for events we propose.
--
-- Naming:
-- - ingestion.ledger_contract_* : contract surfaces (what-to-write) for event_ledger.

BEGIN;

-- Contract View: run created -> proposed event row
CREATE OR REPLACE VIEW ingestion.ledger_contract_run_created AS
SELECT
  'ingestion.run'::text                 AS aggregate_type,
  r.run_id                              AS aggregate_id,
  'ingestion.run.created'::text         AS event_type,
  jsonb_build_object(
    'run_id', r.run_id,
    'source_id', r.source_id
  )                                     AS payload,
  'system'::text                        AS actor_type,
  r.run_id                              AS actor_id,
  'ingestion'::text                     AS zone_context,
  r.run_id                              AS correlation_id,
  NULL::uuid                            AS causation_id,
  r.created_at                          AS event_timestamp,
  NULL::timestamptz                     AS valid_timestamp
FROM ingestion.run r;

COMMENT ON VIEW ingestion.ledger_contract_run_created IS
'Contract: proposed event_ledger row(s) for ingestion.run creation. Read-only.';

-- Contract View: run_state appended -> proposed event row
CREATE OR REPLACE VIEW ingestion.ledger_contract_run_state_appended AS
SELECT
  'ingestion.run'::text                   AS aggregate_type,
  rs.run_id                               AS aggregate_id,
  'ingestion.run_state.appended'::text    AS event_type,
  jsonb_build_object(
    'run_id', rs.run_id,
    'state', rs.state,
    'state_seq', rs.state_seq
  )                                       AS payload,
  'system'::text                          AS actor_type,
  rs.run_id                               AS actor_id,
  'ingestion'::text                       AS zone_context,
  rs.run_id                               AS correlation_id,
  NULL::uuid                              AS causation_id,
  rs.created_at                           AS event_timestamp,
  NULL::timestamptz                       AS valid_timestamp
FROM ingestion.run_state rs;

COMMENT ON VIEW ingestion.ledger_contract_run_state_appended IS
'Contract: proposed event_ledger row(s) for ingestion.run_state append. Read-only.';

-- Self-recording proof
INSERT INTO public.schema_migrations(version)
VALUES ('017_ingestion_write_contract.sql');

COMMIT;
