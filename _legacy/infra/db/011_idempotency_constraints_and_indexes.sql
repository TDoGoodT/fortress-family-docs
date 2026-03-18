BEGIN;

-- ============================================================
-- 011_idempotency_constraints_and_indexes.sql
-- Scope: UNIQUE constraints + required indexes per pipeline-architecture.v3
-- No triggers, no functions, no extra columns.
-- ============================================================

-- -------------------------
-- 011B: Unique constraints
-- -------------------------

DO $$
BEGIN
  -- ingestion.source: UNIQUE (source_type, source_key)
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'uq_ingestion_source_source_type_source_key'
  ) THEN
    ALTER TABLE ingestion.source
      ADD CONSTRAINT uq_ingestion_source_source_type_source_key
      UNIQUE (source_type, source_key);
  END IF;

  -- ingestion.raw_object: UNIQUE (source_id, object_locator, content_sha256)
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'uq_ingestion_raw_object_source_id_object_locator_content_sha256'
  ) THEN
    ALTER TABLE ingestion.raw_object
      ADD CONSTRAINT uq_ingestion_raw_object_source_id_object_locator_content_sha256
      UNIQUE (source_id, object_locator, content_sha256);
  END IF;

  -- ingestion.raw_record: UNIQUE (raw_object_id, record_seq)
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'uq_ingestion_raw_record_raw_object_id_record_seq'
  ) THEN
    ALTER TABLE ingestion.raw_record
      ADD CONSTRAINT uq_ingestion_raw_record_raw_object_id_record_seq
      UNIQUE (raw_object_id, record_seq);
  END IF;

  -- ingestion.raw_record: UNIQUE (source_id, record_sha256)
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'uq_ingestion_raw_record_source_id_record_sha256'
  ) THEN
    ALTER TABLE ingestion.raw_record
      ADD CONSTRAINT uq_ingestion_raw_record_source_id_record_sha256
      UNIQUE (source_id, record_sha256);
  END IF;

  -- ingestion.normalized_record: UNIQUE (raw_record_id, schema_version)
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'uq_ingestion_normalized_record_raw_record_id_schema_version'
  ) THEN
    ALTER TABLE ingestion.normalized_record
      ADD CONSTRAINT uq_ingestion_normalized_record_raw_record_id_schema_version
      UNIQUE (raw_record_id, schema_version);
  END IF;

  -- ingestion.normalized_record: UNIQUE (source_id, normalized_sha256, schema_version)
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'uq_ingestion_normalized_record_source_id_normalized_sha256_schema_version'
  ) THEN
    ALTER TABLE ingestion.normalized_record
      ADD CONSTRAINT uq_ingestion_normalized_record_source_id_normalized_sha256_schema_version
      UNIQUE (source_id, normalized_sha256, schema_version);
  END IF;

  -- ingestion.canonical_handoff_request: UNIQUE (normalized_record_id)
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'uq_ingestion_canonical_handoff_request_normalized_record_id'
  ) THEN
    ALTER TABLE ingestion.canonical_handoff_request
      ADD CONSTRAINT uq_ingestion_canonical_handoff_request_normalized_record_id
      UNIQUE (normalized_record_id);
  END IF;

  -- ingestion.canonical_handoff_request: UNIQUE (handoff_sha256)
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'uq_ingestion_canonical_handoff_request_handoff_sha256'
  ) THEN
    ALTER TABLE ingestion.canonical_handoff_request
      ADD CONSTRAINT uq_ingestion_canonical_handoff_request_handoff_sha256
      UNIQUE (handoff_sha256);
  END IF;

  -- ingestion.error: UNIQUE (run_id, stage, subject_type, subject_id, attempt)
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'uq_ingestion_error_run_stage_subject_attempt'
  ) THEN
    ALTER TABLE ingestion.error
      ADD CONSTRAINT uq_ingestion_error_run_stage_subject_attempt
      UNIQUE (run_id, stage, subject_type, subject_id, attempt);
  END IF;

  -- ingestion.error: UNIQUE (run_id, error_fingerprint_sha256, attempt)
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'uq_ingestion_error_run_error_fingerprint_sha256_attempt'
  ) THEN
    ALTER TABLE ingestion.error
      ADD CONSTRAINT uq_ingestion_error_run_error_fingerprint_sha256_attempt
      UNIQUE (run_id, error_fingerprint_sha256, attempt);
  END IF;
END
$$;

-- -------------------------
-- 011C: Required indexes
-- -------------------------

-- Hash indexes (btree)
CREATE INDEX IF NOT EXISTS ix_ingestion_raw_object_content_sha256
  ON ingestion.raw_object (content_sha256);

CREATE INDEX IF NOT EXISTS ix_ingestion_raw_record_record_sha256
  ON ingestion.raw_record (record_sha256);

CREATE INDEX IF NOT EXISTS ix_ingestion_normalized_record_normalized_sha256
  ON ingestion.normalized_record (normalized_sha256);

CREATE INDEX IF NOT EXISTS ix_ingestion_canonical_handoff_request_handoff_sha256
  ON ingestion.canonical_handoff_request (handoff_sha256);

CREATE INDEX IF NOT EXISTS ix_ingestion_error_error_fingerprint_sha256
  ON ingestion.error (error_fingerprint_sha256);

-- Operational indexes
CREATE INDEX IF NOT EXISTS ix_ingestion_run_source_id_created_at_desc
  ON ingestion.run (source_id, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_ingestion_error_run_id_stage
  ON ingestion.error (run_id, stage);

-- Note:
-- run_state(run_id, state_seq) already exists: idx_ingestion_run_state_run_id_state_seq
-- canonical_handoff_request(run_id) already exists: idx_ingestion_handoff_request_run_id

-- -------------------------
-- Migration ledger append
-- -------------------------
INSERT INTO public.schema_migrations (version)
VALUES ('011_idempotency_constraints_and_indexes.sql');

COMMIT;
