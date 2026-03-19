# Fortress 2.0 Architecture

## Overview

Fortress 2.0 is built on FastAPI + PostgreSQL 16 + WAHA + Ollama + Docker Compose. It runs locally on a Mac Mini M4 as four containers: the Python application, the database, the WhatsApp bridge, and the local LLM.

```
WhatsApp (phone)
        │
        ▼
┌─────────────────────┐
│  WAHA (port 3000)    │
│  WhatsApp Web bridge │
└────────┬────────────┘
         │ webhook POST
         ▼
┌─────────────────────┐
│  FastAPI (port 8000) │
│  ├── /health         │
│  └── /webhook/wa     │
│                      │
│  Router:             │
│  └── whatsapp.py     │
│       ├── parse msg  │
│       ├── download   │
│       │   media      │
│       ├── handle msg │
│       └── send reply │
│                      │
│  Services:           │
│  ├── message_handler │  ← thin auth layer
│  ├── model_router    │  ← intent dispatch
│  ├── intent_detector │  ← keyword + LLM
│  ├── llm_client      │  ← async Ollama client
│  ├── whatsapp_client │
│  ├── auth.py         │
│  ├── tasks.py        │
│  ├── recurring.py    │
│  ├── audit.py        │
│  └── documents.py    │
│                      │
│  Prompts:            │
│  └── system_prompts  │  ← LLM prompt templates
└────────┬────────────┘
         │ SQLAlchemy      httpx async
         ▼                     ▼
┌──────────────────┐  ┌──────────────────┐
│  PostgreSQL 16   │  │  Ollama          │
│  (8 tables)      │  │  (port 11434)    │
└──────────────────┘  │  llama3.1:8b     │
                      └──────────────────┘
```

## Message Flow

1. Family member sends WhatsApp message to the Fortress phone number
2. WAHA receives the message via WhatsApp Web and POSTs webhook to FastAPI
3. WhatsApp router parses the WAHA payload, extracts phone/text/media
4. Message handler identifies the sender via auth service (phone lookup)
5. If unknown/inactive → Hebrew rejection message
6. If active → delegates to model router
7. Model router detects intent via intent detector (keyword match → LLM fallback)
8. Model router checks permissions for the detected intent
9. Model router dispatches to the appropriate handler
10. Handler uses LLM client to generate natural Hebrew responses via Ollama
11. Conversation is saved with detected intent
12. Response is sent back through WAHA API → WhatsApp → user's phone

## Service Layer

**Message Handler** (`src/services/message_handler.py`) — Thin auth layer. Identifies the sender by phone, rejects unknown/inactive members, and delegates all message processing to the model router. Contains no keyword matching or intent logic.

**Model Router** (`src/services/model_router.py`) — Intent-based message dispatch. Receives a detected intent, checks permissions, routes to the appropriate handler (list_tasks, create_task, complete_task, greeting, upload_document, list_documents, ask_question, unknown), saves conversation records, and returns Hebrew responses.

**Intent Detector** (`src/services/intent_detector.py`) — Classifies incoming messages into intent categories. Uses keyword matching (Hebrew + English) as the fast path, with LLM fallback via Ollama for unrecognized messages. Returns one of 8 intent strings.

**LLM Client** (`src/services/llm_client.py`) — Async HTTP client for Ollama REST API. Sends generation requests to `/api/generate` with 30-second timeout. Returns Hebrew fallback messages on any error. Also provides `is_available()` for health checks.

**System Prompts** (`src/prompts/system_prompts.py`) — Predefined prompt templates that guide LLM behavior: FORTRESS_BASE (system identity), INTENT_CLASSIFIER (message classification), TASK_EXTRACTOR (structured task extraction), TASK_RESPONDER (task list formatting).

**WhatsApp Client** (`src/services/whatsapp_client.py`) — Sends messages back through WAHA API. Supports text messages and replies. Handles errors gracefully.

**Auth Service** (`src/services/auth.py`) — Phone-based identity lookup and role-based permission checks. Family members are identified by phone number (from WhatsApp). Permissions map roles (parent, child, grandparent) to read/write access on resource types (finance, documents, tasks).

**Audit Service** (`src/services/audit.py`) — Append-only logging of all significant system actions. Each entry records the actor, action, target resource, and structured details as JSONB.

**Document Service** (`src/services/documents.py`) — Document ingestion and metadata storage. Currently a minimal implementation; will be expanded with AI/OCR processing in future phases.

**Task Service** (`src/services/tasks.py`) — Household task management: create, list, complete, and archive tasks. Tasks can be manual, linked to source documents, or generated from recurring patterns. All mutations are audit-logged.

**Recurring Service** (`src/services/recurring.py`) — Manages recurring task patterns (daily, weekly, monthly, yearly). Detects due patterns and auto-generates tasks, advancing the next due date after each generation.

## Utilities

**Phone** (`src/utils/phone.py`) — Phone number normalization (strip @c.us, non-digits, +) and Israeli phone validation.

**Media** (`src/utils/media.py`) — Downloads media from WAHA API and saves to organized storage path (year/month/uuid_filename).

## Database Schema

| Table | Purpose | Primary Key |
|-------|---------|-------------|
| `family_members` | Identity and roles | UUID |
| `permissions` | Role-based access control | UUID |
| `documents` | Document metadata | UUID |
| `transactions` | Financial records from documents | UUID |
| `audit_log` | Action history | BIGSERIAL |
| `conversations` | WhatsApp message history (with detected intent) | UUID |
| `tasks` | Household task tracking (manual, document-linked, recurring) | UUID |
| `recurring_patterns` | Recurring task schedules (daily/weekly/monthly/yearly) | UUID |

Migrations are raw SQL files applied by `scripts/apply_migrations.sh`, tracked in a `schema_migrations` table.

## Key Design Decisions

- **WAHA over WhatsApp Cloud API** — Self-hosted, no Meta business verification, full control over data
- **FastAPI over Flask/Django** — async-ready, auto-generated OpenAPI docs, native Pydantic integration
- **SQLAlchemy 2.0 mapped_column style** — typed ORM with modern Python syntax
- **Raw SQL migrations** — simple, auditable, no ORM migration tool dependency
- **Phone-based auth** — WhatsApp messages arrive with phone numbers, making phone the natural identity key
- **Docker Compose** — single-command deployment, PostgreSQL health checks, named volumes for persistence
- **Always return 200 to WAHA** — WAHA retries on non-200, so errors are logged but never cause webhook failures
- **Hebrew-first responses** — Primary users are Hebrew speakers; all LLM responses are in Hebrew
- **Ollama for local LLM** — No external API dependencies, runs on Mac Mini M4 with 6GB memory reservation
- **Keyword matching + LLM fallback** — Fast path for known commands, LLM for natural language understanding
- **Intent-based routing** — Clean separation of intent detection, permission checking, and handler dispatch
- **Graceful degradation** — If Ollama is down, keyword-matched intents still work; LLM failures return Hebrew fallback messages
