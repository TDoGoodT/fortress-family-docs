#!/usr/bin/env bash
set -euo pipefail

echo "core.account handoff processor skeleton"
echo "Mode: evidence-first, non-operational"
echo "Input surface: core.ledger_contract_account_created"
echo "Canonical aggregate identity: ingestion.canonical_handoff_request.target_entity_id"
echo

docker compose exec -T postgres psql -X -U fortress -d fortress -v ON_ERROR_STOP=1 <<'SQL'
/*
  core.account MVP runtime skeleton
  ---------------------------------
  This script is intentionally NON-OPERATIONAL.
  It documents the approved deterministic processing shape after Master ruling.

  Master-approved canonical identity rule:
    - aggregate_id for core.account MUST resolve from
      ingestion.canonical_handoff_request.target_entity_id
    - normalized_record_id remains linkage/reference only
    - normalized_record_id is NOT the canonical aggregate identity

  Intended final flow:
    1. Read eligible handoff rows for target_entity_type = 'account'
    2. Join to contract surface for payload and validation fields
    3. Resolve canonical aggregate_id from handoff.target_entity_id
    4. Enforce idempotency via core.canonical_handoff_receipt
    5. Emit core.account.created into public.event_ledger using canonical aggregate_id
    6. Materialize core.account from core.ledger_projection_account_created
    7. Write receipt last

  Current deterministic state:
    - contract row exists
    - event row exists
    - receipt row exists
    - projection row missing
    - aggregate row missing

  Root cause already confirmed:
    - contract.aggregate_id currently reflects normalized_record_id
    - event.aggregate_id reflects target_entity_id
    - projection join therefore fails

  Required implementation alignment for future operational version:
    - either contract surface must expose canonical aggregate identity directly
    - or processor must source aggregate identity from handoff.target_entity_id
      and projection surface must align to that same canonical identity

  Governance:
    - no canonical writes
    - no event emission
    - no aggregate inserts
    - no receipt mutations
*/

SELECT 'contract_row_count' AS metric, COUNT(*)::text AS value
FROM core.ledger_contract_account_created
UNION ALL
SELECT 'handoff_row_count' AS metric, COUNT(*)::text AS value
FROM ingestion.canonical_handoff_request
WHERE target_entity_type = 'account'
UNION ALL
SELECT 'event_row_count' AS metric, COUNT(*)::text AS value
FROM public.event_ledger
WHERE aggregate_type = 'core.account'
  AND event_type = 'core.account.created'
UNION ALL
SELECT 'projection_row_count' AS metric, COUNT(*)::text AS value
FROM core.ledger_projection_account_created
UNION ALL
SELECT 'aggregate_row_count' AS metric, COUNT(*)::text AS value
FROM core.account
UNION ALL
SELECT 'receipt_row_count' AS metric, COUNT(*)::text AS value
FROM core.canonical_handoff_receipt
WHERE handoff_request_id IN (
    SELECT handoff_request_id
    FROM ingestion.canonical_handoff_request
    WHERE target_entity_type = 'account'
);

SELECT
    hr.handoff_request_id,
    hr.normalized_record_id,
    hr.target_entity_id AS canonical_account_id,
    lc.aggregate_id AS contract_aggregate_id,
    el.aggregate_id AS event_aggregate_id,
    el.event_id,
    r.handoff_receipt_id,
    CASE
        WHEN lc.aggregate_id = hr.target_entity_id THEN 'aligned'
        ELSE 'contract_mismatch'
    END AS contract_identity_status,
    CASE
        WHEN el.aggregate_id = hr.target_entity_id THEN 'aligned'
        ELSE 'event_mismatch'
    END AS event_identity_status
FROM ingestion.canonical_handoff_request hr
LEFT JOIN core.ledger_contract_account_created lc
    ON lc.normalized_record_id = hr.normalized_record_id
LEFT JOIN public.event_ledger el
    ON el.causation_id = hr.handoff_request_id
   AND el.aggregate_type = 'core.account'
   AND el.event_type = 'core.account.created'
LEFT JOIN core.canonical_handoff_receipt r
    ON r.handoff_request_id = hr.handoff_request_id
WHERE hr.target_entity_type = 'account'
ORDER BY hr.created_at, hr.handoff_request_id;

/*
  Placeholder for future operational implementation:

  DO $$
  DECLARE
      v_handoff_request_id uuid;
      v_target_entity_id uuid;
      v_contract RECORD;
      v_event_id uuid;
      v_receipt_exists boolean;
      v_event_exists boolean;
      v_account_exists boolean;
  BEGIN
      -- Load one eligible handoff_request_id deterministically
      -- Resolve v_target_entity_id from ingestion.canonical_handoff_request.target_entity_id
      -- Load matching contract row for payload validation
      -- Enforce idempotency using core.canonical_handoff_receipt
      -- Check partial-state inconsistencies
      -- INSERT INTO public.event_ledger using aggregate_id = v_target_entity_id
      -- RETURNING event_id INTO v_event_id
      -- INSERT INTO core.account from projection aligned to canonical account_id
      -- INSERT INTO core.canonical_handoff_receipt last
  END
  $$;
*/
SQL

echo
echo "No writes executed. Master-approved identity rule documented."
