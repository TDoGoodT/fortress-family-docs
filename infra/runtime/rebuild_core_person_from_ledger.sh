#!/usr/bin/env bash
set -euo pipefail

echo "Rebuilding core.person from ledger projection (missing rows only)"

docker compose exec -T postgres psql -X -U fortress -d fortress -v ON_ERROR_STOP=1 <<'SQL'
BEGIN;

INSERT INTO core.person (
    person_id,
    household_id,
    display_name,
    created_at
)
SELECT
    p.person_id,
    p.household_id,
    p.display_name,
    p.created_at
FROM core.ledger_projection_person_created p
LEFT JOIN core.person c
    ON c.person_id = p.person_id
WHERE c.person_id IS NULL;

COMMIT;
SQL

echo "core.person rebuild completed."
