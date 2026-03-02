BEGIN;

-- Fail hard unless ingestion.source is empty.
-- Rationale: adding NOT NULL natural keys requires deterministic values.
DO $$
DECLARE
  n bigint;
BEGIN
  SELECT count(*) INTO n FROM ingestion.source;
  IF n <> 0 THEN
    RAISE EXCEPTION '009_add_source_natural_key_columns: ingestion.source is not empty (% rows). Refusing to add NOT NULL natural-key columns without deterministic backfill.', n;
  END IF;
END $$;

ALTER TABLE ingestion.source
  ADD COLUMN source_type text NOT NULL,
  ADD COLUMN source_key  text NOT NULL;

-- Optional performance index (UNIQUE will be added in the next migration).
CREATE INDEX ix_ingestion_source_source_type_source_key
  ON ingestion.source (source_type, source_key);

-- Append-only migration ledger
INSERT INTO public.schema_migrations(version)
VALUES ('009_add_source_natural_key_columns.sql');

COMMIT;
