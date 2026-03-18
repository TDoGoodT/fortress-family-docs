BEGIN;

-- 012_idempotency_constraints_and_indexes.sql
-- Scope: Idempotency UNIQUE constraints + required btree indexes per pipeline-architecture.v3
-- No triggers, no functions, no event emission logic.
-- Fail hard on duplicates: constraints will error if existing data violates uniqueness.

-- =========================================================
-- 012B – Unique Constraints (Idempotency Enforcement)
-- =========================================================

-- ingestion.source
ALTER TABLE ingestion.source
  ADD CONSTRAINT uq_ing_source_type_key
  UNIQUE (source_type, source_key);

-- ingestion.raw_object
ALTER TABLE ingestion.raw_object
  ADD CONSTRAINT uq_raw_object_src_loc_hash
  UNIQUE (source_id, object_locator, content_sha256);

-- ingestion.raw_record
ALTER TABLE ingestion.raw_record
  ADD CONSTRAINT uq_raw_record_obj_seq
  UNIQUE (raw_object_id, record_seq);

ALTER TABLE ingestion.raw_record
  ADD CONSTRAINT uq_raw_cord_src_hash
  UNIQUE (source_id, record_sha256);

-- ingestion.normalized_record
ALTER TABLE ingestion.normalized_record
  ADD CONSTRAINT uq_norm_record_raw_schema
  UNIQUE (raw_record_id, schema_version);

ALTER TABLE ingestion.normalized_record
  ADD CONSTRAINT uq_norm_record_src_hash_ver
  UNIQUE (source_id, normalized_sha256, schema_version);

-- ingestion.canonical_handoff_request
ALTER TABLE ingestion.canonical_handoff_request
  ADD CONSTRAINT uq_handoff_norm_record
  UNIQUE (normalized_record_id);

ALTER TABLE ingestion.canonical_handoff_request
  ADD CONSTRAINT uq_handoff_hash
  UNIQUE (handoff_sha256);

-- ingestion.error
ALTER TABLE ingestion.error
  ADD CONSTRAINT uq_error_run_stage_subject_attempt
  UNIQUE (run_id, stage, subject_type, subject_id, attempt);

ALTER TABLE ingestion.error
  ADD CONSTRAINT uq_error_run_fingerprint_attempt
  UNIQUE (run_id, error_fingerprint_sha256, attempt);

-- =========================================================
-- 012C – Required Indexes
-- =======================================================

-- Hash indexes (btree)
CREATE INDEX ix_raw_object_content_sha256
  ON ingestion.raw_object (content_sha256);

CREATE INDEX ix_raw_record_record_sha256
  ON ingestion.raw_record (record_sha256);

CREATE INDEX ix_norm_record_normalized_sha256
  ON ingestion.normalized_record (normalized_sha256);

CREATE INDEX ix_handoff_request_handoff_sha256
  ON ingestion.canonical_handoff_request (handoff_sha256);

CREATE INDEX ix_error_fingerprint_sha256
  ON ingestion.error (error_fingerprint_sha256);

-- Operational indexes
CREATE INDEX ix_run_source_created_at_desc
  ON ingestion.run (source_id, created_at DESC);

CREATE INDEX ix_error_run_stage
  ON ingestion.error (run_id, stage);

-- Append to migration ledger (append-only)
INSERT INTO public.schema_migrations(version)
VALUES ('012_idempotency_constraints_and_indexes.sql')
ON CONFLICT (version) DO NOTHING;

COMMIT;
