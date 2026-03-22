#!/usr/bin/env bash
set -euo pipefail

# Fortress 2.0 — Manual Scheduler Trigger
# Sends a POST request to the scheduler endpoint to trigger a daily run.

BASE_URL="${BASE_URL:-http://localhost:8000}"

echo "=== Fortress Scheduler — Manual Trigger ==="
echo "Endpoint: ${BASE_URL}/scheduler/run"
echo ""

curl -s -X POST "${BASE_URL}/scheduler/run" \
  -H "Content-Type: application/json" | python3 -m json.tool

echo ""
echo "Done."
