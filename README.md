# 🏰 Fortress

**ג'רוויס למשפחה — עוזר משפחתי חכם דרך WhatsApp**

Fortress is a sovereign, local-first family intelligence system that manages household tasks, documents, finances, and knowledge through WhatsApp. It runs entirely on your own hardware — your data never leaves your home except for encrypted AI API calls. מערכת ניהול משפחתית חכמה שרצה על החומרה שלכם, עם ממשק וואטסאפ טבעי בעברית.

## Architecture

**Skills Engine** — 90% deterministic (regex → DB → template), 10% LLM fallback (free chat only). Zero LLM calls for CRUD operations.

```
WhatsApp → WAHA → FastAPI → Skills Engine
                    ├── CommandParser (regex → Command)
                    ├── Executor → Skill.execute → verify
                    ├── ResponseFormatter → personality template
                    └── ChatSkill (LLM fallback for free chat)
```

**4 Docker containers** on a Mac Mini M4:

| Container | Role |
|-----------|------|
| `fortress-app` | FastAPI + Skills Engine |
| `fortress-db` | PostgreSQL 16 (12 tables) |
| `fortress-waha` | WhatsApp Web bridge (WAHA) |
| `fortress-ollama` | Local LLM fallback (Ollama) |

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.12 |
| Backend | FastAPI |
| Database | PostgreSQL 16 |
| WhatsApp | WAHA (self-hosted bridge) |
| Local LLM | Ollama (last-resort fallback) |
| Primary AI | AWS Bedrock (Claude 3.5 Haiku + Sonnet) |
| Cheap AI | OpenRouter (free/cheap models) |
| Deployment | Docker Compose |
| Hardware | Mac Mini M4, 24 GB RAM |

## Quick Start

```bash
# Clone
git clone https://github.com/Segway16/fortress-family.git
cd fortress-family/fortress

# Environment
cp .env.example .env           # edit with your API keys and passwords
cp scripts/seed_family.sh.template scripts/seed_family.sh  # edit with phone numbers

# Launch
docker compose up -d           # start all 4 containers
./scripts/apply_migrations.sh  # create database tables
./scripts/seed_family.sh       # seed family members
```

Dashboard: [http://localhost:8000/dashboard](http://localhost:8000/dashboard)

See [docs/setup.md](fortress/docs/setup.md) for detailed instructions.

## Available Skills

| Skill | Commands | Description |
|-------|----------|-------------|
| Tasks | משימה חדשה:, משימות, מחק, סיים | ניהול משימות |
| Recurring | תזכורת חדשה:, תזכורות | תזכורות חוזרות |
| Documents | שלח תמונה, מסמכים | אחסון מסמכים |
| Bugs | באג:, באגים | מעקב באגים |
| Chat | שלום, שיחה חופשית | שיחה עם AI |
| Memory | זכרונות | זיכרון המערכת |
| Morning | בוקר, סיכום | סיכום יומי |
| System | עזרה, ביטול, אישור | פקודות מערכת |

## Database (12 Tables)

| Table | Purpose |
|-------|---------|
| `family_members` | Phone-based identity and roles |
| `permissions` | Role-based access control (parent/child/grandparent) |
| `documents` | Uploaded file metadata |
| `transactions` | Financial records linked to documents |
| `audit_log` | Append-only action history |
| `conversations` | WhatsApp message history with detected intent |
| `tasks` | Household task management |
| `recurring_patterns` | Recurring task schedules (daily/weekly/monthly/yearly) |
| `memories` | AI conversational memory with tiered expiration |
| `memory_exclusions` | PII protection patterns (passwords, codes, credit cards) |
| `bug_reports` | Bug tracking (parents only) |
| `conversation_state` | Per-user conversation context and pending confirmations |

## How to Add a Skill

1. **Create** `src/skills/my_skill.py` extending `BaseSkill`
2. **Define** regex command patterns in the `commands` property
3. **Implement** `execute(db, member, command) → Result` and `verify(db, result) → bool`
4. **Register** in `src/skills/__init__.py` (add to the registry)
5. **Add** personality templates in `src/prompts/personality.py`
6. **Add** tests in `tests/test_my_skill.py`

```python
class MySkill(BaseSkill):
    @property
    def name(self) -> str:
        return "my_skill"

    @property
    def commands(self) -> list[tuple[re.Pattern, str]]:
        return [
            (re.compile(r"^פקודה:(.+)$"), "my_action"),
        ]

    def execute(self, db, member, command) -> Result:
        # Your logic here
        return Result(success=True, message="✅ Done")

    def verify(self, db, result) -> bool:
        return result.success
```

## Roadmap & Version History

| Phase | Status | Description | Tests |
|-------|--------|-------------|-------|
| 1.0 — Foundation | ✅ Complete | 6 tables, FastAPI, Docker, auth, audit | 10 |
| 2.0 — Tasks | ✅ Complete | Tasks + recurring patterns | 28 |
| 3.0 — WhatsApp | ✅ Complete | WAHA integration, message handler | 52 |
| 3.5 — Deploy | ✅ Complete | Mac Mini deployment, permissions, seed | 52 |
| 4A — Local AI | ✅ Complete | Ollama, intent detection, model router | 89 |
| 4A — Hotfix | ✅ Complete | WAHA config, logging fixes | 89 |
| 4B — Bedrock + Memory | ✅ Complete | AWS Bedrock, memory system | 91 |
| 4B.5 — Model Routing | ✅ Complete | OpenRouter, 3-tier routing, fallbacks | 130 |
| 4B.6 — Ollama Cleanup | ✅ Complete | Remove Ollama from critical path | 150 |
| 4B.7 — Pipeline Resilience | ✅ Complete | JSON healing, response protection, logging | 175 |
| STABLE-2 — Personality | ✅ Complete | Hebrew personality, templates, consistent tone | 201 |
| STABLE-3 — Core Hardening | ✅ Complete | Delete tasks, ownership, dedup, prompt cleanup | 228 |
| STABLE-4 — Document Flow | ✅ Complete | Document storage, metadata, personality templates | 254 |
| STABLE-5 — Recurring Scheduler | ✅ Complete | Recurring scheduler, WhatsApp notifications | 254+ |
| STABLE-6 — Early Production | ✅ Complete | Bug tracker, memory fix, session resilience, dashboard | 318 |
| SPRINT-1 — State + Verification | ✅ Complete | Conversation state, time injection, confirmations | 365 |
| SPRINT-2 — Intent + UX | ✅ Complete | Priority classification, multi-intent, bulk ops | 420+ |
| R1 — Skills Engine Core | ✅ Complete | BaseSkill ABC, Registry, CommandParser, Executor, ResponseFormatter | 478 |
| R2 — Core Skills Migration | ✅ Complete | Task, Recurring, Document, Bug, Chat, Memory, Morning skills | 627 |
| R3 — Wire + Test + Deploy | ✅ Complete | E2E tests, permissions, confirmations, regression, merge to main | 689 |
| R4 — Trim + Document + Organize | ✅ Complete | Delete old pipeline, clean deps, rewrite docs | 428 |
| S1 — PII Guard + Intent Logging | ✅ Complete | Regex PII stripping, restore, intent audit logging | 450 |
| S2 — SOUL.md + SKILL.md + Nudges | ✅ Complete | Editable personality file, skill docs, memory nudges | 479 |
| S3 — OCR + Document Intelligence | ✅ Complete | PDF/DOCX/image text extraction, raw_text storage | 494 |
| SMART-1 — OCR | 📋 Planned | Document intelligence, invoice scanning | — |
| SMART-2 — RAG | 📋 Planned | pgvector, document Q&A, contract analysis | — |
| SMART-3 — NAS + Backup | 📋 Planned | NAS storage, Backblaze B2 backup | — |
| SMART-4 — Email | 📋 Planned | IMAP polling, auto-ingest from email | — |
| Hardening | 📋 Planned | Monitoring, auto-restart, rate limiting | — |

Current: **Phase S3** — OCR + Document Intelligence (494 tests)

## Dashboard

Access the admin dashboard at [http://localhost:8000/dashboard](http://localhost:8000/dashboard) for system status, recent conversations, and skill activity.

## License

Private — Family use only.
