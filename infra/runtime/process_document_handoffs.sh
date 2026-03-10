#!/usr/bin/env bash
set -euo pipefail

HANDOFF_IDS="$(
  docker compose exec -T postgres psql -X -A -t -U fortress -d fortress -v ON_ERROR_STOP=1 <<'SQL'
SELECT c.causation_id::text
FROM core.ledger_contract_document_created c
ORDER BY c.event_timestamp, c.causation_id;
SQL
)"

if [ -z "${HANDOFF_IDS}" ]; then
  echo "No eligible document handoffs found in core.ledger_contract_document_created"
  exit 0
fi

while IFS= read -r HANDOFF_REQUEST_ID; do
  [ -z "${HANDOFF_REQUEST_ID}" ] && continue

  echo "Processing handoff_request_id=${HANDOFF_REQUEST_ID}"

  docker compose exec -T postgres psql -X -U fortress -d fortress \
    -v ON_ERROR_STOP=1 \
    -v handoff_request_id="${HANDOFF_REQUEST_ID}" <<'SQL'
BEGIN;
SELECT set_config('app.handoff_request_id', :'handoff_request_id', true);

DO $$
DECLARE
    v_handoff_request_id uuid := current_setting('app.handoff_request_id')::uuid;
    v_contract RECORD;
    v_event_id uuid;
    v_receipt_exists boolean;
    v_event_exists boolean;
    v_document_exists boolean;
BEGIN
    /*
      Primary idempotency gate:
      - receipt exists => already processed, skip
      - no receipt => event/document existence means inconsistent partial state
    */
    SELECT EXISTS (
        SELECT 1
        FROM core.canonical_handoff_receipt r
        WHERE r.handoff_request_id = v_handoff_request_id
    )
    INTO v_receipt_exists;

    IF v_receipt_exists THEN
        RAISE NOTICE 'Skipping %, receipt already exists', v_handoff_request_id;
        RETURN;
    END IF;

    /*
      Select exactly one contract row for this handoff_request_id.
      This row is the sole source for all writes in this transaction.
    */
    SELECT
        c.aggregate_type,
        c.aggregate_id,
        c.event_type,
        c.payload,
        c.actor_type,
        c.actor_id,
        c.zone_context,
        c.correlation_id,
        c.causation_id,
        c.event_timestamp,
        c.valid_timestamp,
        c.emit_dedup_key
    INTO v_contract
    FROM core.ledger_contract_document_created c
    WHERE c.causation_id = v_handoff_request_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'No eligible contract row found for handoff_request_id=%', v_handoff_request_id;
    END IF;

    /*
      Consistency check only, not primary processing gate:
      detect whether the exact canonical event already exists without a receipt.
    */
    SELECT EXISTS (
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
        ) = v_contract.emit_dedup_key
    )
    INTO v_event_exists;

    IF v_event_exists THEN
        RAISE EXCEPTION
            'Inconsistent partial state: matching event already exists without receipt for handoff_request_id=%',
            v_handoff_request_id;
    END IF;

    /*
      Consistency check only:
      target document must not already exist without a receipt.
    */
    SELECT EXISTS (
        SELECT 1
        FROM core.document d
        WHERE d.document_id = v_contract.aggregate_id
    )
    INTO v_document_exists;

    IF v_document_exists THEN
        RAISE EXCEPTION
            'Inconsistent partial state: document already exists without receipt for handoff_request_id=% document_id=%',
            v_handoff_request_id,
            v_contract.aggregate_id;
    END IF;

    /*
      First canonical write:
      insert event, capture exact event_id
    */
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
    VALUES (
        v_contract.aggregate_type,
        v_contract.aggregate_id,
        v_contract.event_type,
        v_contract.payload,
        v_contract.actor_type,
        v_contract.actor_id,
        v_contract.zone_context,
        v_contract.correlation_id,
        v_contract.causation_id,
        v_contract.event_timestamp,
        v_contract.valid_timestamp
    )
    RETURNING event_id
    INTO v_event_id;

    /*
      Second canonical write:
      materialize core.document from the inserted event via projection rule
    */
    INSERT INTO core.document (
        document_id,
        household_id,
        document_type,
        title,
        source_uri
    )
    SELECT
        p.document_id,
        p.household_id,
        p.document_type,
        p.title,
        p.source_uri
    FROM core.ledger_projection_document_created p
    WHERE p.event_id = v_event_id
      AND NOT EXISTS (
          SELECT 1
          FROM core.document d
          WHERE d.document_id = p.document_id
      );

    /*
      Final canonical write:
      receipt row = acceptance
      applied_event_id must be the exact inserted event_id
    */
    INSERT INTO core.canonical_handoff_receipt (
        handoff_request_id,
        applied_event_id
    )
    VALUES (
        v_contract.causation_id,
        v_event_id
    );

    RAISE NOTICE 'Applied handoff_request_id=%, event_id=%, document_id=%',
        v_contract.causation_id,
        v_event_id,
        v_contract.aggregate_id;
END
$$;

COMMIT;
SQL
done <<< "${HANDOFF_IDS}"
