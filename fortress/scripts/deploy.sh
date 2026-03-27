#!/bin/bash
# Fortress remote deploy script — triggered via WhatsApp
# Runs on the Mac Mini host (NOT inside Docker)
set -euo pipefail

REPO_DIR="${FORTRESS_REPO_DIR:-$(dirname "$(dirname "$(dirname "$(realpath "$0")")")")}"
LOG_FILE="${REPO_DIR}/fortress/storage/deploy.log"
COMPOSE_FILE="${REPO_DIR}/fortress/docker-compose.yml"

ACTION="${1:-deploy}"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log "=== Starting ${ACTION} ==="

case "$ACTION" in
    deploy)
        log "Pulling latest code..."
        cd "$REPO_DIR"
        git pull origin main 2>&1 | tee -a "$LOG_FILE"

        log "Building fortress container..."
        docker compose -f "$COMPOSE_FILE" build --no-cache fortress 2>&1 | tee -a "$LOG_FILE"

        log "Restarting services..."
        docker compose -f "$COMPOSE_FILE" up -d 2>&1 | tee -a "$LOG_FILE"

        log "=== Deploy complete ==="
        ;;

    restart)
        log "Restarting fortress container..."
        docker compose -f "$COMPOSE_FILE" restart fortress 2>&1 | tee -a "$LOG_FILE"
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
