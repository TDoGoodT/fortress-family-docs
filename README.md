# Fortress 2.0 🏰

**Sovereign, local-first family intelligence system.**

Fortress manages your household documents, finances, tasks, and
knowledge through WhatsApp. It runs entirely on your own hardware —
your data never leaves your home except for AI processing via
encrypted API calls.

## Architecture

```
WhatsApp → WAHA → FastAPI → LangGraph Workflow
                    ├── Unified LLM (classify + respond)
                    ├── AWS Bedrock (Hebrew AI)
                    ├── Ollama (last-resort fallback)
                    ├── PostgreSQL (data + memory)
                    └── NAS (document storage)
```

**4 Docker containers** on a Mac Mini M4:
- `fortress-app` — FastAPI backend + LangGraph workflow engine
- `fortress-db` — PostgreSQL 16 (10 tables)
- `fortress-waha` — WhatsApp Web bridge
- `fortress-ollama` — Local LLM (last-resort generation fallback)

## Features

- 📱 **WhatsApp Interface** — send messages, photos, documents
- 🧠 **AI-Powered** — Bedrock Claude for Hebrew, unified classify+respond for routing
- ✅ **Task Management** — create, list, complete tasks via chat
- 🔄 **Recurring Tasks** — auto-generated from patterns
- 📄 **Document Storage** — photos and files saved to NAS
- 💰 **Financial Tracking** — transactions linked to documents
- 🧠 **Memory System** — learns preferences, goals, facts across sessions
- 🔒 **Family Permissions** — parents see finances, kids don't
- 📊 **Audit Trail** — every action logged

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | Python 3.12 + FastAPI |
| AI Orchestration | LangGraph |
| Primary AI | AWS Bedrock (Claude 3.5) |
| Local AI | Ollama (Llama 3.1 8B) — fallback only |
| Database | PostgreSQL 16 |
| WhatsApp | WAHA (self-hosted) |
| Deployment | Docker Compose |
| Hardware | Mac Mini M4, 24GB RAM |

## Quick Start

```bash
git clone https://github.com/Segway16/fortress-family.git
cd fortress-family/fortress
cp .env.example .env           # edit with your values
cp scripts/seed_family.sh.template scripts/seed_family.sh  # edit with phone numbers
./scripts/setup_mac_mini.sh    # one-command setup
```

See [docs/setup.md](fortress/docs/setup.md) for detailed instructions.

## Project Structure

```
fortress/
├── src/           # Application code
├── migrations/    # Database schema (4 migration files, 10 tables)
├── scripts/       # Deployment & setup scripts
├── tests/         # Test suite (150 tests)
├── docs/          # Architecture & setup documentation
└── docker-compose.yml
```

## Database (10 tables)

| Table | Purpose |
|-------|---------|
| family_members | Phone-based identity + roles |
| permissions | Role-based access control |
| documents | Uploaded files metadata |
| transactions | Financial records |
| tasks | Household task management |
| recurring_patterns | Auto-generated recurring tasks |
| memories | AI conversational memory |
| memory_exclusions | PII protection rules |
| audit_log | Action history |
| conversations | WhatsApp message history |

## Status

**Phase 4B.6 Complete — Bedrock + LangGraph + Memory + Unified Classify+Respond**

- ✅ 150 passing tests
- ✅ 10 database tables
- ✅ 4 Docker services
- ✅ WhatsApp integration
- ✅ AI-powered intent routing
- ✅ Hebrew responses via Bedrock
- ✅ Memory system with PII exclusions
- ✅ Permission-based access control
- ✅ Ollama removed from critical path — unified classify+respond

## License

Private — Family use only.
