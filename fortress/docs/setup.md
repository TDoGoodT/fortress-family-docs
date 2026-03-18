# Fortress — Mac Mini Deployment Guide

## Prerequisites

- Mac Mini M4 with macOS
- Docker Desktop for Mac installed and running
- Git installed
- The Fortress phone (with SIM) nearby for QR scanning

## Quick Setup

```bash
git clone <repo-url>
cd fortress
cp scripts/seed_family.sh.template scripts/seed_family.sh
# Edit seed_family.sh with real phone numbers
./scripts/setup_mac_mini.sh
```

The setup script handles everything: Docker services, database migrations,
seeding, and health checks.

## WhatsApp Setup

1. Open http://localhost:3000
2. Click "Start New Session" → session name: `default`
3. Scan QR code with the Fortress phone
4. Session persists across restarts (stored in `waha_sessions` volume)

## Verification

Send a test message from your phone to the Fortress number:

| Message | Expected Response |
|---------|-------------------|
| שלום | Acknowledgment response |
| משימות | Task list or "אין משימות פתוחות" |

### Manual health checks

```bash
# API health
curl http://localhost:8000/health

# WAHA status
curl http://localhost:3000/api/sessions

# Database connectivity
docker compose exec db psql -U fortress -c "SELECT count(*) FROM family_members;"
```

## Troubleshooting

### WAHA shows disconnected

Restart the session and re-scan the QR code:

1. Open http://localhost:3000
2. Stop the existing session
3. Start a new session and scan QR again

### API returns database disconnected

Check the database container logs:

```bash
docker compose logs db
docker compose restart db
# Wait for healthy, then restart app
docker compose restart fortress
```

### No response on WhatsApp

Check the webhook URL in WAHA config:

```bash
docker compose logs waha
# Verify WHATSAPP_HOOK_URL points to http://fortress-app:8000/webhook/whatsapp
```

## NAS Setup (Optional)

To store documents on a NAS instead of local disk:

1. Mount NAS to `~/fortress_nas`
2. Update `STORAGE_PATH` in `.env` to point to the NAS mount
3. Restart: `docker compose restart fortress`

## Backup

### Database

```bash
docker compose exec db pg_dump -U fortress fortress > backup.sql
```

### Files

Use rsync or Restic to back up `~/fortress_storage/` to Backblaze B2
or another remote target.

Full backup automation coming in a future phase.
