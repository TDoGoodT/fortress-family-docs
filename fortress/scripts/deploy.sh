#!/bin/bash
# Fortress remote deploy script — triggered via WhatsApp
# Runs on the Mac Mini host (NOT inside Docker)
set -euo pipefail

REPO_DIR="${FORTRESS_REPO_DIR:-$(dirname "$(dirname "$(dirname "$(realpath "$0")")")")}"
LOG_FILE="${REPO_DIR}/fortress/storage/deploy.log"
COMPOSE_FILE="${REPO_DIR}/fortress/docker-compose.yml"
ENV_FILE="${REPO_DIR}/fortress/.env"

# Ensure a valid working directory (launchd may start with a non-existent cwd)
cd /private/tmp

ACTION="${1:-deploy}"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log "=== Starting ${ACTION} ==="

case "$ACTION" in
    deploy)
        log "Pulling latest code..."
        git -C "$REPO_DIR" pull origin main >> "$LOG_FILE" 2>&1

        log "Building fortress container..."
        docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" build --no-cache fortress >> "$LOG_FILE" 2>&1

        log "Restarting fortress service (WAHA excluded)..."
        # --no-deps ensures only fortress restarts, never waha/db/ollama
        docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --no-deps fortress >> "$LOG_FILE" 2>&1

        log "Verifying WAHA session..."
        WAHA_API_KEY="$(grep '^WAHA_API_KEY' "$ENV_FILE" | cut -d= -f2)"
        WAHA_STATUS="$(curl -s "http://localhost:3000/api/sessions/default" -H "X-Api-Key: $WAHA_API_KEY" | grep -o '"status":"[^"]*"' | cut -d: -f2 | tr -d '"')"
        log "WAHA session status: $WAHA_STATUS"
        if [ "$WAHA_STATUS" != "WORKING" ]; then
            log "WARNING: WAHA session is $WAHA_STATUS — run: deploy.sh waha-restart"
        fi

        log "=== Deploy complete ==="
        ;;

    restart)
        log "Restarting fortress container..."
        docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" restart fortress >> "$LOG_FILE" 2>&1
        log "=== Restart complete ==="
        ;;

    waha-restart)
        log "Restarting WAHA container (explicit)..."
        docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" --profile waha restart waha >> "$LOG_FILE" 2>&1
        log "=== WAHA restart complete — re-scan QR if session is broken ==="
        ;;

    status)
        docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps 2>&1
        ;;

    *)
        echo "Usage: $0 {deploy|restart|waha-restart|status}"
        exit 1
        ;;
esac
