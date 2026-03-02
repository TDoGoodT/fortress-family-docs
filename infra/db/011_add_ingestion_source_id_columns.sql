BEGIN;

-- 011_add_ingestion_source_id_columns.sql
-- Purpose:
-- Bring ingestion.raw_record and ingestion.normalized_record up to canonical spec readiness
-- by adding source_id and backfilling deterministically via existing FK paths.
--
-- Determinism rules:
-- raw_record.source_id is derived from raw_object.source_id via raw_record.raw_object_id
-- normalized_record.source_id is derived from raw_record.source_id via normalized_record.raw_record_id
--
-- Fail hard:
-- If any row cannot be backfilled, SET NOT NULL will fail and the migration aborts.

-- 1) Add columns (nullable first)
ALTER TABLE ingestion.raw_record
  ADD COLUMN IF NOT EXISTS source_id uuid;

ALTER TABLE ingestion.normalized_record
  ADD COLUMN IF NOT EXISTS source_id uuid;

-- 2) Backfill deterministically

-- raw_record.source_id <- raw_object.source_id
UPDATE ingestion.raw_record rr
SET source_id = ro.source_id
FROM ingestion.raw_object ro
WHERE rr.source_id IS NULL
  AND rr.raw_object_id = ro.raw_object_id;

-- normalized_record.source_id <- raw_record.source_id
UPDATE ingestion.normalized_record nr
SET source_id = rr.source_id
FROM ingestion.raw_record rr
WHERE nr.source_id IS NULL
  AND nr.raw_record_id = rr.raw_record_id;

-- 3) Enforce NOT NULL (will fail hard if any NULL remains)
ALTER TABLE ingestion.raw_record
  ALTER COLUMN source_id SET NOT NULL;

ALTER TABLE ingestion.normalized_record
  ALTER COLUMN source_id SET NOT NULL;

-- 4) Append to migration ledger (append-only)
INSERT INTO public.schema_migrations(version)
VALUES ('011_add_ingestion_source_id_columns.sql')
ON CONFLICT (version) DO NOTHING;

COMMIT;
