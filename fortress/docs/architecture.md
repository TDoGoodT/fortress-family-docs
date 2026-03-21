# Fortress 2.0 Architecture

## Overview

Fortress 2.0 is built on FastAPI + PostgreSQL 16 + WAHA + Ollama + AWS Bedrock + OpenRouter + Docker Compose. It runs locally on a Mac Mini M4 as four containers: the Python application, the database, the WhatsApp bridge, and the local LLM. The application container connects to AWS Bedrock for sensitive Hebrew text generation and OpenRouter for cheap/free model access on non-sensitive tasks.

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
│  ├── /health         (DB + Ollama + Bedrock + OpenRouter) │
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
│  ├── intent_node       → keyword match / "needs_llm" │
│  ├── unified_llm_node  → single LLM classify + respond │
│  ├── permission_node   → Auth service            │
│  ├── task_create_node  → create task after permission │
│  ├── memory_load_node  → MemoryService           │
│  ├── action_node       → ModelDispatcher (route) │
│  ├── response_node     → pass-through / denial   │
│  ├── memory_save_node  → Bedrock (always)        │
│  └── conversation_save_node → DB                 │
│                                                  │
│  Services:                                       │
│  ├── message_handler   ← thin auth layer         │
│  ├── workflow_engine   ← LangGraph pipeline      │
│  ├── bedrock_client    ← AWS Bedrock Claude      │
│  ├── openrouter_client ← OpenRouter API          │
│  ├── routing_policy    ← sensitivity routing     │
│  ├── model_dispatch    ← unified dispatch        │
│  ├── memory_service    ← three-tier memory       │
│  ├── intent_detector   ← keyword-only (sync)     │
│  ├── unified_handler   ← classify + respond      │
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
│  └── system_prompts    ← unified + Bedrock prompts│
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
                                    ┌──────────────────┐
                                    │ OpenRouter       │
                                    │ (free/cheap LLMs)│
                                    └──────────────────┘
```

## Message Flow (LangGraph Workflow)

```
START
  │
  ▼
┌─────────────┐
│ intent_node │──── Synchronous keyword matching only (no Ollama)
└──────┬──────┘
       │
       ├── keyword match ───────────────────────────┐
       │                                            │
       ├── "needs_llm" (no keyword match)           │
       ▼                                            │
┌───────────────────┐                               │
│ unified_llm_node  │── single LLM call:            │
│                   │   classify intent + respond   │
└──────┬────────────┘                               │
       │                                            │
       ▼                                            ▼
┌──────────────────┐
│ permission_node  │──── Auth service checks role-based access
└──────┬───────────┘
       │
       ├── denied ──────────────────────────────────┐
       │                                            │
       ├── granted + from_unified + task_data       │
       │   ▼                                        │
       │  ┌──────────────────┐                      │
       │  │ task_create_node │── creates task       │
       │  └──────┬───────────┘                      │
       │         │                                  │
       ├── granted + from_unified (no task_data)    │
       │   │     │                                  │
       │   │     ▼                                  │
       │   └──► ┌───────────────┐                   │
       │        │ response_node │◄──────────────────┘
       │        └──────┬────────┘  (🔒 denial msg if denied)
       │               │
       ├── granted + keyword origin                 │
       ▼               │                            │
┌──────────────────┐   │
│ memory_load_node │   │
└──────┬───────────┘   │
       ▼               │
┌─────────────┐        │
│ action_node │── Bedrock/OpenRouter generates      │
│             │   Hebrew response                   │
└──────┬──────┘        │
       ▼               │
┌───────────────┐◄─────┘
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
8. **intent_node**: Synchronous keyword matching — if a keyword matches, returns the intent directly. If no keyword matches, returns `"needs_llm"` (no Ollama, no network calls)
9. If `"needs_llm"` → **unified_llm_node**: Single LLM call via ModelDispatcher that classifies intent AND generates a Hebrew response simultaneously. Stores `intent`, `response`, `task_data` (if create_task), and `from_unified=True` in workflow state
10. **permission_node**: Auth service checks role-based permissions for the classified intent
11. If denied → skips to response_node with 🔒 denial message (replaces any LLM-generated response)
12. If granted + `from_unified` + `task_data` → **task_create_node**: Creates the task via task service, then proceeds to response_node
13. If granted + `from_unified` (no task_data) → proceeds directly to response_node (response already generated by unified_llm_node, skips action_node)
14. If granted + keyword origin → **memory_load_node**: MemoryService loads relevant memories for context → **action_node**: ModelDispatcher routes to the appropriate provider based on sensitivity (OpenRouter for low/medium, Bedrock for high). Haiku for simple intents, Sonnet for `ask_question`
15. **response_node**: Passes through the generated response
16. **memory_save_node**: Bedrock extracts facts from the conversation (always uses Bedrock directly — memory content is sensitive), MemoryService saves them (with exclusion filtering)
17. **conversation_save_node**: Saves Conversation record to DB with detected intent
18. Response is sent back through WAHA API → WhatsApp → user's phone

## Hybrid AI Architecture

### Model Routing

| Model | Tier | Role | Use Cases |
|-------|------|------|-----------|
| **OpenRouter** (free/cheap) | Tier 2 | Non-sensitive Hebrew generation | Greetings, task formatting, simple responses (low/medium sensitivity) |
| **Bedrock Haiku** (Claude 3.5) | Tier 3 | Fast Hebrew generation | Task confirmations, list formatting, fallback for medium intents |
| **Bedrock Sonnet** (Claude 3.5) | Tier 3 | Complex Hebrew reasoning | `ask_question` intent — open-ended questions requiring deeper analysis |
| **Ollama** (llama3.1:8b) | Tier 1 | Last-resort generation fallback | Fallback Hebrew generation when OpenRouter and Bedrock both fail |

### Routing Policy

Requests are routed based on data sensitivity:

| Sensitivity | Intents | Provider Order |
|------------|---------|----------------|
| Low | greeting | OpenRouter → Bedrock → Ollama |
| Medium | list_tasks, create_task, complete_task, list_documents, unknown | OpenRouter → Bedrock → Ollama |
| High | ask_question, upload_document | Bedrock → Ollama (no OpenRouter) |

High-sensitivity intents never go to OpenRouter — sensitive data stays in AWS.

### Model Dispatcher

The `ModelDispatcher` service provides unified dispatch with automatic fallback:

1. Get the ordered provider list from `RoutingPolicy` based on intent sensitivity
2. Try each provider in order until one succeeds
3. If a provider returns the Hebrew fallback message, treat it as a failure and try the next
4. If all providers fail, return the hardcoded Hebrew fallback message

### Graceful Degradation

The system uses a full fallback chain for Hebrew generation:

- **Preferred provider fails** → try next provider in the routing order
- **OpenRouter fails or no API key** → skip to Bedrock
- **Bedrock fails** → try Ollama as last-resort generator
- **All providers fail** → return hardcoded Hebrew fallback: "מצטער, לא הצלחתי לעבד את הבקשה. נסה שוב."
- **Ollama is down** → generation fallback skipped, system continues with OpenRouter/Bedrock
- **No keyword match** → `"needs_llm"` routes to unified_llm_node for single-call classify+respond
- **Memory service fails** → workflow continues without memory context (empty memories list)
- **Conversation save fails** → response is still returned to the user (failure is logged)
- **OpenRouter API key is empty** → system works without it, routing skips OpenRouter entirely

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

**Workflow Engine** (`src/services/workflow_engine.py`) — LangGraph StateGraph orchestrating message processing through 9 nodes: synchronous intent detection (keyword-only), unified LLM classification+response (for non-keyword messages), permission checking, task creation (for unified create_task), memory loading, action dispatch (for keyword-matched intents), response assembly, memory extraction/saving, and conversation persistence.

**Bedrock Client** (`src/services/bedrock_client.py`) — Async client for AWS Bedrock Claude models. Supports Haiku (fast) and Sonnet (complex) model selection. Uses boto3 `bedrock-runtime` with the "fortress" AWS profile. 30-second timeout, returns Hebrew fallback on any error.

**OpenRouter Client** (`src/services/openrouter_client.py`) — Async HTTP client for OpenRouter API (OpenAI-compatible format). Used for cheap/free model access on non-sensitive tasks. 30-second timeout via httpx, returns Hebrew fallback on any error. Returns immediately if no API key is configured.

**Routing Policy** (`src/services/routing_policy.py`) — Pure functions mapping intents to sensitivity levels (low/medium/high) and sensitivity levels to ordered provider lists. High-sensitivity intents never include OpenRouter. Unknown intents default to high sensitivity (fail-safe).

**Model Dispatcher** (`src/services/model_dispatch.py`) — Unified dispatch service that tries providers in routing order until one succeeds. Selects Bedrock model per intent (sonnet for ask_question, haiku otherwise). Skips OpenRouter when no API key is set. Returns Hebrew fallback if all providers fail.

**Memory Service** (`src/services/memory_service.py`) — Manages the memory lifecycle: extraction via Bedrock, exclusion checking, persistence, loading with access tracking, and expiration cleanup. Enforces the three-tier expiration model and sensitive data exclusions.

**Model Router** (`src/services/model_router.py`) — Legacy intent-based message dispatch. Kept for backward compatibility. New messages flow through the workflow engine instead.

**Intent Detector** (`src/services/intent_detector.py`) — Synchronous keyword-only classification. Matches incoming messages against Hebrew and English keyword patterns. Returns a known intent string on match, or `"needs_llm"` when no keyword matches (indicating the message requires LLM-based classification via the unified handler). No network calls, no Ollama dependency.

**Unified Handler** (`src/services/unified_handler.py`) — Single LLM call combining intent classification and response generation for non-keyword messages. Sends the message with the UNIFIED_CLASSIFY_AND_RESPOND prompt to ModelDispatcher, parses the structured JSON response (intent, response text, optional task_data), and returns the result. Falls back gracefully on invalid JSON or unrecognized intents.

**LLM Client** (`src/services/llm_client.py`) — Async HTTP client for Ollama REST API. Retained as a last-resort generation fallback in ModelDispatcher. No longer used for intent classification. Sends generation requests to `/api/generate` with 30-second timeout.

**System Prompts** (`src/prompts/system_prompts.py`) — Predefined prompt templates: FORTRESS_BASE (system identity), UNIFIED_CLASSIFY_AND_RESPOND (single-call intent classification + Hebrew response generation), INTENT_CLASSIFIER (legacy Ollama intent classification), TASK_EXTRACTOR (Ollama task extraction), TASK_RESPONDER (task formatting), MEMORY_EXTRACTOR (Bedrock memory extraction), TASK_EXTRACTOR_BEDROCK (Bedrock Hebrew task extraction).

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

- **Hybrid AI (Bedrock + Unified LLM)** — Bedrock for high-quality Hebrew generation, unified classify+respond for non-keyword messages in a single LLM call. Ollama retained as last-resort generation fallback.
- **3-Tier Model Routing** — OpenRouter for cheap/free models on non-sensitive tasks, Bedrock for sensitive/complex tasks, Ollama as last-resort fallback. Sensitivity-based routing ensures data privacy.
- **Unified Classify+Respond** — Non-keyword messages are classified and answered in a single LLM call, eliminating the previous two-call flow (Ollama classify → Bedrock generate). Reduces latency by ~50%.
- **Automatic Fallback Chain** — If the preferred provider fails, the next is tried automatically. System never crashes — worst case returns a hardcoded Hebrew message.
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
- **Graceful degradation** — If any provider is down, the system degrades gracefully through the fallback chain. OpenRouter is optional — works without an API key.
