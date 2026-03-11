#!/usr/bin/env bash
set -euo pipefail

echo "Phase 5: projection consistency diagnostics for core.person"

docker compose exec -T postgres psql -X -U fortress -d fortress -v ON_ERROR_STOP=1 <<'SQL'
/*
  Phase 5 diagnostics only:
  - read-only
  - compares projection surface to materialized aggregate
  - no writes, no updates, no deletes, no event emission

  Comparison scope:
  - core.ledger_projection_person_created
  - core.person

  Important:
  - core.person.created_at is aggregate-local materialization metadata
  - created_at is explicitly excluded from projection-consistency comparison
*/

WITH comparison AS (
    SELECT
        p.person_id AS projection_person_id,
        c.person_id AS aggregate_person_id,
        p.household_id AS projection_household_id,
        c.household_id AS aggregate_household_id,
        p.display_name AS projection_display_name,
        c.display_name AS aggregate_display_name,
        CASE
            WHEN p.person_id IS NOT NULL AND c.person_id IS NULL THEN 'missing_aggregate'
            WHEN p.person_id IS NULL AND c.person_id IS NOT NULL THEN 'orphan_aggregate'
            WHEN p.household_id IS DISTINCT FROM c.household_id
              OR p.display_name IS DISTINCT FROM c.display_name
            THEN 'field_divergence'
            ELSE 'consistent'
        END AS diagnostic_class
    FROM core.ledger_projection_person_created p
    FULL OUTER JOIN core.person c
      ON c.person_id = p.person_id
)
SELECT 'SUMMARY' AS section, metric, value
FROM (
    SELECT 'projection_row_count'::text AS metric, COUNT(*)::text AS value
    FROM core.ledger_projection_person_created
    UNION ALL
    SELECT 'aggregate_row_count'::text AS metric, COUNT(*)::text AS value
    FROM core.person
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
        p.person_id AS projection_person_id,
        c.person_id AS aggregate_person_id,
        p.household_id AS projection_household_id,
        c.household_id AS aggregate_household_id,
        p.display_name AS projection_display_name,
        c.display_name AS aggregate_display_name,
        CASE
            WHEN p.person_id IS NOT NULL AND c.person_id IS NULL THEN 'missing_aggregate'
            WHEN p.person_id IS NULL AND c.person_id IS NOT NULL THEN 'orphan_aggregate'
            WHEN p.household_id IS DISTINCT FROM c.household_id
              OR p.display_name IS DISTINCT FROM c.display_name
            THEN 'field_divergence'
            ELSE 'consistent'
        END AS diagnostic_class
    FROM core.ledger_projection_person_created p
    FULL OUTER JOIN core.person c
      ON c.person_id = p.person_id
)
SELECT
    diagnostic_class,
    COALESCE(projection_person_id, aggregate_person_id) AS person_id,
    projection_household_id,
    aggregate_household_id,
    projection_display_name,
    aggregate_display_name
FROM comparison
WHERE diagnostic_class <> 'consistent'
ORDER BY
    diagnostic_class,
    COALESCE(projection_person_id, aggregate_person_id);
SQL

echo "Projection consistency diagnostics completed."
