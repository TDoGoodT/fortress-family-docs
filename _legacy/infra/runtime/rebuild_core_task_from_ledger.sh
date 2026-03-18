#!/usr/bin/env bash
set -euo pipefail

echo "Rebuilding core.task from ledger projection (missing rows only)"

docker compose exec -T postgres psql -X -U fortress -d fortress -v ON_ERROR_STOP=1 <<'SQL'
BEGIN;

INSERT INTO core.task (
    task_id,
    household_id,
    title,
    status,
    created_at
)
SELECT
    p.task_id,
    p.household_id,
    p.title,
    p.status,
    p.created_at
FROM core.ledger_projection_task_created p
LEFT JOIN core.task c
    ON c.task_id = p.task_id
WHERE c.task_id IS NULL;

COMMIT;
SQL

echo "core.task rebuild completed."
