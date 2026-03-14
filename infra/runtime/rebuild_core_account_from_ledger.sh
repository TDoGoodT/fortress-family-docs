#!/usr/bin/env bash
set -euo pipefail

echo "Rebuilding core.account from normalized ledger projection (missing rows only)"

docker compose exec -T postgres psql -X -U fortress -d fortress -v ON_ERROR_STOP=1 <<'SQL'
BEGIN;

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
LEFT JOIN core.account a
  ON a.account_id = p.account_id
WHERE a.account_id IS NULL;

COMMIT;
SQL

echo "core.account rebuild completed."
