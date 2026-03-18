#!/usr/bin/env bash
set -euo pipefail

echo "Phase 4C-lite: rebuild/reconciliation for core.document from ledger projection"

docker compose exec -T postgres psql -X -U fortress -d fortress -v ON_ERROR_STOP=1 <<'SQL'
BEGIN;

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
WHERE NOT EXISTS (
    SELECT 1
    FROM core.document d
    WHERE d.document_id = p.document_id
);

COMMIT;
SQL

echo "Rebuild/reconciliation completed."
