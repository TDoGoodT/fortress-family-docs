#!/usr/bin/env bash
# Fortress 2.0 — Wait for Ollama to be ready, then pull the required model.
set -euo pipefail

CONTAINER="${OLLAMA_CONTAINER:-fortress-ollama}"
MODEL="${OLLAMA_MODEL:-llama3.1:8b}"
MAX_RETRIES=30
RETRY_INTERVAL=2

echo "⏳ Waiting for Ollama container ($CONTAINER) to be ready..."

for i in $(seq 1 $MAX_RETRIES); do
    if docker exec "$CONTAINER" curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo "✅ Ollama is ready."
        break
    fi
    if [ "$i" -eq "$MAX_RETRIES" ]; then
        echo "❌ Ollama did not become ready after $((MAX_RETRIES * RETRY_INTERVAL))s." >&2
        exit 1
    fi
    echo "  Attempt $i/$MAX_RETRIES — retrying in ${RETRY_INTERVAL}s..."
    sleep "$RETRY_INTERVAL"
done

echo "⏳ Pulling model: $MODEL (this may take a while on first run)..."
if ! docker exec "$CONTAINER" ollama pull "$MODEL"; then
    echo "❌ Failed to pull model $MODEL." >&2
    exit 1
fi

echo "🔍 Verifying model is available..."
if docker exec "$CONTAINER" ollama list | grep -q "$MODEL"; then
    echo "✅ Model $MODEL is ready."
else
    echo "❌ Model $MODEL not found after pull." >&2
    exit 1
fi

echo "🎉 Ollama setup complete."
