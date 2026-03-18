-- 022_ingestion_contract_error.sql
--
-- Adds contract view for ingestion.error events
-- Phase 3A – Deterministic ingestion event contracts

BEGIN;

CREATE OR REPLACE VIEW ingestion.ledger_contract_error_recorded AS
SELECT
  'ingestion.error'::text                    AS aggregate_type,
  e.ingestion_error_id                       AS aggregate_id,
  'ingestion.error.recorded'::text           AS event_type,

  jsonb_build_object(
    'ingestion_error_id', e.ingestion_error_id,
    'run_id', e.run_id,
    'stage', e.stage,
    'subject_type', e.subject_type,
    'subject_id', e.subject_id,
    'error_fingerprint_sha256_hex', encode(e.error_fingerprint_sha256,'hex'),
    'attempt', e.attempt
  )                                          AS payload,

  'system'::text                             AS actor_type,
  e.run_id                                   AS actor_id,
  'ingestion'::text                          AS zone_context,
  e.run_id                                 AS correlation_id,
  NULL::uuid                                 AS causation_id,
  e.created_at                               AS event_timestamp,
  NULL::timestamptz                          AS valid_timestamp

FROM ingestion.error e;

COMMENT ON VIEW ingestion.ledger_contract_error_recorded IS
'Contract: proposed event_ledger row(s) for ingestion.error events.';

INSERT INTO public.schema_migrations(version)
VALUES ('022_ingestion_contract_error.sql');

COMMIT;
