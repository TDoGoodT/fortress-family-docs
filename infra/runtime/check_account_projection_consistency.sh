#!/usr/bin/env bash
set -euo pipefail

echo "core.account projection consistency diagnostics"
echo "Mode: read-only"
echo

docker compose exec -T postgres psql -X -U fortress -d fortress -v ON_ERROR_STOP=1 <<'SQL'
/*
  core.account projection consistency diagnostics
  -----------------------------------------------
  Read-only diagnostics only.

  Comparison scope:
    - core.ledger_projection_account_created
    - core.account

  Important:
    - created_at is excluded from divergence comparison
    - current known upstream blocker:
      projection depends on contract.aggregate_id = event.aggregate_id,
      but observed event was emitted under a different aggregate_id
*/

WITH comparison AS (
    SELECT
        p.account_id AS projection_account_id,
        a.account_id AS aggregate_account_id,
        p.household_id AS projection_household_id,
        a.household_id AS aggregate_household_id,
        p.account_label AS projection_account_label,
        a.account_label AS aggregate_account_label,
        p.account_kind AS projection_account_kind,
        a.account_kind AS aggregate_account_kind,
        CASE
            WHEN p.account_id IS NOT NULL AND a.account_id IS NULL THEN 'missing_aggregate'
            WHEN p.account_id IS NULL AND a.account_id IS NOT NULL THEN 'orphan_aggregate'
            WHEN p.household_id IS DISTINCT FROM a.household_id
              OR p.account_label IS DISTINCT FROM a.account_label
              OR p.account_kind IS DISTINCT FROM a.account_kind
            THEN 'field_divergence'
            ELSE 'consistent'
        END AS diagnostic_class
    FROM core.ledger_projection_account_created p
    FULL OUTER JOIN core.account a
      ON a.account_id = p.account_id
)
SELECT 'SUMMARY' AS section, metric, value
FROM (
    SELECT 'projection_row_count'::text AS metric, COUNT(*)::text AS value
    FROM core.ledger_projection_account_created
    UNION ALL
    SELECT 'aggregate_row_count'::text AS metric, COUNT(*)::text AS value
    FROM core.account
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
        p.account_id AS projection_account_id,
        a.account_id AS aggregate_account_id,
        p.household_id AS projection_household_id,
        a.household_id AS aggregate_household_id,
        p.account_label AS projection_account_label,
        a.account_label AS aggregate_account_label,
        p.account_kind AS projection_account_kind,
        a.account_kind AS aggregate_account_kind,
        CASE
            WHEN p.account_id IS NOT NULL AND a.account_id IS NULL THEN 'missing_aggregate'
            WHEN p.account_id IS NULL AND a.account_id IS NOT NULL THEN 'orphan_aggregate'
            WHEN p.household_id IS DISTINCT FROM a.household_id
              OR p.account_label IS DISTINCT FROM a.account_label
              OR p.account_kind IS DISTINCT FROM a.account_kind
            THEN 'field_divergence'
            ELSE 'consistent'
        END AS diagnostic_class
    FROM core.ledger_projection_account_created p
    FULL OUTER JOIN core.account a
      ON a.account_id = p.account_id
)
SELECT
    diagnostic_class,
    COALESCE(projection_account_id, aggregate_account_id) AS account_id,
    projection_household_id,
    aggregate_household_id,
    projection_account_label,
    aggregate_account_label,
    projection_account_kind,
    aggregate_account_kind
FROM comparison
WHERE diagnostic_class <> 'consistent'
ORDER BY
    diagnostic_class,
    COALESCE(projection_account_id, aggregate_account_id);
SQL

echo
echo "Read-only diagnostics completed."
