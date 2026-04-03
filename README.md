# Fortress Family Repository

Practical operator/developer guide for the current Fortress system.

## What Fortress is today

Fortress is a FastAPI service that acts as a WhatsApp family assistant through WAHA. It handles deterministic command-driven workflows (tasks, recurring reminders, documents, bug reports, deploy/status commands, memory list, morning summary) and uses LLM services when needed. The current runtime path is:

`WhatsApp -> WAHA -> Fortress API -> Postgres` (with Bedrock/Ollama connectivity checks in health).

## Quick start (first run)

From repo root:

```bash
cd fortress
cp .env.example .env
docker compose up -d
bash scripts/apply_migrations.sh
curl -s http://localhost:8000/health
```

> WAHA is **not** started by default by `docker compose up -d` because it is behind a profile. Start it explicitly with `docker compose --profile waha up -d` when you need WhatsApp connectivity.

## Canonical repo layout

The repository root is mainly a wrapper; the app lives under `fortress/`.

```text
.
├─ README.md                      # canonical entry doc (this file)
└─ fortress/
   ├─ src/                        # FastAPI app, routers, services, skills
   ├─ migrations/                 # SQL migrations (001..009)
   ├─ scripts/                    # setup/deploy/migrations/ops scripts
   ├─ tests/                      # pytest suite
   ├─ docker-compose.yml          # db/app/ollama/waha services
   ├─ Dockerfile
   └─ .env.example
```

## Where to work from

- For source edits, tests, compose, and scripts: `cd fortress`.
- Most commands in this README assume you are already inside `fortress/`.

```bash
cd fortress
```

## Local development workflow

1. Create env file and fill required values.

```bash
cp .env.example .env
# Required in practice: DB_PASSWORD, WAHA_API_KEY, ADMIN_PHONE, BEDROCK_API_KEY
```

2. Start core containers.

```bash
docker compose up -d
```

3. Apply migrations (idempotent, tracks applied files in `schema_migrations`).

```bash
bash scripts/apply_migrations.sh
```

4. Seed family members (optional but needed for real usage).

```bash
cp scripts/seed_family.sh.template scripts/seed_family.sh
# edit scripts/seed_family.sh
bash scripts/seed_family.sh
```

5. Start WAHA profile (not started by default in base `docker compose up`).

```bash
docker compose --profile waha up -d
```

6. Verify app + dashboard.

```bash
curl -s http://localhost:8000/health
open http://localhost:8000/dashboard
```

## Docker / Compose usage

Services in `docker-compose.yml`:

- `db` (`fortress-db`) - PostgreSQL 16
- `fortress` (`fortress-app`) - FastAPI app on port `8000`
- `ollama` (`fortress-ollama`) - local model runtime (still present)
- `waha` (`fortress-waha`) - WhatsApp bridge, behind `waha` compose profile

Useful commands:

```bash
# build or rebuild app image
docker compose build fortress

# restart only app
docker compose restart fortress

# start WAHA when needed (explicit; not part of default profile)
docker compose --profile waha up -d waha

# logs
docker compose logs -f fortress
docker compose logs -f waha
```

## Deployment flow (Mac Mini)

### One-time setup on host

From `fortress/`:

```bash
bash scripts/setup_mac_mini.sh
```

For WhatsApp-triggered deploys, run deploy listener on the host (not inside the app container):

```bash
export DEPLOY_SECRET='<same secret as .env>'
python3 scripts/deploy_listener.py
```

### Safe deploy procedure

Preferred explicit actions (from host):

```bash
bash scripts/deploy.sh deploy_app   # code/container only
bash scripts/deploy.sh deploy_db    # migrations only
bash scripts/deploy.sh deploy_all   # pull + rebuild + migrations
bash scripts/deploy.sh status       # runtime status summary
```

`deploy_all` runs `git pull`, `docker compose up -d --build`, applies all SQL migrations, then checks `/health` and WAHA session status.

## WhatsApp / WAHA integration

- WAHA sends webhook events to `http://fortress-app:8000/webhook/whatsapp`.
- API key auth is passed via `X-Api-Key` header.
- WAHA dashboard defaults to `http://localhost:3000`.
- Deploy skill supports parent/admin-only remote commands (status/deploy/restart) via deploy listener.
- WAHA is behind the compose `waha` profile and stays down unless you explicitly run with `--profile waha`.

Typical WAHA bring-up:

```bash
docker compose --profile waha up -d
# then open http://localhost:3000 and scan QR for session: default
```

## Document ingestion flow (high-level)

Current operational path for incoming WhatsApp documents/media:

1. WhatsApp message/file arrives in WAHA.
2. WAHA forwards webhook event to `/webhook/whatsapp`.
3. Router hands message to the skills/message handler flow.
4. `DocumentSkill` handles media/document commands and stores raw file to configured storage path.
5. Document pipeline (`process_document()` path) performs text extraction, classification, fact extraction, and summary generation.
6. Metadata/results are persisted in Postgres and document list/query endpoints can return the stored item.

## Database and migration flow

- SQL migrations are in `migrations/*.sql`.
- `scripts/apply_migrations.sh` applies pending files in lexical order.
- Applied migrations are tracked in table `schema_migrations`.

Manual DB checks:

```bash
docker compose exec -T db psql -U fortress -d fortress -c '\dt'
docker compose exec -T db psql -U fortress -d fortress -c 'SELECT * FROM schema_migrations ORDER BY applied_at DESC LIMIT 5;'
```

## Status / observability basics

Primary checks:

```bash
curl -s http://localhost:8000/health
bash scripts/deploy.sh status
```

## Common debugging flows

When something breaks, run these first:

```bash
# app logs
docker compose logs -f fortress

# WAHA logs
docker compose logs -f waha

# container status
docker compose ps

# health endpoint
curl -s http://localhost:8000/health

# DB shell/checks
docker compose exec -T db psql -U fortress -d fortress
# inside psql: \dt
```

## Current major capabilities

Implemented and registered skills currently include:

- Deploy (admin-only)
- System/help
- Tasks
- Documents/media intake + list
- Bug reporting/list
- Chat greetings
- Recurring reminders
- Morning summary/report
- Memory list

## Current limitations (as of April 3, 2026)

- WAHA is optional profile-based and requires QR/session maintenance.
- Ollama service is still in compose and health checks, but Bedrock is the primary LLM path in current operations.
- Deploy automation assumes a Mac Mini-style host setup and local listener service.
- No documented zero-downtime rollout or automatic rollback flow in current scripts.

## Running tests

From `fortress/`:

```bash
python -m pytest tests/ -q
python -m pytest tests/ -v
python -m pytest tests/test_deploy_skill.py -q
```

## Verify which version is running

1. Check git commit on host:

```bash
git rev-parse --short HEAD
```

2. Check app health version:

```bash
curl -s http://localhost:8000/health
# includes: "version": "2.0.0"
```

3. Check deploy status summary:

```bash
bash scripts/deploy.sh status
```

If WhatsApp-triggered deploy/status behavior looks inconsistent, verify host commit, run `git pull origin main`, run `bash scripts/deploy.sh status` (or `deploy_all`) directly on the Mac Mini, then re-check `/health` and WAHA status.
