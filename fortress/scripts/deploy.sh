#!/bin/bash
# Fortress remote deploy script — triggered via WhatsApp
# Runs on the Mac Mini host (NOT inside Docker)
set -euo pipefail

REPO_DIR="${FORTRESS_REPO_DIR:-$(dirname "$(dirname "$(dirname "$(realpath "$0")")")")}"
LOG_FILE="${HOME}/fortress-scripts/deploy.log"
COMPOSE_FILE="${REPO_DIR}/fortress/docker-compose.yml"

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
        docker compose --env-file "$REPO_DIR/fortress/.env" -f "$COMPOSE_FILE" build --no-cache fortress >> "$LOG_FILE" 2>&1

        log "Restarting services..."
        docker compose --env-file "$REPO_DIR/fortress/.env" -f "$COMPOSE_FILE" up -d >> "$LOG_FILE" 2>&1

        log "=== Deploy complete ==="
        ;;

    restart)
        log "Restarting fortress container..."
        docker compose --env-file "$REPO_DIR/fortress/.env" -f "$COMPOSE_FILE" restart fortress >> "$LOG_FILE" 2>&1
        log "=== Restart complete ==="
        ;;

    status)
        docker compose -f "$COMPOSE_FILE" ps 2>&1
        ;;

    *)
        echo "Usage: $0 {deploy|restart|status}"
        exit 1
        ;;
esac
