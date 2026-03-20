# Fortress 2.0 Architecture

## Overview

Fortress 2.0 is built on FastAPI + PostgreSQL 16 + WAHA + Ollama + AWS Bedrock + Docker Compose. It runs locally on a Mac Mini M4 as four containers: the Python application, the database, the WhatsApp bridge, and the local LLM. The application container connects to AWS Bedrock for Hebrew text generation.

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
┌─────────────────────────────────────────────────┐
│  FastAPI (port 8000)                             │
│  ├── /health         (DB + Ollama + Bedrock)     │
│  └── /webhook/wa     (fromMe echo prevention)    │
│                                                  │
│  Router:                                         │
│  └── whatsapp.py                                 │
│       ├── parse msg                              │
│       ├── download media                         │
│       ├── handle msg                             │
│       └── send reply                             │
│                                                  │
│  Workflow Engine (LangGraph StateGraph):          │
│  ├── intent_node       → Ollama (classify)       │
│  ├── permission_node   → Auth service            │
│  ├── memory_load_node  → MemoryService           │
│  ├── action_node       → Bedrock (haiku/sonnet)  │
│  ├── response_node     → pass-through / denial   │
│  ├── memory_save_node  → MemoryService           │
│  └── conversation_save_node → DB                 │
│                                                  │
│  Services:                                       │
│  ├── message_handler   ← thin auth layer         │
│  ├── workflow_engine   ← LangGraph pipeline      │
│  ├── bedrock_client    ← AWS Bedrock Claude      │
│  ├── memory_service    ← three-tier memory       │
│  ├── intent_detector   ← keyword + Ollama        │
│  ├── llm_client        ← async Ollama client     │
│  ├── model_router      ← legacy (kept for compat)│
│  ├── whatsapp_client                             │
│  ├── auth.py                                     │
│  ├── tasks.py                                    │
│  ├── recurring.py                                │
│  ├── audit.py                                    │
│  └── documents.py                                │
│                                                  │
│  Prompts:                                        │
│  └── system_prompts    ← Ollama + Bedrock prompts│
└────────┬──────────┬──────────┬──────────────────┘
         │          │          │
    SQLAlchemy   httpx      boto3
         │          │          │
         ▼          ▼          ▼
┌──────────────┐ ┌────────┐ ┌──────────────────┐
│ PostgreSQL 16│ │ Ollama │ │ AWS Bedrock      │
│ (10 tables)  │ │:11434  │ │ Claude 3.5       │
│              │ │llama3.1│ │ Haiku + Sonnet   │
└──────────────┘ └────────┘ └──────────────────┘
```

## Message Flow (LangGraph Workflow)

```
START
  │
  ▼
┌─────────────┐
│ intent_node │──── Ollama classifies intent (English-only)
└──────┬──────┘
       ▼
┌──────────────────┐
│ permission_node  │──── Auth service checks role-based access
└──────┬───────────┘
       │
       ├── denied ──────────────────────┐
       │                                │
       ▼                                ▼
┌──────────────────┐           ┌───────────────┐
│ memory_load_node │           │ response_node │ (🔒 denial msg)
└──────┬───────────┘           └───────┬───────┘
       ▼                               │
┌─────────────┐                        │
│ action_node │── Bedrock generates    │
│             │   Hebrew response      │
└──────┬──────┘                        │
       ▼                               │
┌───────────────┐◄─────────────────────┘
│ response_node │
└──────┬────────┘
       ▼
┌──────────────────┐
│ memory_save_node │──── Bedrock extracts memories from conversation
└──────┬───────────┘
       ▼
┌────────────────────────┐
│ conversation_save_node │──── Saves to DB with detected intent
└──────┬─────────────────┘
       ▼
      END
```

### Detailed Flow

1. Family member sends WhatsApp message to the Fortress phone number
2. WAHA receives the message via WhatsApp Web and POSTs webhook to FastAPI
3. WhatsApp router checks `fromMe` field — ignores the bot's own outgoing messages
4. WhatsApp router parses the WAHA payload, extracts phone/text/media
5. Message handler identifies the sender via auth service (phone lookup)
6. If unknown/inactive → Hebrew rejection message
7. If active → delegates to workflow engine (`run_workflow`)
8. **intent_node**: Ollama classifies the message intent (keyword match → LLM fallback)
9. **permission_node**: Auth service checks role-based permissions for the intent
10. If denied → skips to response_node with 🔒 denial message
11. **memory_load_node**: MemoryService loads relevant memories for context
12. **action_node**: Bedrock generates Hebrew response (Haiku for simple intents, Sonnet for `ask_question`)
13. **response_node**: Passes through the generated response
14. **memory_save_node**: Bedrock extracts facts from the conversation, MemoryService saves them (with exclusion filtering)
15. **conversation_save_node**: Saves Conversation record to DB with detected intent
16. Response is sent back through WAHA API → WhatsApp → user's phone

## Hybrid AI Architecture

### Model Routing

| Model | Role | Use Cases |
|-------|------|-----------|
| **Bedrock Haiku** (Claude 3.5) | Fast Hebrew generation | Greetings, task confirmations, list formatting, unknown intents |
| **Bedrock Sonnet** (Claude 3.5) | Complex Hebrew reasoning | `ask_question` intent — open-ended questions requiring deeper analysis |
| **Ollama** (llama3.1:8b) | Intent classification | Classifying messages into one of 8 intent categories (English-only) |

### Graceful Degradation

- If Bedrock is down → workflow catches the error, returns Hebrew fallback message
- If Ollama is down → intent detection falls back to keyword matching only (existing behavior)
- If memory service fails → workflow continues without memory context (empty memories list)
- If conversation save fails → response is still returned to the user (failure is logged)

## Memory System

### Three-Tier Memory Model

The MemoryService provides conversational context across sessions. Memories are extracted from conversations by Bedrock and stored with tiered expiration.

| Tier | Expiration | Use Case | Examples |
|------|-----------|----------|----------|
| **short** | 7 days | Transient context | "User asked about weather yesterday" |
| **medium** | 90 days | Recurring preferences | "Prefers morning reminders" |
| **long** | 365 days | Important facts | "Child's school name" |
| **permanent** | Never | Critical facts | Allergies, birthdays, family relationships |

### Memory Categories

| Category | Description |
|----------|-------------|
| `preference` | User preferences and settings |
| `goal` | Goals and objectives |
| `fact` | Factual information about the family |
| `habit` | Behavioral patterns |
| `context` | Conversational context |

### Memory Exclusions

Sensitive data is never stored as memory. The `memory_exclusions` table defines patterns that are checked before any memory is saved:

- **Keyword exclusions**: Case-insensitive substring matching (e.g., "password", "סיסמה", "credit card", "כרטיס אשראי")
- **Regex exclusions**: Pattern matching (e.g., credit card number format, Israeli ID number format)
- Exclusions can be global (apply to all members) or member-specific

### Memory Lifecycle

1. **Extract**: After each conversation, Bedrock analyzes the exchange and identifies facts worth remembering
2. **Filter**: Each candidate memory is checked against exclusion patterns
3. **Save**: Approved memories are stored with type, category, confidence, and calculated expiration
4. **Load**: Before generating a response, relevant memories are loaded and provided as context
5. **Track**: Each load updates `last_accessed_at` and increments `access_count` for relevance ranking
6. **Expire**: `cleanup_expired` removes memories past their expiration date

## Service Layer

**Message Handler** (`src/services/message_handler.py`) — Thin auth layer. Identifies the sender by phone, rejects unknown/inactive members, and delegates all message processing to the workflow engine. Contains no keyword matching or intent logic.

**Workflow Engine** (`src/services/workflow_engine.py`) — LangGraph StateGraph replacing the model router. Orchestrates message processing through 7 nodes: intent detection (Ollama), permission checking, memory loading, action dispatch (Bedrock), response assembly, memory extraction/saving, and conversation persistence.

**Bedrock Client** (`src/services/bedrock_client.py`) — Async client for AWS Bedrock Claude models. Supports Haiku (fast) and Sonnet (complex) model selection. Uses boto3 `bedrock-runtime` with the "fortress" AWS profile. 30-second timeout, returns Hebrew fallback on any error.

**Memory Service** (`src/services/memory_service.py`) — Manages the memory lifecycle: extraction via Bedrock, exclusion checking, persistence, loading with access tracking, and expiration cleanup. Enforces the three-tier expiration model and sensitive data exclusions.

**Model Router** (`src/services/model_router.py`) — Legacy intent-based message dispatch. Kept for backward compatibility. New messages flow through the workflow engine instead.

**Intent Detector** (`src/services/intent_detector.py`) — Classifies incoming messages into intent categories. Uses keyword matching (Hebrew + English) as the fast path, with LLM fallback via Ollama for unrecognized messages. Returns one of 8 intent strings.

**LLM Client** (`src/services/llm_client.py`) — Async HTTP client for Ollama REST API. Used only for intent classification after Phase 4B. Sends generation requests to `/api/generate` with 30-second timeout.

**System Prompts** (`src/prompts/system_prompts.py`) — Predefined prompt templates for both Ollama and Bedrock: FORTRESS_BASE (system identity), INTENT_CLASSIFIER (Ollama intent classification), TASK_EXTRACTOR (Ollama task extraction), TASK_RESPONDER (task formatting), MEMORY_EXTRACTOR (Bedrock memory extraction), TASK_EXTRACTOR_BEDROCK (Bedrock Hebrew task extraction).

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
| `memories` | Conversational memory with tiered expiration | UUID |
| `memory_exclusions` | Patterns for sensitive data that must never be stored | UUID |

Migrations are raw SQL files applied by `scripts/apply_migrations.sh`, tracked in a `schema_migrations` table.

## Key Design Decisions

- **Hybrid AI (Bedrock + Ollama)** — Bedrock for high-quality Hebrew generation, Ollama for fast local intent classification. Best of both worlds.
- **LangGraph StateGraph** — Structured, extensible workflow pipeline with conditional edges. Cleaner than imperative if/else routing.
- **Three-tier memory** — Tiered expiration prevents unbounded memory growth while preserving critical facts permanently.
- **Memory exclusions** — Keyword and regex patterns prevent storing sensitive data (PII, passwords, credit cards).
- **WAHA over WhatsApp Cloud API** — Self-hosted, no Meta business verification, full control over data
- **FastAPI over Flask/Django** — async-ready, auto-generated OpenAPI docs, native Pydantic integration
- **SQLAlchemy 2.0 mapped_column style** — typed ORM with modern Python syntax
- **Raw SQL migrations** — simple, auditable, no ORM migration tool dependency
- **Phone-based auth** — WhatsApp messages arrive with phone numbers, making phone the natural identity key
- **Docker Compose** — single-command deployment, PostgreSQL health checks, named volumes for persistence
- **Always return 200 to WAHA** — WAHA retries on non-200, so errors are logged but never cause webhook failures
- **Hebrew-first responses** — Primary users are Hebrew speakers; all LLM responses are in Hebrew
- **Echo prevention via fromMe** — Uses WAHA's `fromMe` field instead of phone comparison for reliable echo detection
- **Graceful degradation** — If Bedrock or Ollama is down, the system degrades gracefully with fallback messages
