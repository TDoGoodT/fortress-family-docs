#!/bin/bash
# setup_mac_mini.sh — One-time setup for Fortress on Mac Mini M4
# Idempotent: safe to run multiple times.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── 1. Check Docker ──────────────────────────────────────────────
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker Desktop and try again."
    exit 1
fi
echo "✅ Docker is running"

if ! docker compose version > /dev/null 2>&1; then
    echo "❌ docker compose not found. Please install Docker Desktop (includes Compose V2)."
    exit 1
fi
echo "✅ docker compose is available"

# ── 2. Environment file ─────────────────────────────────────────
cd "$PROJECT_DIR"

if [ -f .env ]; then
    echo "✅ .env already exists — skipping"
else
    cp .env.example .env
    echo "Created .env from .env.example"
    read -rp "Enter DB password (or press Enter for default 'fortress_dev'): " db_pass
    if [ -n "$db_pass" ]; then
        sed -i.bak "s/^DB_PASSWORD=.*/DB_PASSWORD=$db_pass/" .env && rm -f .env.bak
        echo "✅ DB password updated in .env"
    else
        echo "✅ Using default DB password"
    fi
fi

# ── 3. Local storage directories ─────────────────────────────────
mkdir -p ~/fortress_storage/documents
mkdir -p ~/fortress_storage/backup
echo "✅ Storage directories ready (~/fortress_storage/)"

# ── 4. Start services ────────────────────────────────────────────
echo ""
echo "=== Starting Docker Compose services ==="
docker compose up -d
echo "✅ Services started"

# ── 5. Wait for database ─────────────────────────────────────────
echo ""
echo "Waiting for database to be healthy..."
MAX_RETRIES=30
RETRY_INTERVAL=2
for i in $(seq 1 $MAX_RETRIES); do
    if docker compose exec -T db pg_isready -U fortress > /dev/null 2>&1; then
        echo "✅ Database is healthy"
        break
    fi
    if [ "$i" -eq "$MAX_RETRIES" ]; then
        echo "❌ Database did not become healthy after $((MAX_RETRIES * RETRY_INTERVAL))s"
        echo "   Check logs: docker compose logs db"
        exit 1
    fi
    sleep $RETRY_INTERVAL
done

# ── 6. Apply migrations ──────────────────────────────────────────
echo ""
echo "=== Applying database migrations ==="
for migration in migrations/*.sql; do
    echo "  Applying $(basename "$migration")..."
    docker compose exec -T db psql -U fortress -d fortress < "$migration"
done
echo "✅ Migrations applied"

# ── 7. Seed family members ────────────────────────────────────────
echo ""
if [ -f scripts/seed_family.sh ]; then
    echo "=== Running seed script ==="
    bash scripts/seed_family.sh
    echo "✅ Family members seeded"
else
    echo "⚠️  scripts/seed_family.sh not found"
    echo "   To seed family members:"
    echo "   1. cp scripts/seed_family.sh.template scripts/seed_family.sh"
    echo "   2. Edit with real phone numbers"
    echo "   3. Run: ./scripts/seed_family.sh"
fi

# ── 8. Health checks ─────────────────────────────────────────────
echo ""
echo "=== Health Checks ==="

# API health
if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ API is healthy (http://localhost:8000/health)"
else
    echo "❌ API not responding at http://localhost:8000/health"
fi

# WAHA status
if curl -sf http://localhost:3000/api/sessions > /dev/null 2>&1; then
    echo "✅ WAHA is running (http://localhost:3000/api/sessions)"
else
    echo "❌ WAHA not responding at http://localhost:3000/api/sessions"
fi

# ── 9. Summary ────────────────────────────────────────────────────
echo ""
echo "========================================="
echo "  Fortress setup complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo "  1. Open http://localhost:3000"
echo "  2. Scan QR code with Fortress phone"
echo "  3. Send a test message"
echo ""
