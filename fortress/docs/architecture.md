# Fortress 2.0 Architecture

## Overview

Fortress 2.0 is built on FastAPI + PostgreSQL 16 + WAHA + Docker Compose. It runs locally on a Mac Mini M4 as three containers: the Python application, the database, and the WhatsApp bridge.

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
│  ├── message_handler │
│  ├── whatsapp_client │
│  ├── auth.py         │
│  ├── tasks.py        │
│  ├── recurring.py    │
│  ├── audit.py        │
│  └── documents.py    │
└────────┬────────────┘
         │ SQLAlchemy
         ▼
┌─────────────────────┐
│  PostgreSQL 16       │
│  (8 tables)          │
└─────────────────────┘
```

## Message Flow

1. Family member sends WhatsApp message to the Fortress phone number
2. WAHA receives the message via WhatsApp Web and POSTs webhook to FastAPI
3. WhatsApp router parses the WAHA payload, extracts phone/text/media
4. Message handler identifies the sender via auth service (phone lookup)
5. Based on content: lists tasks, creates tasks, stores documents, or acknowledges
6. Response is sent back through WAHA API → WhatsApp → user's phone
7. Conversation is saved to the conversations table

## Service Layer

**Message Handler** (`src/services/message_handler.py`) — Core message processing logic. Receives parsed WhatsApp messages, identifies the sender, routes to appropriate handler based on keywords (Hebrew + English), and returns response text. Saves all conversations.

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
| `conversations` | WhatsApp message history | UUID |
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
- **Hebrew-first commands** — Primary users are Hebrew speakers; English aliases provided as fallback
