/*
fortress 2.0 — Phase 2C
Migration: 014_event_emission_contract.sql

Version authority (MUST):
- fortress.ingestion.pipeline-architecture.v3
- fortress.core.event-ledger.v1
- fortress.project.dependency-model.v2
- fortress.project.version-governance.v1

Scope guard (OUT OF SCOPE):
- No triggers, no functions
- No materialized views
- No new sequences/columns/tables/constraints
- No writes, no data fixes, detect/report only
- No changes to public.event_ledger triggers/functions

Ordering / time semantics:
- Do NOT treat created_at as semantic ordering.
- For diagnostics that require a stable order, we use (created_at, event_id) ONLY as a deterministic tie-breaker for reporting, not as business semantics.
- event_timestamp is the semantic time field.
*/

BEGIN;

-- =====================================================================
-- diag_ing_* : ingestion diagnostics (read-only)
-- ===================================================================

/*
Detect run_state sequencing violations per run_id:
- state_seq should start at 1
- no duplicates
- no gaps (i.e., expected next = prior + 1)
*/
CREATE OR REPLACE VIEW ingestion.diag_ing_run_state_seq_violations AS
WITH base AS (
  SELECT
    rs.run_id,
    rs.state_seq
  FROM ingestion.run_state rs
),
distinct_seq AS (
  SELECT DISTINCT run_id, state_seq
  FROM base
),
ordered AS (
  SELECT
    run_id,
    state_seq,
    LAG(state_seq) OVER (PARTITION BY run_id ORDER BY state_seq) AS prev_seq
  FROM distinct_seq
),
gaps AS (
  SELECT
    run_id,
    'GAP'::text AS violation_type,
    (prev_seq + 1) AS expected_seq,
    state_seq AS observed_seq,
    (state_seq - (prev_seq + 1)) AS gap_size
  FROM ordered
  WHERE prev_seq IS NOT NULL
    AND state_seq <> prev_seq + 1
),
dupes AS (
  SELECT
    run_id,
    'DUPLICATE'::text AS violation_type,
    state_seq AS expected_seq,
    state_seq AS observed_seq,
    (COUNT(*) - 1) AS gap_size
  FROM base
  GROUP BY run_id, state_seq
  HAVING COUNT(*) > 1
),
starts AS (
  SELECT
    run_id,
    'START_NOT_ONE'::text AS violation_type,
    1 AS expected_seq,
    MIN(state_seq) AS observed_seq,
    0 AS gap_size
  FROM base
  GROUP BY run_id
  HAVING MIN(state_seq) <> 1
)
SELECT * FROM gaps
UNION ALL
SELECT * FROM dupes
UNION ALL
SELECT * FROM starts;

COMMENT ON VIEW ingestion.diag_ing_run_state_seq_violations IS
'Diagnostics: detects ingestion.run_state sequencing violations per run_id (gaps, duplicates, non-1 start). Read-only.';


/*
Detect idempotency invariant violations by checking for duplicates on keys that are expected to be unique.
Note: under normal operation, UNIQUE constraints prevent duplicates. This view is for detection/reporting only
(e.g., manual data corruption, disabled constraints in dev, import anomalies).
*/
CREATE OR REPLACE VIEW ingestion.diag_ing_idempotency_duplicates AS
SELECT
  'ingestion.raw_object (source_id, object_locator, content_sha256)'::text AS invariant,
  jsonb_build_object(
    'source_id', source_id,
    'object_locator', object_locator,
    'content_sha256_hex', encode(content_sha256, 'hex')
  ) AS key,
  COUNT(*)::bigint AS row_count
FROM ingestion.raw_object
GROUP BY source_id, object_locator, content_sha256
HAVING COUNT(*) > 1

UNION ALL
SELECT
  'ingestion.raw_record (raw_object_id, record_seq)'::text AS invariant,
  jsonb_build_object(
    'raw_object_id', raw_object_id,
    'record_seq', record_seq
  ) AS key,
  COUNT(*)::bigint AS row_count
FROM ingestion.raw_record
GROUP BY raw_object_id, record_seq
HAVING COUNT(*) > 1

UNION ALL
SELECT
  'ingestion.raw_record (source_id, record_sha256)'::text AS invariant,
  jsonb_build_object(
    'source_id', source_id,
    'record_sha256_hex', encode(record_sha256, 'hex')
  ) AS key,
  COUNT(*)::bigint AS row_count
FROM ingestion.raw_record
GROUP BY source_id, record_sha256
HAVING COUNT(*) > 1

UNION ALL
SELECT
  'ingestion.normalized_record (raw_record_id, schema_version)'::text AS invariant,
  jsonb_build_object(
    'raw_record_id', raw_record_id,
    'schema_version', schema_version
  ) AS key,
  COUNT(*)::bigint AS row_count
FROM ingestion.normalized_record
GROUP BY raw_record_id, schema_version
HAVING COUNT(*) > 1

UNION ALL
SELECT
  'ingestion.normalized_record (source_id, normalized_sha256, schema_version)'::text AS invariant,
  jsonb_build_object(
    'source_id', source_id,
    'normalized_sha256_hex', encode(normalized_sha256, 'hex'),
    'schema_version', schema_version
  ) AS key,
  COUNT(*)::bigint AS row_count
FROM ingestion.normalized_record
GROUP BY source_id, normalized_sha256, schema_version
HAVING COUNT(*) > 1

UNION ALL
SELECT
  'ingestion.canonical_handoff_request (handoff_sha256)'::text AS invariant,
  jsonb_build_object(
    'handoff_sha256_hex', encode(handoff_sha256, 'hex')
  ) AS key,
  COUNT(*)::bigint AS row_count
FROM ingestion.canonical_handoff_request
GROUP BY handoff_sha256
HAVING COUNT(*) > 1

UNION ALL
SELECT
  'ingestion.canonical_handoff_request (normalized_record_id)'::text AS invariant,
  jsonb_build_object(
    'normalized_record_id', normalized_record_id
  ) AS key,
  COUNT(*)::bigint AS row_count
FROM ingestion.canonical_handoff_request
GROUP BY normalized_record_id
HAVING COUNT(*) > 1;

COMMENT ON VIEW ingestion.diag_ing_idempotency_duplicates IS
'Diagnostics: detects duplicates on idempotency-unique key surfaces across ingestion tables. Read-only.';


/*
Optional read-only signal for idempotency-related failures recorded in ingestion.error.
We do NOT assume specific error_code taxonomy; we expose rows where details might indicate uniqueness/idempotency.
This is conservative and deterministic, and intended for operator inspection.
*/
CREATE OR REPLACE VIEW ingestion.diag_ing_error_potential_idempotency AS
SELECT
  e.ingestion_error_id,
  e.run_id,
  e.stage,
  e.error_class,
  e.error_code,
  e.attempt,
  e.subject_type,
  e.subject_id,
  e.created_at,
  e.details,
  encode(e.error_fingerprint_sha256, 'hex') AS error_fingerprint_sha256_hex
FROM ingestion.error e
WHERE
  -- Conservative heuristic for diagnostics only:
  -- look for common substrings in error_class or error_code; if not present, view will be empty.
  (lower(e.error_class) LIKE '%unique%' OR lower(e.error_class) LIKE '%idempot%' OR lower(e.error_class) LIKE '%duplicate%')
  OR
  (lower(e.error_code) LIKE '%unique%' OR lower(e.error_code) LIKE '%idempot%' OR lower(e.error_code) LIKE '%duplicate%');

COMMENT ON VIEW ingestion.diag_ing_error_potential_idempotency IS
'Diagnostics: surfaces ingestion.error rows that may relate to idempotency/uniqueness by conservative text matching. Read-only.';


-- =====================================================================
-- diag_ledger_* : event_ledger envelope + chain diagnostics (read-only)
-- =====================================================================

/*
Envelope validation on public.event_ledger.
This view is global (all events). A zone-filtered view is also provided below.
*/
CREATE OR REPLACE VIEW public.diag_ledger_envelope_violations AS
SELECT
  e.event_id,
  e.aggregate_type,
  e.aggregate_id,
  e.event_type,
  e.created_at,
  e.event_timestamp,
  e.actor_type,
  e.actor_id,
  e.zone_context,
  e.correlation_id,
  e.causation_id,
  -- list violations deterministically
  ARRAY_REMOVE(ARRAY[
    CASE WHEN e.actor_type IS NULL OR e.actor_type = '' THEN 'actor_type_missing' END,
    CASE WHEN e.actor_type = 'unknown' THEN 'actor_type_unknown_default' END,
    CASE WHEN e.zone_context IS NULL OR e.zone_context = '' THEN 'zone_context_missing' END,
    CASE WHEN e.correlation_id IS NULL THEN 'correlation_id_missing' END,
    CASE WHEN e.event_timestamp IS NULL THEN 'event_timestamp_missing' END,
    CASE WHEN e.aggregate_type IS NULL OR e.aggregate_type = '' THEN 'aggregate_type_missing' END,
    CASE WHEN e.aggregate_id IS NULL THEN 'aggregate_id_missing' END,
    CASE WHEN e.event_type IS NULL OR e.event_type = '' THEN 'event_type_missing' END,
    CASE WHEN e.payload IS NULL THEN 'payload_missing' END,
    CASE WHEN e.current_event_hash IS NULL THEN 'current_event_hash_missing' END
  ], NULL) AS violations
FROM public.event_ledger e
WHERE
  cardinality(ARRAY_REMOVE(ARRAY[
    CASE WHEN e.actor_type IS NULL OR e.actor_type = '' THEN 'actor_type_missing' END,
    CASE WHEN e.actor_type = 'unknown' THEN 'actor_type_unknown_default' END,
    CASE WHEN e.zone_context IS NULL OR e.zone_context = '' THEN 'zone_context_missing' END,
    CASE WHEN e.correlation_id IS NULL THEN 'correlation_id_missing' END,
    CASE WHEN e.event_timestamp IS NULL THEN 'event_timestamp_missing' END,
    CASE WHEN e.aggregate_type IS NULL OR e.aggregate_type = '' THEN 'aggregate_type_missing' END,
    CASE WHEN e.aggregate_id IS NULL THEN 'aggregate_id_missing' END,
    CASE WHEN e.event_type IS NULL OR e.event_type = '' THEN 'event_type_missing' END,
    CASE WHEN e.payload IS NULL THEN 'payload_missing' END,
    CASE WHEN e.current_event_hash IS NULL THEN 'current_event_hash_missing' END
  ], NULL)) > 0;

COMMENT ON VIEW public.diag_ledger_envelope_violations IS
'Diagnostics: envelope validation for public.event_ledger (global). Read-only.';


/*
Zone-filtered envelope validation for ingestion zone, if/when zone_context uses ''ingestion''.
If no rows match, view returns empty.
*/
CREATE OR REPLACE VIEW public.diag_ledger_ingestion_zone_envelope_violations AS
SELECT *
FROM public.diag_ledger_envelope_violations
WHERE zone_context = 'ingestion';

COMMENT ON VIEW public.diag_ledger_ingestion_zone_envelope_violations IS
'Diagnostics: envelope validation for event_ledger rows where zone_context = ingestion. Read-only.';


/*
Hash-chain diagnostics:
We do NOT attempt to recompute current_event_hash (function is defined in trigger).
We only validate linkage consistency using a deterministic reporting order (created_at, event_id) as tie-breaker.
*/
CREATE OR REPLACE VIEW public.diag_ledger_hash_chain_mismatch AS
WITH ordered AS (
  SELECT
    e.*,
    LAG(e.current_event_hash) OVER (ORDER BY e.created_at, e.event_id) AS expected_previous_event_hash
  FROM public.event_ledger e
)
SELECT
  event_id,
  created_at,
  event_timestamp,
  previous_event_hash,
  expected_previous_event_hash,
  current_event_hash
FROM ordered
WHERE
  -- if table empty or first row, expected prev is NULL, that's acceptable
  NOT (
    (expected_previous_event_hash IS NULL AND previous_event_hash IS NULL)
    OR
    (expected_previous_event_hash IS NOT NULL AND previous_event_hash = expected_previous_event_hash)
  );

COMMENT ON VIEW public.diag_ledger_hash_chain_mismatch IS
'Diagnostics: checks previous_event_hash linkage against lag(current_event_hash) over (created_at, event_id) ordering. Diagnostic only. Read-only.';


/*
Simple structural check: should be at most 1 chain head (previous_event_hash IS NULL), unless ledger is empty.
*/
CREATE OR REPLACE VIEW public.diag_ledger_hash_chain_head_count AS
SELECT
  COUNT(*) FILTER (WHERE previous_event_hash IS NULL) AS chain_heads,
  COUNT(*) AS total_events
FROM public.event_ledger;

COMMENT ON VIEW public.diag_ledger_hash_chain_head_count IS
'Diagnostics: counts chain head rows where previous_event_hash is NULL. Read-only.';



INSERT INTO public.schema_migrations(version)
VALUES ('014_event_emission_contract.sql');

COMMIT;
