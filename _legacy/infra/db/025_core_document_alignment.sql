-- 025_core_document_alignment.sql
--
-- Version Authority (explicit):
-- - fortress.core.document-domain.v1
-- - fortress.core.database-blueprint.v1
-- - fortress.project.version-governance.v1
-- - fortress.project.dependency-model.v2
--
-- Phase 4B1:
-- - Canonical Aggregate Schema Alignment
-- - Establish core.document as the first canonical aggregate write target
-- - No runtime logic
-- - No data copy
-- - No backfill
-- - No triggers
-- - No functions
--
-- Binding ruling:
-- - Create core.document only
-- - Mirror current minimal column shape of public.document
-- - No household FK yet
-- - No additional indexes beyond PK
-- - No uniqueness constraints

BEGIN;

CREATE TABLE IF NOT EXISTS core.document (
  document_id uuid NOT NULL DEFAULT uuid_v7(),
  household_id uuid NULL,
  document_type text NULL,
  title text NULL,
  source_uri text NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (document_id)
);

COMMENT ON TABLE core.document IS
'Authoritative canonical write target for future document mutation. Introduced by Phase 4B1 schema alignment.';

COMMENT ON COLUMN core.document.household_id IS
'Nullable UUID, intentionally unconstrained in Phase 4B1. No household FK yet by Master ruling.';

COMMENT ON TABLE public.document IS
'Legacy skeleton surface pending later governance resolution. Not the authoritative canonical write target.';

INSERT INTO public.schema_migrations(version)
VALUES ('025_core_document_alignment.sql');

COMMIT;
