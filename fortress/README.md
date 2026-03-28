# 🏰 Fortress 2.0

**Family assistant bot over WhatsApp** — task management, document storage, recurring reminders, memory, bug tracking, and morning briefings. Built for a Hebrew-speaking family, powered by AWS Bedrock LLMs.

## Architecture

```
WhatsApp ←→ WAHA ←→ FastAPI (Fortress) ←→ PostgreSQL
                         ↕
                    AWS Bedrock (LLM)
                         ↕
                    APScheduler (cron)
```

**Request flow:**
1. WAHA receives WhatsApp message → forwards to `/webhook/whatsapp`
2. `message_handler` identifies the sender via `auth` service
3. `command_parser` matches the message against registered skill regex patterns
4. Matched skill executes the action (deterministic or LLM-assisted)
5. `response_formatter` formats the reply → `whatsapp_client` sends it back

**Routers:** `health`, `whatsapp`, `scheduler`, `dashboard`

**Key services:** `auth`, `audit`, `bedrock_client`, `llm_client`, `conversation_state`, `documents`, `memory_service`, `memory_nudge`, `message_handler`, `pii_guard`, `recurring`, `scheduler`, `tasks`, `text_extractor`, `whatsapp_client`

## Active Skills

Skills registered in `src/skills/__init__.py`:

| Skill | Name | Commands | Notes |
|-------|------|----------|-------|
| DeploySkill | `deploy` | `פורטרס תתחדש`, `פורטרס הפעל מחדש`, `פורטרס סטטוס` | Registered twice (first for priority, second normally). Parent-only, rate-limited. |
| SystemSkill | `system` | `עזרה` / `help` / `פקודות` | Help menu |
| TaskSkill | `task` | `משימה חדשה:`, `מחק משימה`, `מחק הכל`, `סיים/בוצע`, `עדכן`, `משימות` / `tasks` | Full CRUD. Supports index and title-based operations. |
| DocumentSkill | `document` | `מסמכים` / `documents` | List documents. Also registered as `media` (dual registration for WhatsApp media handling). |
| BugSkill | `bug` | `באג: <desc>` / `bug: <desc>`, `באגים` / `bugs` | Report and list bugs |
| ChatSkill | `chat` | `שלום`, `היי`, `hello`, `בוקר טוב`, `ערב טוב`, `לילה טוב` | Deterministic greetings |
| RecurringSkill | `recurring` | `תזכורת חדשה:`, `תזכורות` / `חוזרות` / `recurring`, `מחק/בטל תזכורת` | Daily/weekly/monthly/yearly patterns |
| MorningSkill | `morning` | `בוקר` / `morning` / `סיכום בוקר`, `סטטוס` / `status`, `דוח` / `report` / `סיכום` | Daily briefing with tasks + recurring summary |
| MemorySkill | `memory` | `זכרונות` / `memories` | List stored memories |

## Disabled / Unregistered Skills

All skills with code files are now registered. No disabled skills.

## Database Schema

8 migrations in `migrations/`:

| Migration | Tables / Changes |
|-----------|-----------------|
| 001 | `family_members`, `permissions`, `documents`, `transactions`, `audit_log`, `conversations` |
| 002 | `tasks`, `recurring_patterns` |
| 003 | System account insert (`00000000-...`) |
| 004 | `memories`, `memory_exclusions` (with default exclusion keywords) |
| 005 | Cleanup corrupt Ollama-era data (soft-delete archived tasks) |
| 006 | `bug_reports` |
| 007 | `conversation_state` |
| 008 | `is_admin` flag on `family_members` |

**Total tables:** `family_members`, `permissions`, `documents`, `transactions`, `audit_log`, `conversations`, `tasks`, `recurring_patterns`, `memories`, `memory_exclusions`, `bug_reports`, `conversation_state` (12 tables)

## Docker Services

Defined in `docker-compose.yml`:

| Service | Image | Port | Notes |
|---------|-------|------|-------|
| `fortress-db` | `postgres:16-alpine` | 5432 (localhost only) | Persistent volume, healthcheck |
| `fortress-app` | Built from `Dockerfile` | 8000 | Python 3.12-slim, depends on db |
| `fortress-ollama` | `ollama/ollama:latest` | 11434 (localhost only) | 6GB memory reservation |
| `fortress-waha` | `devlikeapro/waha:arm` | 3000 | Profile `waha` — must be started explicitly with `--profile waha` |

## Tech Stack

From `requirements.txt`:

- **Runtime:** Python 3.12, FastAPI 0.115, Uvicorn 0.30, Pydantic 2.9
- **Database:** SQLAlchemy 2.0, psycopg2-binary 2.9 (PostgreSQL)
- **LLM:** AWS Bedrock via OpenAI-compatible API (`openai>=1.30`)
- **Scheduling:** APScheduler 3.10
- **Document processing:** pdfplumber 0.11, python-docx 1.1, Pillow 11.0
- **HTTP client:** httpx 0.27
- **Config:** python-dotenv 1.0

## Quick Start

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env — set DB_PASSWORD, ADMIN_PHONE, WAHA_API_KEY, Bedrock keys

# 2. Start core services
docker compose up -d

# 3. Apply migrations
bash scripts/apply_migrations.sh

# 4. Seed family members
cp scripts/seed_family.sh.template scripts/seed_family.sh
# Edit with real phone numbers, then run:
bash scripts/seed_family.sh

# 5. Start WAHA (WhatsApp bridge) — separate profile
docker compose --profile waha up -d

# 6. Dashboard
open http://localhost:8000/dashboard
```

## Personality

Fortress speaks Hebrew, short and warm — WhatsApp style, not email style. Personality is defined in `config/SOUL.md` and loaded at runtime. Key traits:
- Addresses family members by first name
- Uses emoji sparingly
- Never invents information it doesn't have
- Never stores passwords, PINs, credit cards, or ID numbers
- Keeps messages short and actionable

7 formatter functions in `src/prompts/personality.py`: greetings, task creation, task list, document list, recurring list, bug list.

## Known Limitations

- **Ollama is in docker-compose but Bedrock is the active LLM** — the codebase has migrated to Bedrock; Ollama container is still defined but may not be actively used.

## Test Coverage

```
572 tests collected
572 passed, 0 failed
48 test files
```

Test files cover: auth, base_skill, bug_skill, chat_skill, command_parser, conversation_state, dashboard, deploy_listener, deploy_skill, document_skill, e2e (confirmations, conversations, permissions, personality, regression, skills, state), executor, health, llm_client, memory_nudge, memory_service, memory_skill, message_handler, morning_skill, mvp, mvp_pbt, openrouter_client, personality, phone, pii_guard, pii_integration, recurring_skill, recurring, registry, response_formatter, scheduler, skill_docs, soul_loading, system_prompts, system_skill, task_skill, tasks, text_extractor, time_context, whatsapp_client, whatsapp_router.

## Development Guide

### Adding a New Skill

1. Create `src/skills/my_skill.py` extending `BaseSkill`
2. Implement `name`, `commands` (regex patterns → action names), and `execute()`
3. Create `src/skills/SKILL_my_skill.md` documentation
4. Register in `src/skills/__init__.py`: `registry.register(MySkill())`
5. Add tests in `tests/test_my_skill.py`

### Deploying

```bash
# From Mac Mini host:
bash scripts/deploy.sh

# Or trigger remotely via WhatsApp (parent only):
# Send: פורטרס תתחדש
```

A deploy listener (`scripts/deploy_listener.py`) runs on the host and accepts authenticated deploy requests from the container.

### Running Tests

```bash
cd fortress
python -m pytest tests/ -q          # quick summary
python -m pytest tests/ -v          # verbose
python -m pytest tests/test_task_skill.py  # single file
```
