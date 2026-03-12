#!/usr/bin/env bash
set -euo pipefail

echo "Phase 5B: projection consistency diagnostics for core.task"

docker compose exec -T postgres psql -X -U fortress -d fortress -v ON_ERROR_STOP=1 <<'SQL'
/*
  Phase 5B diagnostics only:
  - read-only
  - compares projection surface to materialized aggregate
  - no writes, no updates, no deletes, no event emission

  Comparison scope:
  - core.ledger_projection_task_created
  - core.task

  Important:
  - core.task.created_at is aggregate-local materialization metadata
  - created_at is explicitly excluded from projection-consistency comparison
*/

WITH comparison AS (
    SELECT
        p.task_id AS projection_task_id,
        c.task_id AS aggregate_task_id,
        p.household_id AS projection_household_id,
        c.household_id AS aggregate_household_id,
        p.title AS projection_title,
        c.title AS aggregate_title,
        p.status AS projection_status,
        c.status AS aggregate_status,
        CASE
            WHEN p.task_id IS NOT NULL AND c.task_id IS NULL THEN 'missing_aggregate'
            WHEN p.task_id IS NULL AND c.task_id IS NOT NULL THEN 'orphan_aggregate'
            WHEN p.household_id IS DISTINCT FROM c.household_id
              OR p.title IS DISTINCT FROM c.title
              OR p.status IS DISTINCT FROM c.status
            THEN 'field_divergence'
            ELSE 'consistent'
        END AS diagnostic_class
    FROM core.ledger_projection_task_created p
    FULL OUTER JOIN core.task c
      ON c.task_id = p.task_id
)
SELECT 'SUMMARY' AS section, metric, value
FROM (
    SELECT 'projection_row_count'::text AS metric, COUNT(*)::text AS value
    FROM core.ledger_projection_task_created
    UNION ALL
    SELECT 'aggregate_row_count'::text AS metric, COUNT(*)::text AS value
    FROM core.task
    UNION ALL
    SELECT 'missing_aggregate_count'::text AS metric, COUNT(*)::text AS value
    FROM comparison
    WHERE diagnostic_class = 'missing_aggregate'
    UNION ALL
    SELECT 'orphan_aggregate_count'::text AS metric, COUNT(*)::text AS value
    FROM comparison
    WHERE diagnostic_class = 'orphan_aggregate'
    UNION ALL
    SELECT 'field_divergence_count'::text AS metric, COUNT(*)::text AS value
    FROM comparison
    WHERE diagnostic_class = 'field_divergence'
) summary
ORDER BY metric;

WITH comparison AS (
    SELECT
        p.task_id AS projection_task_id,
        c.task_id AS aggregate_task_id,
        p.household_id AS projection_household_id,
        c.household_id AS aggregate_household_id,
        p.title AS projection_title,
        c.title AS aggregate_title,
        p.status AS projection_status,
        c.status AS aggregate_status,
        CASE
            WHEN p.task_id IS NOT NULL AND c.task_id IS NULL THEN 'missing_aggregate'
            WHEN p.task_id IS NULL AND c.task_id IS NOT NULL THEN 'orphan_aggregate'
            WHEN p.household_id IS DISTINCT FROM c.household_id
              OR p.title IS DISTINCT FROM c.title
              OR p.status IS DISTINCT FROM c.status
            THEN 'field_divergence'
            ELSE 'consistent'
        END AS diagnostic_class
    FROM core.ledger_projection_task_created p
    FULL OUTER JOIN core.task c
      ON c.task_id = p.task_id
)
SELECT
    diagnostic_class,
    COALESCE(projection_task_id, aggregate_task_id) AS task_id,
    projection_household_id,
    aggregate_household_id,
    projection_title,
    aggregate_title,
    projection_status,
    aggregate_status
FROM comparison
WHERE diagnostic_class <> 'consistent'
ORDER BY
    diagnostic_class,
    COALESCE(projection_task_id, aggregate_task_id);
SQL

echo "Projection consistency diagnostics completed."
