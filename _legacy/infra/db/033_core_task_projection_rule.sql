-- 033_core_task_projection_rule.sql
--
-- Version Authority (explicit):
-- - fortress.core.task-domain.v1
-- - fortress.core.event-ledger.v1
-- - fortress.project.version-governance.v1
--
-- Phase 5B:
-- - core.task projection rule
-- - Event → canonical table materialization

BEGIN;

CREATE OR REPLACE VIEW core.ledger_projection_task_created AS
SELECT
    event_id,
    event_timestamp,

    aggregate_id AS task_id,

    CASE
        WHEN NULLIF(payload ->> 'household_id','') IS NULL
        THEN NULL::uuid
        ELSE (payload ->> 'household_id')::uuid
    END AS household_id,

    NULLIF(payload ->> 'title','') AS title,
    NULLIF(payload ->> 'status','') AS status,

    event_timestamp AS created_at

FROM public.event_ledger
WHERE
    aggregate_type = 'core.task'
    AND event_type = 'core.task.created';

COMMENT ON VIEW core.ledger_projection_task_created IS
'Projection: derive canonical core.task rows from core.task.created events.';

INSERT INTO public.schema_migrations(version)
VALUES ('033_core_task_projection_rule.sql');

COMMIT;
