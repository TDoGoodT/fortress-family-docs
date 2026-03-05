-- 019_ingestion_contract_raw_record.sql
--
-- Adds contract view for raw_record ingestion events
-- Phase 3A – Deterministic ingestion event contracts
--
-- Authority:
-- fortress.ingestion.pipeline-architecture.v3
-- fortress.core.event-ledger.v1

BEGIN;

CREATE OR REPLACE VIEW ingestion.ledger_contract_raw_record_created AS
SELECT
  'ingestion.raw_record'::text          AS aggregate_type,
  rr.raw_record_id                      AS aggregate_id,
  'ingestion.raw_record.created'::text  AS event_type,
  jsonb_build_object(
    'raw_record_id', rr.raw_record_id,
    'raw_object_id', rr.raw_object_id,
    'run_id', rr.run_id,
    'source_id', rr.source_id,
    'record_seq', rr.record_seq,
    'record_sha256_hex', encode(rr.record_sha256, 'hex')
  )                                     AS payload,
  'system'::text                        AS actor_type,
  rr.run_id                             AS actor_id,
  'ingestion'::text                      zone_context,
  rr.run_id                             AS correlation_id,
  NULL::uuid                            AS causation_id,
  rr.created_at                         AS event_timestamp,
  NULL::timestamptz                     AS valid_timestamp
FROM ingestion.raw_record rr;

COMMENT ON VIEW ingestion.ledger_contract_raw_record_created IS
'Contract: proposed event_ledger row(s) for ingestion.raw_record creation.';

INSERT INTO public.schema_migrations(version)
VALUES ('019_ingestion_contract_raw_record.sql');

COMMIT;
