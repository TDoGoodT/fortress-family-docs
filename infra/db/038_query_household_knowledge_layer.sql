-- 038_query_household_knowledge_layer.sql
--
-- Version Authority (explicit):
-- - fortress.project.version-governance.v1
-- - fortress.project.dependency-model.v2
--
-- Household Knowledge Query Layer:
-- - additive query schema only
-- - read-only views only
-- - canonical aggregates as serving sources
-- - no projection serving dependency
-- - no runtime logic
-- - no tables
-- - no triggers
-- - no functions
-- - no procedures
-- - no materialized views

BEGIN;

CREATE SCHEMA IF NOT EXISTS query;

CREATE OR REPLACE VIEW query.household_accounts AS
SELECT
    household_id,
    account_id,
    account_label,
    account_kind,
    created_at
FROM core.account
WHERE household_id IS NOT NULL;

COMMENT ON VIEW query.household_accounts IS
'Household knowledge surface for canonical accounts. Read-only. Served from core.account only.';

CREATE OR REPLACE VIEW query.household_tasks AS
SELECT
    household_id,
    task_id,
    title,
    status,
    created_at
FROM core.task
WHERE household_id IS NOT NULL;

COMMENT ON VIEW query.household_tasks IS
'Household knowledge surface for canonical tasks. Read-only. Served from core.task only.';

CREATE OR REPLACE VIEW query.household_documents AS
SELECT
    household_id,
    document_id,
    document_type,
    title,
    source_uri
FROM core.document
WHERE household_id IS NOT NULL;

COMMENT ON VIEW query.household_documents IS
'Household knowledge surface for canonical documents. Read-only. Served from core.document only.';

CREATE OR REPLACE VIEW query.household_state AS
WITH household_keys AS (
    SELECT household_id
    FROM core.account
    WHERE household_id IS NOT NULL
    UNION
    SELECT household_id
    FROM core.task
    WHERE household_id IS NOT NULL
    UNION
    SELECT household_id
    FROM core.document
    WHERE household_id IS NOT NULL
),
account_summary AS (
    SELECT
        household_id,
        COUNT(*)::bigint AS account_count,
        MAX(created_at) AS latest_account_created_at
    FROM core.account
    WHERE household_id IS NOT NULL
    GROUP BY household_id
),
task_summary AS (
    SELECT
        household_id,
        COUNT(*)::bigint AS task_count,
        MAX(created_at) AS latest_task_created_at
    FROM core.task
    WHERE household_id IS NOT NULL
    GROUP BY household_id
),
document_summary AS (
    SELECT
        household_id,
        COUNT(*)::bigint AS document_count
    FROM core.document
    WHERE household_id IS NOT NULL
    GROUP BY household_id
)
SELECT
    hk.household_id,
    COALESCE(a.account_count, 0::bigint) AS account_count,
    COALESCE(t.task_count, 0::bigint) AS task_count,
    COALESCE(d.document_count, 0::bigint) AS document_count,
    a.latest_account_created_at,
    t.latest_task_created_at
FROM household_keys hk
LEFT JOIN account_summary a
    ON a.household_id = hk.household_id
LEFT JOIN task_summary t
    ON t.household_id = hk.household_id
LEFT JOIN document_summary d
    ON d.household_id = hk.household_id;

COMMENT ON VIEW query.household_state IS
'Household knowledge summary surface. One row per non-null household_id. Read-only. Served from grouped summaries over core.account, core.task, and core.document only.';

INSERT INTO public.schema_migrations(version)
VALUES ('038_query_household_knowledge_layer.sql');

COMMIT;
