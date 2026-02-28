-- 007_create_ingestion_tables.sql
-- Phase 2B: Deterministic Ingestion (tables skeleton only)
--
-- Constraints in this migration:
-- - PKs only
-- - FK-safe ordering
-- - Minimal FK indexes only
-- No unique constraints yet (idempotency in 009).
-- No hash columns yet (idempotency in 009).
-- No run_state sequencing trigger yet (010).
-- No polymorphic foreign keys: ingestion.error uses subject_type + subject_id (no FK constraints).

BEGIN;

-- 1) ingestion.source (Zone C)
CREATE TABLE IF NOT EXISTS ingestion.source (
  source_id uuid NOT NULL DEFAULT uuid_v7(),
  PRIMARY KEY (source_id),
  created_at timestamptz NOT NULL DEFAULT now()
);

-- 2) ingestion.run (Zone C)
CREATE TABLE IF NOT EXISTS ingestion.run (
  run_id uuid NOT NULL DEFAULT uuid_v7(),
  PRIMARY KEY (run_id),
  source_id uuid NOT NULL REFERENCES ingestion.source(source_id),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ingestion_run_source_id ON ingestion.run(source_id);

-- 3) ingestion.run_state (Zone C)  -- foundational for traceability
CREATE TABLE IF NOT EXISTS ingestion.run_state (
  run_state_id uuid NOT NULL DEFAULT uuid_v7(),
  PRIMARY KEY (run_state_id),
  run_id uuid NOT NULL REFERENCES ingestion.run(run_id),
  state_seq integer NOT NULL,
  state text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ingestion_run_state_run_id ON ingestion.run_state(run_id);
CREATE INDEX IF NOT EXISTS idx_ingestion_run_state_run_id_state_seq ON ingestion.run_state(run_id, state_seq);

-- 4) ingestion.raw_object (Zone C)
CREATE TABLE IF NOT EXISTS ingestion.raw_object (
  raw_object_id uuid NOT NULL DEFAULT uuid_v7(),
  PRIMARY KEY (raw_object_id),
  run_id uuid NOT NULL REFERENCES ingestion.run(run_id),
  source_id uuid NOT NULL REFERENCES ingestion.source(source_id),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ingestion_raw_object_run_id ON ingestion.raw_object(run_id);
CREATE INDEX IF NOT EXISTS idx_ingestion_raw_object_source_id ON ingestion.raw_object(source_id);

-- 5) ingestion.raw_record (Zone C)
CREATE TABLE IF NOT EXISTS ingestion.raw_record (
  raw_record_id uuid NOT NULL DEFAULT uuid_v7(),
  PRIMARY KEY (raw_record_id),
  run_id uuid NOT NULL REFERENCES ingestion.run(run_id),
  raw_object_id uuid NOT NULL REFERENCES ingestion.raw_object(raw_object_id),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ingestion_raw_record_run_id ON ingestion.raw_record(run_id);
CREATE INDEX IF NOT EXISTS idx_ingestion_raw_record_raw_object_id ON ingestion.raw_record(raw_object_id);

-- 6) ingestion.normalized_record (Zone C)
CREATE TABLE IF NOT EXISTS ingestion.normalized_record (
  normalized_record_id uuid NOT NULL DEFAULT uuid_v7(),
  PRIMARY KEY (normalized_record_id),
  run_id uuid NOT NULL REFERENCES ingestion.run(run_id),
  raw_record_id uuid NOT NULL REFERENCES ingestion.raw_record(raw_record_id),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ingestion_normalized_record_run_id ON ingestion.normalized_record(run_id);
CREATE INDEX IF NOT EXISTS idx_ingestion_normalized_record_raw_record_id ON ingestion.normalized_record(raw_record_id);

-- 7) ingestion.canonical_handoff_request (Zone C)
CREATE TABLE IF NOT EXISTS ingestion.canonical_handoff_request (
  handoff_request_id uuid NOT NULL DEFAULT uuid_v7(),
  PRIMARY KEY (handoff_request_id),
  run_id uuid NOT NULL REFERENCES ingestion.run(run_id),
  normalized_record_id uuid NOT NULL REFERENCES ingestion.normalized_record(normalized_record_id),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ingestion_handoff_request_run_id ON ingestion.canonical_handoff_request(run_id);
CREATE INDEX IF NOT EXISTS idx_ingestion_handoff_request_normalized_record_id ON ingestion.canonical_handoff_request(normalized_record_id);

-- 8) ingestion.error (Zone C) -- subject_type + subject_id only, no polymorphic FK constraints
CREATE TABLE IF NOT EXISTS ingestion.error (
  ingestion_error_id uuid NOT NULL DEFAULT uuid_v7(),
  PRIMARY KEY (ingestion_error_id),
  run_id uuid NOT NULL REFERENCES ingestion.run(run_id),
  stage text NOT NULL,
  error_class text NOT NULL,
  is_retryable boolean NOT NULL DEFAULT false,
  subject_type text,
  subject_id uuid,
  details jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ingestion_error_run_id ON ingestion.error(run_id);
CREATE INDEX IF NOT EXISTS idx_ingestion_error_subject ON ingestion.error(subject_type, subject_id);

COMMIT;
