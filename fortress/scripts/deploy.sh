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
        COMMIT=$(git -C "$REPO_DIR" rev-parse --short HEAD)

        log "Building fortress container..."
        docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" build --no-cache fortress >> "$LOG_FILE" 2>&1

        log "Restarting fortress service (WAHA excluded)..."
        docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --no-deps fortress >> "$LOG_FILE" 2>&1

        sleep 10

        HEALTH=$(curl -s http://localhost:8000/health 2>/dev/null || echo '{}')
        if echo "$HEALTH" | grep -q '"status":"ok"'; then
            echo "🟢 הקוד עודכן ✅ | גרסה: $COMMIT"
        else
            echo "🟡 העדכון הושלם אבל המערכת לא מגיבה. גרסה: $COMMIT"
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
        COMMIT=$(git -C "$REPO_DIR" rev-parse --short HEAD)

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
            echo "🟢 עדכון מלא הושלם ✅ | גרסה: $COMMIT"
        else
            echo "🟡 העדכון הושלם אבל המערכת לא מגיבה. גרסה: $COMMIT"
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
        # Disable strict mode for status — subcommands may fail gracefully
        set +e
        set +o pipefail

        ERRORS=()

        run_quick() {
            "$@" 2>/dev/null
            return $?
        }

        git_info() {
            COMMIT=$(git -C "$REPO_DIR" rev-parse --short HEAD 2>/dev/null || echo 'unknown')
            BRANCH=$(git -C "$REPO_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'unknown')
            SUBJECT=$(git -C "$REPO_DIR" log -1 --pretty=%s 2>/dev/null || echo 'unknown')
            if ! git -C "$REPO_DIR" diff --quiet --ignore-submodules -- 2>/dev/null || \
               ! git -C "$REPO_DIR" diff --cached --quiet --ignore-submodules -- 2>/dev/null; then
                TREE_STATE="dirty"
            else
                TREE_STATE="clean"
            fi
        }

        container_status() {
            local cname="$1"
            local label="$2"
            local status
            status=$(run_quick docker inspect --format '{{.State.Status}}|{{.State.Health.Status}}|{{.State.RunningFor}}' "$cname")
            if [ $? -ne 0 ] || [ -z "$status" ]; then
                ERRORS+=("$label: לא ניתן לקבל סטטוס קונטיינר")
                echo "⚪ לא ידוע"
                return
            fi

            local state health uptime
            IFS='|' read -r state health uptime <<< "$status"
            uptime="${uptime:-ללא מידע}"
            if [ "$state" = "running" ] && [ "$health" = "healthy" ]; then
                echo "🟢 פעיל ותקין ($uptime)"
            elif [ "$state" = "running" ]; then
                echo "🟡 פעיל ($uptime)"
            else
                echo "🔴 לא פעיל ($state)"
            fi
        }

        health_status() {
            local health_json
            health_json=$(run_quick curl -s --max-time 8 http://localhost:8000/health)
            if [ $? -ne 0 ] || [ -z "$health_json" ]; then
                ERRORS+=("health: לא ניתן להגיע ל-/health")
                echo "לא זמין"
                return
            fi

            echo "$health_json" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    db = '🟢' if data.get('database') == 'connected' else '🔴'
    bedrock = '🟢' if data.get('bedrock') == 'connected' else '🔴'
    ollama_s = '🟢' if data.get('ollama') == 'connected' else '🔴'
    version = data.get('version', 'unknown')
    print(f'DB: {db} | Bedrock: {bedrock} | Ollama: {ollama_s} | App Version: {version}')
except Exception:
    print('לא זמין')
" 2>/dev/null
            if [ ${PIPESTATUS[1]} -ne 0 ]; then
                ERRORS+=("health: תגובת health לא בפורמט צפוי")
            fi
        }

        git_info
        APP=$(container_status "fortress-app" "app")
        DB=$(container_status "fortress-db" "db")
        OLLAMA=$(container_status "fortress-ollama" "ollama")
        WAHA=$(container_status "fortress-waha" "waha")
        HEALTH=$(health_status)

        echo "🏰 סטטוס פורטרס
📌 גרסה רצה: $COMMIT
🌿 branch: $BRANCH
📝 commit: $SUBJECT
🧹 working tree: $TREE_STATE

📦 שירותים:
  אפליקציה: $APP
  בסיס נתונים: $DB
  Ollama: $OLLAMA
  WhatsApp: $WAHA

🔗 חיבורים:
  $HEALTH

📊 דשבורד: http://localhost:8000/dashboard"
        if [ "${#ERRORS[@]}" -gt 0 ]; then
            printf "\n⚠️ בדיקות חלקיות נכשלו:\n"
            for err in "${ERRORS[@]}"; do
                printf "• %s\n" "$err"
            done
        fi
        ;;

    *)
        echo "Usage: $0 {deploy_app|deploy_db|deploy_all|restart|waha-restart|status}"
        exit 1
        ;;
esac
