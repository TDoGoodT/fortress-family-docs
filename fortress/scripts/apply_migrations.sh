#!/usr/bin/env bash
set -euo pipefail

# Fortress 2.0 — Migration Runner
# Applies SQL migrations in alphabetical order, tracking state in schema_migrations.

DATABASE_URL="${DATABASE_URL:-postgresql://fortress:fortress_dev@localhost:5432/fortress}"

MIGRATIONS_DIR="$(cd "$(dirname "$0")/../migrations" && pwd)"

applied=0
skipped=0
failed=0

echo "=== Fortress Migration Runner ==="
echo "Database: ${DATABASE_URL}"
echo "Migrations: ${MIGRATIONS_DIR}"
echo ""

# Create schema_migrations tracking table if it doesn't exist
psql "${DATABASE_URL}" -q -c "
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ DEFAULT now()
);" 2>/dev/null

# Iterate migration files in alphabetical order
for migration in "${MIGRATIONS_DIR}"/*.sql; do
    [ -f "${migration}" ] || continue

    filename="$(basename "${migration}")"

    # Check if already applied
    already_applied=$(psql "${DATABASE_URL}" -tAc \
        "SELECT COUNT(*) FROM schema_migrations WHERE filename = '${filename}';")

    if [ "${already_applied}" -gt 0 ]; then
        echo "SKIP: ${filename} (already applied)"
        skipped=$((skipped + 1))
        continue
    fi

    # Apply migration
    if psql "${DATABASE_URL}" -q -f "${migration}" 2>&1; then
        # Record successful migration
        psql "${DATABASE_URL}" -q -c \
            "INSERT INTO schema_migrations (filename) VALUES ('${filename}');"
        echo "APPLIED: ${filename}"
        applied=$((applied + 1))
    else
        echo "FAILED: ${filename}"
        failed=$((failed + 1))
        echo ""
        echo "=== Summary ==="
        echo "Applied: ${applied} | Skipped: ${skipped} | Failed: ${failed}"
        exit 1
    fi
done

echo ""
echo "=== Summary ==="
echo "Applied: ${applied} | Skipped: ${skipped} | Failed: ${failed}"
