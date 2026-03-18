-- 020_ingestion_contract_normalized_record.sql
BEGIN;

CREATE OR REPLACE VIEW ingestion.ledger_contract_normalized_record_created AS
SELECT
  'ingestion.normalized_record'::text               AS aggregate_type,
  nr.normalized_record_id                           AS aggregate_id,
  'ingestion.normalized_record.created'::text       AS event_type,
  jsonb_build_object(
    'normalized_record_id', nr.normalized_record_id,
    'raw_record_id', nr.raw_record_id,
    'run_id', nr.run_id,
    'source_id', nr.source_id,
    'schema_version', nr.schema_version,
    'normalized_sha256_hex', encode(nr.normalized_sha256, 'hex')
  )                                                  AS payload,
  'system'::text                                     AS actor_type,
  nr.run_id                                          AS actor_id,
  'ingestion'::text                                  AS zone_context,
  nr.run_id                                          AS correlation_id,
  NULL::uuid                                         AS causation_id,
  nr.created_at                                      AS event_timestamp,
  NULL::timestamptz                                  AS valid_timestamp
FROM ingestion.normalized_record nr;

COMMENT ON VIEW ingestion.ledger_contract_normalized_record_created IS
'Contract: proposed event_ledger row(s) for ingestion.normalized_record creation.';

INSERT INTO public.schema_migrations(version)
VALUES ('020_ingestion_contract_normalized_record.sql');

COMMIT;
