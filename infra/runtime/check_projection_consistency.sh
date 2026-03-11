#!/usr/bin/env bash
set -euo pipefail

echo "Phase 4D: projection consistency diagnostics for core.document"

docker compose exec -T postgres psql -X -U fortress -d fortress -v ON_ERROR_STOP=1 <<'SQL'
/*
  Phase 4D diagnostics only:
  - read-only
  - compares projection surface to materialized aggregate
  - no writes, no updates, no deletes, no event emission

  Comparison scope:
  - core.ledger_projection_document_created
  - core.document

  Important:
  - core.document.created_at is aggregate-local materialization metadata
  - created_at is explicitly excluded from projection-consistency comparison
*/

WITH comparison AS (
    SELECT
        p.document_id AS projection_document_id,
        d.document_id AS aggregate_document_id,
        p.household_id AS projection_household_id,
        d.household_id AS aggregate_household_id,
        p.document_type AS projection_document_type,
        d.document_type AS aggregate_document_type,
        p.title AS projection_title,
        d.title AS aggregate_title,
        p.source_uri AS projection_source_uri,
        d.source_uri AS aggregate_source_uri,
        CASE
            WHEN p.document_id IS NOT NULL AND d.document_id IS NULL THEN 'missing_aggregate'
            WHEN p.document_id IS NULL AND d.document_id IS NOT NULL THEN 'orphan_aggregate'
            WHEN p.household_id IS DISTINCT FROM d.household_id
              OR p.document_type IS DISTINCT FROM d.document_type
              OR p.title IS DISTINCT FROM d.title
              OR p.source_uri IS DISTINCT FROM d.source_uri
            THEN 'field_divergence'
            ELSE 'consistent'
        END AS diagnostic_class
    FROM core.ledger_projection_document_created p
    FULL OUTER JOIN core.document d
      ON d.document_id = p.document_id
)
SELECT 'SUMMARY' AS section, metric, value
FROM (
    SELECT 'projection_row_count'::text AS metric, COUNT(*)::text AS value
    FROM core.ledger_projection_document_created
    UNION ALL
    SELECT 'aggregate_row_count'::text AS metric, COUNT(*)::text AS value
    FROM core.document
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
        p.document_id AS projection_document_id,
        d.document_id AS aggregate_document_id,
        p.household_id AS projection_household_id,
        d.household_id AS aggregate_household_id,
        p.document_type AS projection_document_type,
        d.document_type AS aggregate_document_type,
        p.title AS projection_title,
        d.title AS aggregate_title,
        p.source_uri AS projection_source_uri,
        d.source_uri AS aggregate_source_uri,
        CASE
            WHEN p.document_id IS NOT NULL AND d.document_id IS NULL THEN 'missing_aggregate'
            WHEN p.document_id IS NULL AND d.document_id IS NOT NULL THEN 'orphan_aggregate'
            WHEN p.household_id IS DISTINCT FROM d.household_id
              OR p.document_type IS DISTINCT FROM d.document_type
              OR p.title IS DISTINCT FROM d.title
              OR p.source_uri IS DISTINCT FROM d.source_uri
            THEN 'field_divergence'
            ELSE 'consistent'
        END AS diagnostic_class
    FROM core.ledger_projection_document_created p
    FULL OUTER JOIN core.document d
      ON d.document_id = p.document_id
)
SELECT
    diagnostic_class,
    COALESCE(projection_document_id, aggregate_document_id) AS document_id,
    projection_household_id,
    aggregate_household_id,
    projection_document_type,
    aggregate_document_type,
    projection_title,
    aggregate_title,
    projection_source_uri,
    aggregate_source_uri
FROM comparison
WHERE diagnostic_class <> 'consistent'
ORDER BY
    diagnostic_class,
    COALESCE(projection_document_id, aggregate_document_id);
SQL

echo "Projection consistency diagnostics completed."
