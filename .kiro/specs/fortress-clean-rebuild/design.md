# Design Document: Fortress Clean Rebuild

## Overview

Fortress 2.0 is a ground-up rebuild of the Fortress family intelligence system. The existing legacy codebase (event-sourced architecture with 40+ migration files, complex domain models) is archived into `_legacy/` and replaced with a simpler, value-first architecture built on FastAPI + PostgreSQL 16 + Docker.

The rebuild prioritizes:
- **Working code over architectural purity** — a running system beats a perfect design
- **Simplicity** — flat service layer, direct DB access, no event sourcing in v2.0
- **Local-first** — runs entirely on a Mac Mini M4 via Docker Compose
- **Clear boundaries** — WhatsApp ingestion → FastAPI → PostgreSQL, nothing more

The system manages household documents, finances, and family queries via WhatsApp. This foundation phase establishes the database schema, API skeleton, Docker infrastructure, and basic auth/audit services.

## Architecture

### System Architecture Diagram

```mermaid
graph TB
    subgraph External
        WA[WhatsApp Cloud API]
    end

    subgraph "Docker Compose (Mac Mini M4)"
        subgraph "fortress-app container"
            MAIN[FastAPI App<br/>src/main.py]
            HEALTH[GET /health<br/>src/routers/health.py]
            WEBHOOK[POST /webhook/whatsapp<br/>src/routers/whatsapp.py]
            AUTH[Auth Service<br/>src/services/auth.py]
            AUDIT[Audit Service<br/>src/services/audit.py]
            DOCS[Document Service<br/>src/services/documents.py]
            DB_MOD[Database Layer<br/>src/database.py]
        end

        subgraph "fortress-db container"
            PG[(PostgreSQL 16<br/>6 tables)]
        end
    end

    WA -->|POST JSON| WEBHOOK
    MAIN --> HEALTH
    MAIN --> WEBHOOK
    WEBHOOK --> AUTH
    WEBHOOK --> AUDIT
    AUTH --> DB_MOD
    AUDIT --> DB_MOD
    DOCS --> DB_MOD
    DB_MOD -->|SQLAlchemy| PG
```

### Request Flow

```mermaid
sequenceDiagram
    participant WA as WhatsApp
    participant API as FastAPI
    participant Auth as Auth Service
    participant DB as PostgreSQL

    WA->>API: POST /webhook/whatsapp
    API->>Auth: get_family_member_by_phone(phone)
    Auth->>DB: SELECT from family_members
    DB-->>Auth: FamilyMember | None
    Auth-->>API: member or not found
    API-->>WA: {"status": "received"}
```

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Framework | FastAPI | Async-ready, auto-docs, Pydantic integration |
| ORM | SQLAlchemy 2.0 | Mature, typed `mapped_column` style |
| Database | PostgreSQL 16 | JSON support, UUID generation, robust |
| Container | Docker Compose | Single-command deployment on Mac Mini |
| Auth model | Phone-based + role permissions | WhatsApp messages arrive with phone numbers |
| Migration strategy | Raw SQL + bash runner | Simple, auditable, no ORM migration dependency |
| Legacy handling | Archive to `_legacy/` | Preserve history without polluting new code |

## Components and Interfaces

### 1. Infrastructure Layer

**docker-compose.yml** — Defines two services:
- `db`: PostgreSQL 16 Alpine with health check, named volume `fortress_data`
- `fortress`: FastAPI app built from local Dockerfile, depends on healthy `db`

**Dockerfile** — Python 3.12-slim base, installs deps, copies `src/`, runs uvicorn on port 8000.

**requirements.txt** — Pinned dependencies: fastapi==0.115.0, uvicorn==0.30.0, sqlalchemy==2.0.35, psycopg2-binary==2.9.9, python-dotenv==1.0.1, httpx==0.27.0, pydantic==2.9.0, pytest==8.3.0, hypothesis==6.112.0.

**.env.example** — Template with `DB_PASSWORD`, `STORAGE_PATH`, `LOG_LEVEL`.

### 2. Configuration (`src/config.py`)

Loads environment variables via `python-dotenv`. Exports:
- `DATABASE_URL: str` — PostgreSQL connection string
- `STORAGE_PATH: str` — Document storage path
- `LOG_LEVEL: str` — Logging level

### 3. Database Layer (`src/database.py`)

- `engine` — SQLAlchemy engine from `DATABASE_URL`
- `SessionLocal` — Session factory
- `get_db()` — FastAPI dependency yielding DB sessions
- `test_connection() -> bool` — Connection health check

### 4. ORM Models (`src/models/schema.py`)

SQLAlchemy 2.0 mapped models for all 6 tables:

| Model | Table | Primary Key |
|-------|-------|-------------|
| `FamilyMember` | `family_members` | UUID (gen_random_uuid) |
| `Permission` | `permissions` | UUID (gen_random_uuid) |
| `Document` | `documents` | UUID (gen_random_uuid) |
| `Transaction` | `transactions` | UUID (gen_random_uuid) |
| `AuditLog` | `audit_log` | BIGSERIAL |
| `Conversation` | `conversations` | UUID (gen_random_uuid) |

### 5. Services

**Auth Service (`src/services/auth.py`)**

```python
def get_family_member_by_phone(db: Session, phone: str) -> FamilyMember | None
def get_permissions_for_role(db: Session, role: str) -> list[Permission]
def check_permission(db: Session, phone: str, resource_type: str, action: str) -> bool
```

- `action` is `"read"` or `"write"`
- Returns `False` if member not found, not active, or no matching permission

**Audit Service (`src/services/audit.py`)**

```python
def log_action(db: Session, actor_id: UUID, action: str, resource_type: str | None = None, resource_id: UUID | None = None, details: dict | None = None) -> None
```

**Document Service (`src/services/documents.py`)**

```python
async def process_document(db: Session, file_path: str, uploaded_by: UUID, source: str) -> Document
```

Placeholder — creates a minimal document record. Will be expanded with AI/OCR later.

### 6. Routers

**Health Router (`src/routers/health.py`)**
- `GET /health` → `{"status": "ok", "service": "fortress", "version": "2.0.0", "database": "connected"|"disconnected"}`

**WhatsApp Router (`src/routers/whatsapp.py`)**
- `POST /webhook/whatsapp` → Accepts any JSON, logs it, returns `{"status": "received"}`

### 7. Application Entry Point (`src/main.py`)

- FastAPI app with `title="Fortress"`, `version="2.0.0"`
- Includes health and whatsapp routers
- On startup: tests DB connection, logs result
- DB failure on startup: logs warning, does not crash

### 8. Migration Runner (`scripts/apply_migrations.sh`)

Bash script that:
1. Creates `schema_migrations` table if not exists
2. Iterates `migrations/*.sql` in alphabetical order
3. Skips already-applied migrations
4. Applies new migrations via `psql`
5. Records applied migrations with timestamp
6. Exits with code 1 on failure

### 9. Utilities (`src/utils/ids.py`)

- `generate_id() -> str` — Returns `str(uuid.uuid4())`

## Data Models

### Entity Relationship Diagram

```mermaid
erDiagram
    family_members {
        UUID id PK
        TEXT name
        TEXT phone UK
        TEXT role
        BOOLEAN is_active
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
    }

    permissions {
        UUID id PK
        TEXT role
        TEXT resource_type
        BOOLEAN can_read
        BOOLEAN can_write
    }

    documents {
        UUID id PK
        UUID uploaded_by FK
        TEXT file_path
        TEXT original_filename
        TEXT doc_type
        TEXT vendor
        DECIMAL amount
        TEXT currency
        DATE doc_date
        TEXT description
        TEXT ai_summary
        TEXT raw_text
        TEXT source
        JSONB metadata
        TIMESTAMPTZ created_at
    }

    transactions {
        UUID id PK
        UUID document_id FK
        TEXT category
        DECIMAL amount
        TEXT currency
        TEXT direction
        DATE transaction_date
        TEXT description
        TIMESTAMPTZ created_at
    }

    audit_log {
        BIGSERIAL id PK
        UUID actor_id FK
        TEXT action
        TEXT resource_type
        UUID resource_id
        JSONB details
        TIMESTAMPTZ created_at
    }

    conversations {
        UUID id PK
        UUID family_member_id FK
        TEXT message_in
        TEXT message_out
        TEXT intent
        JSONB metadata
        TIMESTAMPTZ created_at
    }

    family_members ||--o{ documents : "uploads"
    family_members ||--o{ audit_log : "performs"
    family_members ||--o{ conversations : "has"
    documents ||--o{ transactions : "contains"
```

### Table Details

**family_members** — Core identity table. Each family member has a unique phone number and a role that determines their permissions. The `is_active` flag allows soft-disabling members.

**permissions** — Role-based access control. Maps (role, resource_type) to read/write booleans. Seeded with defaults for parent, child, and grandparent roles across finance, documents, and tasks resource types.

**documents** — Stores metadata about uploaded documents. The `source` field tracks ingestion channel (whatsapp, email, filesystem, manual). Fields like `ai_summary`, `raw_text`, and `vendor` will be populated by future AI/OCR processing.

**transactions** — Financial transactions extracted from documents. Each transaction has a direction (income/expense) and links back to its source document.

**audit_log** — Append-only log of all significant system actions. Uses BIGSERIAL for ordered, auto-incrementing IDs. Stores structured details as JSONB.

**conversations** — WhatsApp conversation history. Stores inbound/outbound messages, detected intent, and metadata for each interaction.

### Default Permission Matrix

| Role | Finance | Documents | Tasks |
|------|---------|-----------|-------|
| parent | read + write | read + write | read + write |
| child | none | read | read + write |
| grandparent | none | read | read |

### Constraints and Validation

- `family_members.role` CHECK: must be one of `'parent'`, `'child'`, `'grandparent'`, `'other'`
- `documents.source` CHECK: must be one of `'whatsapp'`, `'email'`, `'filesystem'`, `'manual'`
- `transactions.direction` CHECK: must be one of `'income'`, `'expense'`
- `permissions` UNIQUE on `(role, resource_type)`
- `family_members.phone` UNIQUE

### Indexes

Performance indexes on frequently queried columns:
- `family_members`: phone
- `documents`: doc_type, vendor, created_at, source
- `transactions`: category, transaction_date, direction
- `audit_log`: actor_id, created_at
- `conversations`: family_member_id, created_at

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Archive file preservation

*For any* file that existed at the repo root before the archive operation, that file should exist at the same relative path inside `_legacy/` with identical content after the archive operation.

**Validates: Requirements 1.1, 1.3**

### Property 2: No legacy imports

*For any* Python source file in the `fortress/` directory tree, the file should not contain any import statement or string reference to `_legacy/`.

**Validates: Requirements 2.7**

### Property 3: Health endpoint consistency

*For any* GET request to `/health` (regardless of application state), the response status code should be 200 and the response body should contain `"status": "ok"`, `"service": "fortress"`, and `"version": "2.0.0"`.

**Validates: Requirements 7.1**

### Property 4: Webhook accepts arbitrary JSON

*For any* valid JSON object sent as a POST request to `/webhook/whatsapp`, the response status code should be 200 and the response body should contain `"status": "received"`.

**Validates: Requirements 7.4**

### Property 5: Migration runner idempotence

*For any* set of SQL migration files, running the migration runner twice in succession should produce the same database state as running it once — no migrations should be re-applied on the second run, and `schema_migrations` should contain exactly one entry per migration file.

**Validates: Requirements 8.2, 8.3, 8.6**

### Property 6: Migration runner ordering

*For any* set of SQL migration files with alphabetically ordered filenames, the migration runner should apply them in strict alphabetical order, and the `schema_migrations` table should reflect this ordering by timestamp.

**Validates: Requirements 8.4**

### Property 7: Auth lookup correctness

*For any* phone number, `get_family_member_by_phone` should return the matching `FamilyMember` record if one exists in the database with that phone number, or `None` if no matching record exists.

**Validates: Requirements 11.1, 11.2**

### Property 8: Permission check correctness

*For any* combination of (phone number, resource_type, action), `check_permission` should return `True` if and only if: (a) a family member with that phone exists and is active, AND (b) a permission record exists for that member's role and resource_type with the corresponding `can_read` or `can_write` flag set to `True`.

**Validates: Requirements 11.3, 11.4**

### Property 9: Audit log round trip

*For any* action logged via `log_action(db, actor_id, action, resource_type, resource_id, details)`, querying the `audit_log` table should return a record with matching `actor_id`, `action`, `resource_type`, `resource_id`, and `details` fields, a non-null auto-incremented `id`, and a non-null `created_at` timestamp.

**Validates: Requirements 12.1, 12.2, 12.3**

## Error Handling

### Startup Errors

- **Database connection failure**: The app logs a warning and continues running. The health endpoint reports `"database": "disconnected"`. No crash, no retry loop — the operator can check `/health` and fix the DB.
- **Missing environment variables**: `src/config.py` provides sensible defaults for local development. Missing `DATABASE_URL` falls back to `postgresql://fortress:fortress_dev@localhost:5432/fortress`.

### Request Errors

- **Invalid JSON on webhook**: FastAPI's built-in request validation returns 422 with details.
- **Database errors during request**: SQLAlchemy exceptions are caught at the service layer. The session is rolled back via the `get_db()` dependency's `finally` block.

### Migration Errors

- **SQL execution failure**: The migration runner prints `FAILED: <filename>` and exits with code 1. No partial state — each migration is wrapped in `BEGIN/COMMIT`.
- **Connection failure**: `psql` returns non-zero, the runner catches it and exits.

### Auth Errors

- **Unknown phone number**: Returns `None`, not an exception. Callers decide how to handle.
- **Inactive member**: `check_permission` returns `False` for inactive members — same as "no permission."
- **Missing permission record**: Returns `False` — deny by default.

## Testing Strategy

### Dual Testing Approach

This project uses both unit tests and property-based tests for comprehensive coverage:

- **Unit tests** (pytest): Verify specific examples, edge cases, and integration points
- **Property-based tests** (Hypothesis): Verify universal properties across randomly generated inputs

Both are complementary — unit tests catch concrete bugs with known inputs, property tests verify general correctness across the input space.

### Property-Based Testing Configuration

- **Library**: [Hypothesis](https://hypothesis.readthedocs.io/) for Python
- **Minimum iterations**: 100 per property test (via `@settings(max_examples=100)`)
- **Tag format**: Each test is tagged with a comment: `# Feature: fortress-clean-rebuild, Property {number}: {property_text}`
- **Each correctness property is implemented by a single property-based test**

### Unit Tests

| Test File | What It Tests | Approach |
|-----------|--------------|----------|
| `tests/test_health.py` | GET /health returns 200 with status "ok" | FastAPI TestClient, mocked DB |
| `tests/test_auth.py` | Phone lookup (found/not found), permission checks | Mocked SQLAlchemy session |

Unit tests focus on:
- Specific examples that demonstrate correct behavior (known phone → member, unknown phone → None)
- Edge cases (DB down at startup, inactive member permissions)
- Integration points (router → service → DB dependency)

### Property Tests

| Property | Test Description | Generator Strategy |
|----------|-----------------|-------------------|
| Property 3: Health endpoint consistency | Generate random app states, verify /health always returns 200 + "ok" | Hypothesis `@given` with stateful testing |
| Property 4: Webhook accepts arbitrary JSON | Generate random JSON objects, POST to webhook, verify 200 | `st.dictionaries(st.text(), st.text() \| st.integers() \| st.booleans())` |
| Property 7: Auth lookup correctness | Generate random phone numbers and family member records, verify lookup returns correct result | Custom strategy for phone numbers + FamilyMember fixtures |
| Property 8: Permission check correctness | Generate random (phone, resource_type, action) tuples with known permission state, verify check_permission returns correct boolean | `st.sampled_from` for roles/resources/actions + permission matrix |
| Property 9: Audit log round trip | Generate random audit entries, log them, query back, verify all fields match | `st.uuids()`, `st.text()`, `st.dictionaries()` for details |

### Test Execution

```bash
# Run all tests (unit + property)
pytest tests/ -v

# Run only property tests
pytest tests/ -v -k "property"

# Run with Hypothesis verbose output
pytest tests/ -v --hypothesis-show-statistics
```

### What Is NOT Tested

- Docker Compose configuration (validated by `docker-compose config` and manual smoke test)
- Dockerfile build (validated by `docker build` and manual smoke test)
- Migration SQL syntax (validated by applying to a real PostgreSQL instance)
- File system operations for archive (validated manually)
- README/docs content quality (human review)
