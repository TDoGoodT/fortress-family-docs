#!/usr/bin/env bash
set -euo pipefail

HANDOFF_IDS="$(
  docker compose exec -T postgres psql -X -A -t -U fortress -d fortress -v ON_ERROR_STOP=1 <<'SQL'
SELECT c.causation_id::text
FROM core.ledger_contract_account_created c
ORDER BY c.event_timestamp, c.causation_id;
SQL
)"

if [ -z "${HANDOFF_IDS}" ]; then
  echo "No eligible account handoffs found in core.ledger_contract_account_created"
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
    v_account_exists boolean;
BEGIN
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
    FROM core.ledger_contract_account_created c
    WHERE c.causation_id = v_handoff_request_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'No eligible contract row found for handoff_request_id=%', v_handoff_request_id;
    END IF;

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

    SELECT EXISTS (
        SELECT 1
        FROM core.account a
        WHERE a.account_id = v_contract.aggregate_id
    )
    INTO v_account_exists;

    IF v_account_exists THEN
        RAISE EXCEPTION
            'Inconsistent partial state: account already exists without receipt for handoff_request_id=% account_id=%',
            v_handoff_request_id,
            v_contract.aggregate_id;
    END IF;

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

    INSERT INTO core.account (
        account_id,
        household_id,
        account_label,
        account_kind,
        created_at
    )
    SELECT
        p.account_id,
        p.household_id,
        p.account_label,
        p.account_kind,
        p.created_at
    FROM core.ledger_projection_account_created p
    WHERE p.event_id = v_event_id
      AND NOT EXISTS (
          SELECT 1
          FROM core.account ca
          WHERE ca.account_id = p.account_id
      );

    INSERT INTO core.canonical_handoff_receipt (
        handoff_request_id,
        applied_event_id
    )
    VALUES (
        v_contract.causation_id,
        v_event_id
    );

    RAISE NOTICE 'Applied handoff_request_id=%, event_id=%, account_id=%',
        v_contract.causation_id,
        v_event_id,
        v_contract.aggregate_id;
END
$$;

COMMIT;
SQL
done <<< "${HANDOFF_IDS}"
