BEGIN;

-- Rename truncated/typo constraint names to canonical, stable identifiers.

DO $$
BEGIN
  -- raw_record: fix typo/truncation if exists
  IF EXISTS (
    SELECT 1
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'ingestion'
      AND t.relname = 'raw_record'
      AND c.conname = 'uq_raw_cord_src_hash'
  ) THEN
    ALTER TABLE ingestion.raw_record
      RENAME CONSTRAINT uq_raw_cord_src_hash TO uq_raw_record_src_hash;
  END IF;
END
$$;

INSERT INTO public.schema_migrations(version)
VALUES ('013_rename_truncated_constraints.sql')
ON CONFLICT (version) DO NOTHING;

COMMIT;
