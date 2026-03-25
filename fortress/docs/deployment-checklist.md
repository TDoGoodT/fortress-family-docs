# Fortress — Deployment Checklist

## Prerequisites
- [ ] Mac Mini with Docker (OrbStack)
- [ ] Git installed
- [ ] AWS credentials (Access Key + Secret Key)
- [ ] Fortress phone with SIM

## Steps
1. Clone: `git clone https://github.com/Segway16/fortress-family.git`
2. Navigate: `cd fortress-family/fortress`
3. Create .env: `cp .env.example .env` → edit with real values
4. Create seed: `cp scripts/seed_family.sh.template scripts/seed_family.sh` → edit
5. Build: `docker compose up -d --build`
6. Wait: `sleep 20`
7. Migrations: run all .sql files in order
8. Seed: run seed_family.sh
9. Health: `curl http://localhost:8000/health`
10. WAHA: open http://localhost:3000, scan QR
11. Test: send "שלום" from phone
12. Dashboard: open http://localhost:8000/dashboard

## Post-Deploy Verification
- [ ] Health returns all services connected
- [ ] "שלום" returns personalized greeting
- [ ] "משימה חדשה: טסט" creates task
- [ ] "משימות" shows the task
- [ ] "מחק משימה 1" → confirm → deleted
- [ ] Photo upload → "שמרתי ✅" + classification
- [ ] "מסמכים" shows the upload
- [ ] "עזרה" shows skill list
- [ ] "באג: test" creates bug report
- [ ] Dashboard shows activity


## Deploy from WhatsApp

Allows parent-role users to trigger git pull + rebuild from WhatsApp.

### Setup

1. Generate secret: `openssl rand -hex 32`
2. Add to `.env`:
   ```
   DEPLOY_SECRET=<generated-secret>
   ```
3. Update the plist template with your paths:
   ```bash
   cp scripts/com.fortress.deploy-listener.plist ~/Library/LaunchAgents/
   # Edit the file: replace YOUR_USER and REPLACE_ME_WITH_GENERATED_SECRET
   ```
4. Start the listener:
   ```bash
   launchctl load ~/Library/LaunchAgents/com.fortress.deploy-listener.plist
   ```
5. Verify it's running:
   ```bash
   curl -X POST http://127.0.0.1:9111 \
     -H "Content-Type: application/json" \
     -d '{"token":"<your-secret>","action":"status"}'
   ```

### WhatsApp Commands (parent only)

| Command | Action |
|---------|--------|
| עדכן מערכת | git pull + docker build + restart |
| ריסטארט | restart fortress container |
| סטטוס מערכת | show container status |

### Security

- Listener binds to 127.0.0.1 only (no external access)
- Token from .env, never hardcoded
- Rate limit: 3 requests per 10 minutes
- Parent role required
