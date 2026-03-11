#!/usr/bin/env bash
set -euo pipefail

echo "Phase 4E: ledger integrity diagnostics"

docker compose exec -T postgres psql -X -U fortress -d fortress -v ON_ERROR_STOP=1 <<'SQL'
/*
  Phase 4E diagnostics only:
  - read-only
  - operates on ledger diagnostic views only
  - no writes, no updates, no deletes, no rebuilds

  Required summary surface:
  - ledger_row_count
  - hash_chain_mismatch_count
  - hash_chain_head_count
  - envelope_violation_count
  - ingestion_zone_violation_count
*/

WITH summary AS (
    SELECT 'ledger_row_count'::text AS metric, COUNT(*)::text AS value
    FROM public.event_ledger

    UNION ALL

    SELECT 'hash_chain_mismatch_count'::text AS metric, COUNT(*)::text AS value
    FROM public.diag_ledger_hash_chain_mismatch

    UNION ALL

    SELECT 'hash_chain_head_count'::text AS metric, COUNT(*)::text AS value
    FROM public.diag_ledger_hash_chain_head_count

    UNION ALL

    SELECT 'envelope_violation_count'::text AS metric, COUNT(*)::text AS value
    FROM public.diag_ledger_envelope_violations

    UNION ALL

    SELECT 'ingestion_zone_violation_count'::text AS metric, COUNT(*)::text AS value
    FROM public.diag_ledger_ingestion_zone_envelope_violations
)
SELECT
    'SUMMARY' AS section,
    metric,
    value
FROM summary
ORDER BY metric;

SELECT
    diagnostic_class,
    event_id,
    aggregate_type,
    aggregate_id,
    event_type
FROM (
    SELECT
        'hash_chain_mismatch'::text AS diagnostic_class,
        e.event_id,
        e.aggregate_type,
        e.aggregate_id,
        e.event_type
    FROM public.diag_ledger_hash_chain_mismatch m
    JOIN public.event_ledger e
      ON e.event_id = m.event_id

    UNION ALL

    SELECT
        'envelope_violation'::text AS diagnostic_class,
        v.event_id,
        v.aggregate_type,
        v.aggregate_id,
        v.event_type
    FROM public.diag_ledger_envelope_violations v

    UNION ALL

    SELECT
        'ingestion_zone_violation'::text AS diagnostic_class,
        z.event_id,
        z.aggregate_type,
        z.aggregate_id,
        z.event_type
    FROM public.diag_ledger_ingestion_zone_envelope_violations z
) d
ORDER BY
    diagnostic_class,
    event_id;
SQL

echo "Ledger integrity diagnostics completed."
