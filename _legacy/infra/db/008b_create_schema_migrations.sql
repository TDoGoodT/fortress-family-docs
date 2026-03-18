BEGIN;

-- 008b_create_schema_migrations.sql
-- Governance patch: canonical migration ledger (append-only)

CREATE TABLE public.schema_migrations (
  version    text PRIMARY KEY,
  applied_at timestamptz NOT NULL DEFAULT now()
);

-- Append-only discipline (reuse canonical prevention function from 001)
CREATE TRIGGER schema_migrations_no_update
BEFORE UPDATE ON public.schema_migrations
FOR EACH ROW
EXECUTE FUNCTION prevent_event_update_delete();

CREATE TRIGGER schema_migrations_no_delete
BEFORE DELETE ON public.schema_migrations
FOR EACH ROW
EXECUTE FUNCTION prevent_event_update_delete();

-- Backfill: explicit filenames of migrations already applied
INSERT INTO public.schema_migrations (version) VALUES
  ('001_event_ledger.sql'),
  ('002_core_aggregates_skeleton.sql'),
  ('003_uuidv7_enforcement.sql'),
  ('004_event_ledger_envelope.sql'),
  ('005_event_ledger_hash_chaining.sql'),
  ('006_create_ingestion_schema.sql'),
  ('007_create_ingestion_tables.sql'),
  ('008_create_core_handoff_receipt.sql'),
  ('008a_fix_handoff_receipt_event_ledger_fk.sql'),
  ('008b_create_schema_migrations.sql');

COMMIT;