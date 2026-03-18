-- 027_core_document_projection_rule.sql
--
-- Version Authority (explicit):
-- - fortress.core.document-domain.v1
-- - fortress.core.database-blueprint.v1
-- - fortress.core.event-ledger.v1
-- - fortress.project.version-governance.v1
-- - fortress.project.dependency-model.v2
--
-- Phase 4B:
-- - Deterministic event projection rule
-- - Read-only projection surface
-- - No triggers
-- - No functions
-- - No direct data repair in this migration
--
-- Projection rule:
-- - Source of truth is public.event_ledger only
-- - Project only core.document.created
-- - Materialized row shape must derive strictly from event payload
-- - No additional derived fields
--
-- Naming:
-- - ledger_projection_* prefix reserved for deterministic projection views

BEGIN;

CREATE OR REPLACE VIEW core.ledger_projection_document_created AS
SELECT
    el.event_id,
    el.event_timestamp,
    el.aggregate_id AS document_id,
    CASE
        WHEN NULLIF(el.payload ->> 'household_id', '') IS NULL THEN NULL
        ELSE (el.payload ->> 'household_id')::uuid
    END AS household_id,
    NULLIF(el.payload ->> 'document_type', '') AS document_type,
    NULLIF(el.payload ->> 'title', '') AS title,
    NULLIF(el.payload ->> 'source_uri', '') AS source_uri
FROM public.event_ledger el
WHERE el.aggregate_type = 'core.document'
  AND el.event_type = 'core.document.created';

COMMENT ON VIEW core.ledger_projection_document_created IS
'Projection rule: deterministic read-only mapping from public.event_ledger core.document.created events to core.document row shape. Source of truth is the ledger only.';

INSERT INTO public.schema_migrations(version)
VALUES ('027_core_document_projection_rule.sql');

COMMIT;
