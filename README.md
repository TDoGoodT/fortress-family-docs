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
├── migrations/    # Database schema (6 migration files, 11 tables)
├── scripts/       # Deployment & setup scripts
├── tests/         # Test suite (420+ tests)
├── docs/          # Architecture & setup documentation
└── docker-compose.yml
```

## Database (11 tables)

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
| bug_reports | Bug tracking (parents only) |

## Status

**Phase STABLE-6 Complete — Early Production**

- ✅ 420+ passing tests
- ✅ 11 database tables
- ✅ 4 Docker services
- ✅ WhatsApp integration
- ✅ AI-powered intent routing
- ✅ Hebrew responses via Bedrock
- ✅ Memory system with PII exclusions
- ✅ Permission-based access control
- ✅ Ollama removed from critical path — unified classify+respond
- ✅ JSON healing — resilient to imperfect LLM output

## License

Private — Family use only.

## Roadmap & Version History

### Current Version: Phase STABLE-6

| Phase | Status | Description | Tests |
|-------|--------|-------------|-------|
| 1.0 — Foundation | ✅ Complete | 6 tables, FastAPI, Docker, auth, audit | 10 |
| 2.0 — Tasks | ✅ Complete | Tasks + recurring patterns | 28 |
| 3.0 — WhatsApp | ✅ Complete | WAHA integration, message handler | 52 |
| 3.5 — Deploy | ✅ Complete | Mac Mini deployment, permissions, seed | 52 |
| 4A — Local AI | ✅ Complete | Ollama, intent detection, model router | 89 |
| 4A — Hotfix | ✅ Complete | WAHA config, logging fixes | 89 |
| 4B — Bedrock + Memory | ✅ Complete | AWS Bedrock, LangGraph, memory system | 91 |
| 4B.5 — Model Routing | ✅ Complete | OpenRouter, 3-tier routing, fallbacks | 130 |
| 4B.6 — Ollama Cleanup | ✅ Complete | Remove Ollama from critical path, unified LLM | 150 |
| 4B.7 — Pipeline Resilience | ✅ Complete | JSON healing, response protection, logging | 175 |
| STABLE-2 — Agent Personality | ✅ Complete | Centralised Hebrew personality, templates, consistent tone | 201 |
| STABLE-3 — Core Flows Hardening | ✅ Complete | Delete tasks, ownership, dedup, prompt cleanup, migration | 228 |
| STABLE-4 — Document Flow | ✅ Complete | Document storage, metadata, list/upload personality templates | 254 |
| STABLE-5 — Recurring Scheduler | ✅ Complete | Recurring task scheduler, WhatsApp notifications, pattern management | 254+ |
| STABLE-6 — Early Production | ✅ Complete | Bug tracker, memory fix, session resilience, media logging, admin dashboard | 318 |
| SPRINT-1 — State + Time + Verification | ✅ Complete | Conversation state, time injection, action verification, confirmations | 365 |
| SPRINT-2 — Intent + Entity + UX | ✅ Complete | Priority intent classification, multi-intent, clarification, bulk ops, notifications | 420+ |
| R1 — Skills Engine Core | ✅ Complete | BaseSkill ABC, Registry, deterministic Command Parser, Executor, State integration, Response Formatter | 478 |
| 5A — OCR | 📋 Planned | Document intelligence, invoice scanning | — |
| 5C — RAG | 📋 Planned | pgvector, document Q&A, contract analysis | — |
| 6.0 — NAS + Backup | 📋 Planned | NAS storage, Restic → Backblaze B2 | — |
| 7.0 — Email | 📋 Planned | IMAP polling, auto-ingest from email | — |
| 8.0 — Hardening | 📋 Planned | Monitoring, auto-restart, rate limiting | — |
