-- 018_ingestion_contract_raw_object.sql
--
-- Adds contract view for raw_object ingestion events
-- Phase 3A – Deterministic ingestion event contracts
--
-- Authority:
-- fortress.ingestion.pipeline-architecture.v3
-- fortress.core.event-ledger.v1

BEGIN;

CREATE OR REPLACE VIEW ingestion.ledger_contract_raw_object_ingested AS
SELECT
  'ingestion.raw_object'::text          AS aggregate_type,
  ro.raw_object_id                      AS aggregate_id,
  'ingestion.raw_object.ingested'::text AS event_type,
  jsonb_build_object(
    'raw_object_id', ro.raw_object_id,
    'run_id', ro.run_id,
    'source_id', ro.source_id,
    'object_locator', ro.object_locator,
    'content_sha256_hex', encode(ro.content_sha256, 'hex')
  )                                     AS payload,
  'system'::text                        AS actor_type,
  ro.run_id                             AS actor_id,
  'ingestion'::text                     AS zone_context,
  ro.run_id                           AS correlation_id,
  NULL::uuid                            AS causation_id,
  ro.created_at                         AS event_timestamp,
  NULL::timestamptz                     AS valid_timestamp
FROM ingestion.raw_object ro;

COMMENT ON VIEW ingestion.ledger_contract_raw_object_ingested IS
'Contract: proposed event_ledger row(s) for ingestion.raw_object ingestion.';

INSERT INTO public.schema_migrations(version)
VALUES ('018_ingestion_contract_raw_object.sql');

COMMIT;
