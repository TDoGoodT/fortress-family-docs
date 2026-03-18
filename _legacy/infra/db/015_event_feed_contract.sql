-- 015_event_feed_contract.sql
--
-- Version Authority (explicit):
-- - fortress.core.event-ledger.v1 (envelope + hash-chain invariants)
-- - fortress.project.version-governance.v1
-- - fortress.project.dependency-model.v2
--
-- Scope / Out of Scope:
-- - Views only (read-only contract). No materialized views.
-- - No triggers, no functions, no schema changes, no data fixes.
-- - No reliance on created_at as authoritative event ordering.
--
-- Ordering / Time Semantics:
-- - Authoritative semantic time: event_timestamp.
-- - Deterministic tie-breakers (diagnostic only): created_at, then event_id.
-- - The event feed defines a monotonic seq computed over the deterministic ordering above.
--
-- Naming:
-- - diag_ledger_* prefix reserved for diagnostics.
-- - ledger_* prefix used for consumer-facing read surfaces.

BEGIN;

-- Consumer-facing deterministic event feed over public.event_ledger.
-- Provides a stable monotonic seq cursor without introducing schema sequences.
CREATE OR REPLACE VIEW public.ledger_event_feed AS
SELECT
  row_number() OVER (
    ORDER BY
      el.event_timestamp ASC,
      el.created_at ASC,
      el.event_id ASC
  )::bigint AS seq,

  el.event_id,
  el.event_timestamp,

  el.aggregate_type,
  el.aggregate_id,
  el.event_type,

  el.correlation_id,
  el.causation_id,
  el.zone_context

FROM public.event_ledger el;

COMMENT ON VIEW public.ledger_event_feed IS
'Contract: deterministic, consumer-facing event feed over public.event_ledger.
Ordering: event_timestamp (semantic), then created_at and event_id as deterministic tie-breakers.
Cursor: seq = row_number() over the deterministic ordering.
Read-only view, no triggers/functions/schema changes.';

-- Optional helper: diagnostics-friendly cursor filter pattern example (still a view, not a function).
-- Consumers can query: SELECT * FROM public.ledger_event_feed WHERE seq > <cursor> ORDER BY seq LIMIT <n>;
-- Not materialized, no side effects.

INSERT INTO public.schema_migrations(version)
VALUES ('015_event_feed_contract.sql');

COMMIT;

