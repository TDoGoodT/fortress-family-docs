# Fortress 2.0

Fortress is a sovereign, local-first family intelligence system. It manages household documents, finances, and tasks via WhatsApp, running entirely on a Mac Mini M4 via Docker Compose.

## Architecture

Fortress uses a hybrid AI architecture:

- **AWS Bedrock** (Claude 3.5 Haiku/Sonnet) — All Hebrew text generation. Haiku handles simple intents (greetings, task confirmations), Sonnet handles complex questions.
- **Ollama** (llama3.1:8b) — Demoted to English-only intent classification. Fast, local, no cloud dependency for routing decisions.
- **LangGraph StateGraph** — Replaces the old model router with a structured 7-node workflow pipeline: intent → permission → memory load → action → response → memory save → conversation save.
- **Three-tier memory** — Conversational context persisted across sessions with tiered expiration (short 7d, medium 90d, long 365d, permanent).

## Quick Start

```bash
# Copy and configure environment
cp .env.example .env
# Edit .env with your DB_PASSWORD, AWS settings, and phone numbers

# Start everything (PostgreSQL + FastAPI + WAHA + Ollama)
docker compose up -d

# Apply database migrations
./scripts/apply_migrations.sh

# Pull the Ollama model (~4.7GB on first run)
./scripts/setup_ollama.sh
```

The API will be available at `http://localhost:8000`. Check health at `GET /health`.

### AWS Bedrock Setup

Fortress requires AWS credentials with Bedrock access. See [docs/setup.md](docs/setup.md) for full IAM and credential configuration.

### WhatsApp Setup

1. Open the WAHA dashboard at `http://localhost:3000`
2. Start a new session (or use the default session)
3. Scan the QR code with the Fortress phone
4. The system is now ready to receive WhatsApp messages

## Project Structure

```
fortress/
├── src/
│   ├── main.py              # FastAPI application entry point
│   ├── config.py            # Environment configuration (AWS, phone, DB)
│   ├── database.py          # SQLAlchemy engine and session
│   ├── models/
│   │   └── schema.py        # ORM models (10 tables incl. memories)
│   ├── prompts/
│   │   ├── __init__.py      # Prompt exports
│   │   └── system_prompts.py # LLM prompt templates (Ollama + Bedrock)
│   ├── routers/
│   │   ├── health.py        # GET /health (DB + Ollama + Bedrock status)
│   │   └── whatsapp.py      # POST /webhook/whatsapp (WAHA handler)
│   ├── services/
│   │   ├── auth.py          # Phone-based auth + permissions
│   │   ├── audit.py         # Audit logging
│   │   ├── bedrock_client.py # AWS Bedrock Claude client (Hebrew generation)
│   │   ├── documents.py     # Document processing
│   │   ├── intent_detector.py # Intent classification (keyword + Ollama)
│   │   ├── llm_client.py    # Async Ollama REST API client (intent only)
│   │   ├── memory_service.py # Three-tier memory with exclusion filtering
│   │   ├── model_router.py  # Legacy intent-based routing (kept for compat)
│   │   ├── tasks.py         # Task management
│   │   ├── recurring.py     # Recurring task patterns
│   │   ├── message_handler.py # Thin auth layer → workflow engine
│   │   ├── whatsapp_client.py # WAHA API client (send messages)
│   │   └── workflow_engine.py # LangGraph StateGraph workflow pipeline
│   └── utils/
│       ├── ids.py           # UUID generation
│       ├── phone.py         # Phone number normalization
│       └── media.py         # Media download and storage
├── migrations/              # SQL migration files (001–004)
├── scripts/                 # Operational scripts
├── tests/                   # pytest tests
├── docs/                    # Architecture documentation
├── docker-compose.yml       # PostgreSQL + FastAPI + WAHA + Ollama
├── Dockerfile
├── requirements.txt
└── .env.example
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check (DB + Ollama + Bedrock status) |
| POST | `/webhook/whatsapp` | WAHA webhook handler |

## Current Status

Phase 4B — Hybrid AI with LangGraph workflow and memory. The current implementation includes:

- Four-container Docker Compose: PostgreSQL 16 + FastAPI + WAHA + Ollama
- Hybrid AI: AWS Bedrock (Claude 3.5 Haiku/Sonnet) for Hebrew, Ollama for intent classification
- LangGraph StateGraph workflow replacing the model router
- Three-tier memory system (short/medium/long/permanent) with exclusion filtering
- PostgreSQL schema with 10 tables (including memories and memory_exclusions)
- Phone-based auth with role-based permissions
- AI-powered intent detection with keyword matching and Ollama LLM fallback
- Task management with recurring patterns (daily/weekly/monthly/yearly)
- Natural language task creation and completion via Bedrock
- Media download and storage from WhatsApp
- Audit logging for all actions
- Conversation history tracking with detected intents
- Echo prevention via WAHA `fromMe` field
- Health endpoint monitoring DB, Ollama, and Bedrock connectivity

## Development

### Running Tests

```bash
pytest fortress/tests/ -v
```

All 91 tests should pass. Tests use mocked dependencies — no Docker or database required.

### Adding a New Migration

1. Create `migrations/NNN_description.sql` (next sequential number)
2. Write idempotent SQL (`CREATE TABLE IF NOT EXISTS`, etc.)
3. Run `./scripts/apply_migrations.sh` to apply

### Adding a New Service

1. Create `src/services/your_service.py`
2. Add corresponding test in `tests/test_your_service.py`
3. Wire it into the workflow engine or router as needed
4. Update `src/services/__init__.py` if exposing publicly

### Current Phase

Phase 4B Complete — Bedrock + LangGraph + Memory System. 91 passing tests, 10 database tables, 4 Docker services.

## Deployment

For full deployment instructions on a Mac Mini M4, see [docs/setup.md](docs/setup.md).

### First-Time Setup

```bash
cp scripts/seed_family.sh.template scripts/seed_family.sh
# Edit seed_family.sh with real phone numbers
./scripts/setup_mac_mini.sh
```

The setup script checks Docker, starts services, applies migrations, seeds
family members, and verifies health — all in one command.
