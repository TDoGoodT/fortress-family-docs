-- 016_drop_duplicate_constraints_from_011.sql
--
-- Version Authority (explicit):
-- - fortress.project.version-governance.v1
-- - fortress.project.dependency-model.v2
--
-- Purpose:
-- - Remove duplicate UNIQUE constraints introduced by an out-of-band apply of
--   011_idempotency_constraints_and_indexes.sql.
-- - Safe to run whether duplicates exist or not (IF EXISTS).
--
-- Scope:
-- - Drops constraints only; no triggers, no functions, no materialized views.
-- - No data fixes; only schema hygiene for deterministic rebuilds.

BEGIN;

-- canonical_handoff_request duplicates
ALTER TABLE ingestion.canonical_handoff_request
  DROP CONSTRAINT IF EXISTS uq_ingestion_canonical_handoff_request_handoff_sha256;

ALTER TABLE ingestion.canonical_handoff_request
  DROP CONSTRAINT IF EXISTS uq_ingestion_canonical_handoff_request_normalized_record_id;

-- error duplicates
ALTER TABLE ingestion.error
  DROP CONSTRAINT IF EXISTS uq_ingestion_error_run_error_fingerprint_sha256_attempt;

ALTER TABLE ingestion.error
  DROP CONSTRAINT IF EXISTS uq_ingestion_error_run_stage_subject_attempt;

-- normalized_record duplicates
ALTER TABLE ingestion.normalized_record
  DROP CONSTRAINT IF EXISTS uq_ingestion_normalized_record_raw_record_id_schema_version;

ALTER TABLE ingestion.normalized_record
  DROP CONSTRAINT IF EXISTS uq_ingestion_normalized_record_source_id_normalized_sha256_sche;

-- raw_object duplicates
ALTER TABLE ingestion.raw_object
  DROP CONSTRAINT IF EXISTS uq_ingestion_raw_object_source_id_object_locator_content_sha256;

-- raw_record duplicates
ALTER TABLE ingestion.raw_record
  DROP CONSTRAINT IF EXISTS uq_ingestion_raw_record_raw_object_id_record_seq;

ALTER TABLE ingestion.raw_record
  DROP CONSTRAINT IF EXISTS uq_ingestion_raw_record_source_id_record_sha256;

-- source duplicates
ALTER TABLE ingestion.source
  DROP CONSTRAINT IF EXISTS uq_ingestion_source_source_type_source_key;

INSERT INTO public.schema_migrations(version)
VALUES ('016_drop_duplicate_constraints_from_011.sql');

COMMIT;
