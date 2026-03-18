-- 031_core_task_alignment.sql
--
-- Version Authority (explicit):
-- - fortress.core.task-domain.v1
-- - fortress.core.database-blueprint.v1
-- - fortress.project.version-governance.v1
-- - fortress.project.dependency-model.v2
--
-- Phase 5B:
-- - Canonical Aggregate Schema Alignment
-- - Introduce core.task canonical write surface
-- - Minimal MVP aggregate
--
-- Scope:
-- - Create core.task only
-- - No triggers
-- - No functions
-- - No backfill
-- - No lifecycle logic

BEGIN;

CREATE TABLE IF NOT EXISTS core.task (
    task_id      uuid PRIMARY KEY,
    household_id uuid NOT NULL,
    title        text NOT NULL,
    status       text NOT NULL,
    created_at   timestamptz NOT NULL
);

COMMENT ON TABLE core.task IS
'Canonical aggregate table for core.task MVP. Created by Phase 5B task aggregate introduction.';

INSERT INTO public.schema_migrations(version)
VALUES ('031_core_task_alignment.sql');

COMMIT;
