#!/bin/bash
export PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"
# Fortress remote deploy script — triggered via WhatsApp
# Runs on the Mac Mini host (NOT inside Docker)
set -euo pipefail

REPO_DIR="${FORTRESS_REPO_DIR:-$(dirname "$(dirname "$(dirname "$(realpath "$0")")")")}"
LOG_FILE="${REPO_DIR}/fortress/storage/deploy.log"
COMPOSE_FILE="${REPO_DIR}/fortress/docker-compose.yml"
ENV_FILE="${REPO_DIR}/fortress/.env"

# Ensure a valid working directory (launchd may start with a non-existent cwd)
cd /private/tmp

ACTION="${1:-deploy_all}"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

log "=== Starting ${ACTION} ==="

case "$ACTION" in
    deploy_app)
        log "Pulling latest code..."
        git -C "$REPO_DIR" pull origin main >> "$LOG_FILE" 2>&1

        log "Building fortress container..."
        docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" build --no-cache fortress >> "$LOG_FILE" 2>&1

        log "Restarting fortress service (WAHA excluded)..."
        docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --no-deps fortress >> "$LOG_FILE" 2>&1

        sleep 10

        HEALTH=$(curl -s http://localhost:8000/health 2>/dev/null || echo '{}')
        if echo "$HEALTH" | grep -q '"status":"ok"'; then
            echo "🟢 העדכון הושלם בהצלחה ✅"
        else
            echo "🟡 העדכון הושלם אבל המערכת לא מגיבה עדיין. נסה שוב בעוד דקה."
        fi

        log "=== APP UPDATE complete ==="
        ;;

    deploy_db)
        log "Running migrations..."
        for f in "$REPO_DIR"/fortress/migrations/*.sql; do
            log "Applying $f..."
            docker exec -i fortress-db psql -U fortress -d fortress < "$f" 2>&1 | tail -1 | tee -a "$LOG_FILE"
        done
        log "=== DB UPDATE complete ==="
        ;;

    deploy_all)
        log "Pulling latest code..."
        git -C "$REPO_DIR" pull origin main >> "$LOG_FILE" 2>&1

        log "Building and restarting all services..."
        docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --build >> "$LOG_FILE" 2>&1

        log "Waiting for services to stabilize..."
        sleep 15

        log "Running migrations..."
        for f in "$REPO_DIR"/fortress/migrations/*.sql; do
            log "Applying $f..."
            docker exec -i fortress-db psql -U fortress -d fortress < "$f" 2>&1 | tail -1 | tee -a "$LOG_FILE"
        done

        log "Verifying WAHA session..."
        WAHA_API_KEY="$(grep '^WAHA_API_KEY' "$ENV_FILE" | cut -d= -f2)"
        WAHA_STATUS="$(curl -s "http://localhost:3000/api/sessions/default" -H "X-Api-Key: $WAHA_API_KEY" | grep -o '"status":"[^"]*"' | cut -d: -f2 | tr -d '"')"
        log "WAHA session status: $WAHA_STATUS"
        if [ "$WAHA_STATUS" != "WORKING" ]; then
            log "WARNING: WAHA session is $WAHA_STATUS — run: deploy.sh waha-restart"
        fi

        sleep 10

        HEALTH=$(curl -s http://localhost:8000/health 2>/dev/null || echo '{}')
        if echo "$HEALTH" | grep -q '"status":"ok"'; then
            echo "🟢 עדכון מלא הושלם בהצלחה ✅"
        else
            echo "🟡 העדכון הושלם אבל המערכת לא מגיבה עדיין. נסה שוב בעוד דקה."
        fi

        log "=== FULL UPDATE complete ==="
        ;;

    deploy)
        # Legacy alias for deploy_all
        exec "$0" deploy_all
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
        DC="docker compose --env-file $ENV_FILE -f $COMPOSE_FILE"

        APP=$($DC ps --format json fortress 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    state = data.get('State', 'unknown')
    uptime = data.get('Status', '')
    if state == 'running':
        print(f'🟢 פעיל ({uptime})')
    else:
        print(f'🔴 לא פעיל ({state})')
except: print('⚪ לא ידוע')
" 2>/dev/null || echo '⚪ לא ידוע')

        DB=$($DC ps --format json db 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    state = data.get('State', 'unknown')
    uptime = data.get('Status', '')
    if 'healthy' in uptime.lower():
        print(f'🟢 תקין ({uptime})')
    elif state == 'running':
        print(f'🟡 פעיל ({uptime})')
    else:
        print(f'🔴 לא פעיל ({state})')
except: print('⚪ לא ידוע')
" 2>/dev/null || echo '⚪ לא ידוע')

        OLLAMA=$($DC ps --format json ollama 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    state = data.get('State', 'unknown')
    uptime = data.get('Status', '')
    if state == 'running':
        print(f'🟢 פעיל ({uptime})')
    else:
        print(f'🔴 לא פעיל ({state})')
except: print('⚪ לא ידוע')
" 2>/dev/null || echo '⚪ לא ידוע')

        WAHA=$($DC ps --format json waha 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    state = data.get('State', 'unknown')
    uptime = data.get('Status', '')
    if state == 'running':
        print(f'🟢 פעיל ({uptime})')
    else:
        print(f'🔴 לא פעיל ({state})')
except: print('⚪ לא ידוע')
" 2>/dev/null || echo '⚪ לא ידוע')

        HEALTH=$(curl -s http://localhost:8000/health 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    db = '🟢' if data.get('database') == 'connected' else '🔴'
    bedrock = '🟢' if data.get('bedrock') == 'connected' else '🔴'
    ollama_s = '🟢' if data.get('ollama') == 'connected' else '🔴'
    print(f'DB: {db} | Bedrock: {bedrock} | Ollama: {ollama_s}')
except: print('לא זמין')
" 2>/dev/null || echo 'לא זמין')

        echo "🏰 סטטוס פורטרס

📦 שירותים:
  אפליקציה: $APP
  בסיס נתונים: $DB
  Ollama: $OLLAMA
  WhatsApp: $WAHA

🔗 חיבורים:
  $HEALTH

📊 דשבורד: http://localhost:8000/dashboard"
        ;;

    *)
        echo "Usage: $0 {deploy_app|deploy_db|deploy_all|restart|waha-restart|status}"
        exit 1
        ;;
esac
