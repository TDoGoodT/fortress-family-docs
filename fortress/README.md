# Fortress 2.0

Fortress is a sovereign, local-first family intelligence system. It manages household documents, finances, and tasks via WhatsApp, running entirely on a Mac Mini M4 via Docker Compose.

## Quick Start

```bash
# Copy and configure environment
cp .env.example .env
# Edit .env with your DB_PASSWORD

# Start everything (PostgreSQL + FastAPI + WAHA + Ollama)
docker compose up -d

# Apply database migrations
./scripts/apply_migrations.sh

# Pull the Ollama model (~4.7GB on first run)
./scripts/setup_ollama.sh
```

The API will be available at `http://localhost:8000`. Check health at `GET /health`.

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
│   ├── config.py            # Environment configuration
│   ├── database.py          # SQLAlchemy engine and session
│   ├── models/
│   │   └── schema.py        # ORM models (8 tables)
│   ├── prompts/
│   │   ├── __init__.py      # Prompt exports
│   │   └── system_prompts.py # LLM prompt templates
│   ├── routers/
│   │   ├── health.py        # GET /health (DB + Ollama status)
│   │   └── whatsapp.py      # POST /webhook/whatsapp (WAHA handler)
│   ├── services/
│   │   ├── auth.py          # Phone-based auth + permissions
│   │   ├── audit.py         # Audit logging
│   │   ├── documents.py     # Document processing
│   │   ├── intent_detector.py # Intent classification (keyword + LLM)
│   │   ├── llm_client.py    # Async Ollama REST API client
│   │   ├── model_router.py  # Intent-based message routing
│   │   ├── tasks.py         # Task management
│   │   ├── recurring.py     # Recurring task patterns
│   │   ├── message_handler.py # Thin auth layer → model router
│   │   └── whatsapp_client.py # WAHA API client (send messages)
│   └── utils/
│       ├── ids.py           # UUID generation
│       ├── phone.py         # Phone number normalization
│       └── media.py         # Media download and storage
├── migrations/              # SQL migration files
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
| GET | `/health` | Health check with DB status |
| POST | `/webhook/whatsapp` | WAHA webhook handler |

## Current Status

Phase 4A — AI-powered intent routing. The current implementation includes:

- Four-container Docker Compose: PostgreSQL 16 + FastAPI + WAHA (WhatsApp bridge) + Ollama (local LLM)
- PostgreSQL schema with 8 tables
- Phone-based auth with role-based permissions
- AI-powered intent detection with keyword matching and LLM fallback
- Model router dispatching intents to handlers with LLM-generated Hebrew responses
- Ollama integration (llama3.1:8b) for natural language understanding
- WhatsApp message handling via intent-based routing
- Task management with recurring patterns (daily/weekly/monthly/yearly)
- Natural language task creation and completion
- Media download and storage from WhatsApp
- Audit logging for all actions
- Conversation history tracking with detected intents
- System prompts tuned for Hebrew WhatsApp interactions

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
