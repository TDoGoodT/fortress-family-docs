#!/usr/bin/env bash
set -euo pipefail

if [ "${1:-}" = "" ]; then
  echo "Usage: $0 <run_id>" >&2
  exit 1
fi

RUN_ID="$1"

EMIT_SEQS="$(
  docker compose exec -T postgres psql -X -A -t -U fortress -d fortress -v ON_ERROR_STOP=1 -v run_id="$RUN_ID" <<'SQL'
SELECT q.emit_seq::text
FROM ingestion.ledger_contract_emit_queue q
WHERE q.emit_scope_id = :'run_id'::uuid
  AND NOT EXISTS (
    SELECT 1
    FROM public.event_ledger el
    WHERE encode(
            digest(
              concat_ws(
                '|',
                el.correlation_id::text,
                el.aggregate_type,
                el.aggregate_id::text,
                el.event_type,
                md5(el.payload::text)
              ),
              'sha256'
            ),
            'hex'
          ) = q.emit_dedup_key
  )
ORDER BY q.emit_seq;
SQL
)"

if [ -z "${EMIT_SEQS}" ]; then
  echo "No eligible events found for emit_scope_id=${RUN_ID}"
  exit 0
fi

while IFS= read -r EMIT_SEQ; do
  [ -z "${EMIT_SEQ}" ] && continue

  echo "Emitting emit_scope_id=${RUN_ID} emit_seq=${EMIT_SEQ}"

  docker compose exec -T postgres psql -X -U fortress -d fortress \
    -v ON_ERROR_STOP=1 \
    -v run_id="${RUN_ID}" \
    -v emit_seq="${EMIT_SEQ}" <<'SQL'
BEGIN;

INSERT INTO public.event_ledger (
    aggregate_type,
    aggregate_id,
    event_type,
    payload,
    actor_type,
    actor_id,
    zone_context,
    correlation_id,
    causation_id,
    event_timestamp,
    valid_timestamp
)
SELECT
    q.aggregate_type,
    q.aggregate_id,
    q.event_type,
    q.payload,
    q.actor_type,
    q.actor_id,
    q.zone_context,
    q.correlation_id,
    q.causation_id,
    q.event_timestamp,
    q.valid_timestamp
FROM ingestion.ledger_contract_emit_queue q
WHERE q.emit_scope_id = :'run_id'::uuid
  AND q.emit_seq = :'emit_seq'::integer
  AND NOT EXISTS (
    SELECT 1
    FROM public.event_ledger el
    WHERE encode(
            digest(
              concat_ws(
                '|',
                el.correlation_id::text,
                el.aggregate_type,
                el.aggregate_id::text,
                el.event_type,
                md5(el.payload::text)
              ),
              'sha256'
            ),
            'hex'
          ) = q.emit_dedup_key
  );

COMMIT;
SQL
done <<< "${EMIT_SEQS}"
