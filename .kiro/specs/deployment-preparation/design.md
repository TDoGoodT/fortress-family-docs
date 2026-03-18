# Design Document: Deployment Preparation (Phase 3.5)

## Overview

Phase 3.5 prepares Fortress 2.0 for production deployment on a Mac Mini M4. The changes span three categories:

1. **Infrastructure & Scripts** — SQL migration for a system account, seed data template, one-touch setup script, Docker Compose bind-mount update, gitignore hardening.
2. **Documentation** — Setup guide (`docs/setup.md`) and README updates reflecting deployment capabilities.
3. **Permission Enforcement** — Adding `check_permission` calls to the message handler before task and document operations, with audit logging for denials.

No existing Python source files are modified except `src/services/message_handler.py`. All 48 existing tests continue to pass; new permission-denial tests are added alongside them.

## Architecture

The deployment preparation changes touch the following layers:

```mermaid
graph TD
    subgraph Scripts
        A[setup_mac_mini.sh] --> B[apply_migrations.sh]
        A --> C[seed_family.sh]
        B --> D[003_system_account.sql]
    end

    subgraph Docker
        E[docker-compose.yml] -->|bind mount| F["${STORAGE_PATH:-./storage}:/data/documents"]
    end

    subgraph Application
        G[message_handler.py] -->|calls| H[auth.py::check_permission]
        G -->|calls| I[audit.py::log_action]
    end

    subgraph Docs
        J[docs/setup.md]
        K[README.md]
    end
```

### Setup Script Flow

```mermaid
flowchart TD
    Start([setup_mac_mini.sh]) --> CheckDocker{Docker running?}
    CheckDocker -->|No| FailDocker[❌ Exit 1]
    CheckDocker -->|Yes| CheckCompose{docker compose available?}
    CheckCompose -->|No| FailCompose[❌ Exit 1]
    CheckCompose -->|Yes| CheckEnv{.env exists?}
    CheckEnv -->|No| CreateEnv[Create .env from .env.example]
    CheckEnv -->|Yes| SkipEnv[✅ Skip]
    CreateEnv --> Dirs
    SkipEnv --> Dirs
    Dirs[Create ~/fortress_storage/documents & backup] --> Compose[docker compose up -d]
    Compose --> WaitDB{Poll DB health}
    WaitDB -->|Timeout| FailDB[❌ Exit 1]
    WaitDB -->|Healthy| Migrate[Apply migrations]
    Migrate --> CheckSeed{seed_family.sh exists?}
    CheckSeed -->|Yes| RunSeed[Execute seed script]
    CheckSeed -->|No| WarnSeed[⚠️ Print warning]
    RunSeed --> HealthAPI[Check API /health]
    WarnSeed --> HealthAPI
    HealthAPI --> HealthWAHA[Check WAHA /api/sessions]
    HealthWAHA --> Summary[Print summary & next steps]
```

### Permission Check Flow in Message Handler

```mermaid
flowchart TD
    Msg[Incoming message] --> Auth[get_family_member_by_phone]
    Auth -->|Not found| Reject[Return unknown sender]
    Auth -->|Inactive| Inactive[Return inactive]
    Auth -->|Active| Route{Route by content}

    Route -->|"משימות / tasks"| PermRead[check_permission tasks read]
    Route -->|"משימה חדשה / new task"| PermWrite[check_permission tasks write]
    Route -->|"סיום משימה / done"| PermWriteC[check_permission tasks write]
    Route -->|Media| PermDoc[check_permission documents write]
    Route -->|Other text| Ack[Return acknowledgment]

    PermRead -->|Denied| DenyRead["🔒 + audit log"]
    PermRead -->|Allowed| ListTasks[list_tasks]

    PermWrite -->|Denied| DenyWrite["🔒 + audit log"]
    PermWrite -->|Allowed| CreateTask[create_task]

    PermWriteC -->|Denied| DenyComplete["🔒 + audit log"]
    PermWriteC -->|Allowed| CompleteTask[complete_task]

    PermDoc -->|Denied| DenyDoc["🔒 + audit log"]
    PermDoc -->|Allowed| StoreDoc[process_document]
```

## Components and Interfaces

### 1. Migration: `migrations/003_system_account.sql`

- Wrapped in `BEGIN; ... COMMIT;`
- Inserts a single row into `family_members` with a fixed UUID (`00000000-0000-0000-0000-000000000000`), name `'Fortress System'`, phone `'0000000000'`, role `'other'`, `is_active = true`
- Uses `ON CONFLICT (phone) DO NOTHING` for idempotency
- Follows the pattern of existing migrations (001, 002)

### 2. Seed Template: `scripts/seed_family.sh.template`

- Header comments: copy → edit → run workflow, phone format note, gitignore note
- `set -euo pipefail`
- `DB_URL` variable with default `postgresql://fortress:fortress_dev@localhost:5432/fortress`
- Placeholder `INSERT INTO family_members ... ON CONFLICT (phone) DO UPDATE SET` statements
- Closing `SELECT` to display current members
- No real PII — only `[PHONE_1]`, `[NAME_1]` style placeholders

### 3. Setup Script: `scripts/setup_mac_mini.sh`

- `set -euo pipefail`
- Prerequisite checks: `docker info`, `docker compose version`
- `.env` creation from `.env.example` if missing (prompt for DB password or use default)
- Directory creation: `~/fortress_storage/documents`, `~/fortress_storage/backup`
- `docker compose up -d`
- DB health polling loop (max ~30 retries, 2s sleep)
- Migration application via `psql` (inline, not calling `apply_migrations.sh` which requires `psql` on host — instead uses `docker compose exec db psql`)
- Conditional seed execution
- API health check (`curl http://localhost:8000/health`)
- WAHA status check (`curl http://localhost:3000/api/sessions`)
- Summary with next steps
- Idempotent — safe to re-run

### 4. Docker Compose Changes

Current:
```yaml
volumes:
  - document_storage:/data/documents
```

New:
```yaml
volumes:
  - ${STORAGE_PATH:-./storage}:/data/documents
```

The named volume `document_storage` is removed from the top-level `volumes:` section.

### 5. `.env.example` Update

Add:
```
STORAGE_PATH=./storage
```

(Already present in current `.env.example` as `STORAGE_PATH=/data/documents` — will be changed to `./storage` to match the bind-mount default.)

### 6. Gitignore Additions

Append to root `.gitignore`:
```gitignore
# Fortress deployment
fortress/scripts/seed_family.sh
fortress/.env
fortress/storage/*
!fortress/storage/.gitkeep
```

### 7. `storage/.gitkeep`

An empty file at `fortress/storage/.gitkeep` to ensure the directory is tracked.

### 8. `docs/setup.md`

Sections:
- Prerequisites (Docker Desktop, git, curl)
- Quick Setup (reference `setup_mac_mini.sh`)
- Manual Setup (step-by-step alternative)
- WhatsApp Setup (WAHA dashboard, QR code)
- Verification (health checks, DB connectivity)
- Troubleshooting (Docker, DB, WAHA)
- Backup (backup script, recommended locations)
- No real PII

### 9. README Updates

- Add "Deployment" section referencing `setup_mac_mini.sh` and `docs/setup.md`
- Add "First-Time Setup" subsection
- Update "Current Status" to reflect Phase 3.5
- Preserve all existing content

### 10. Message Handler Permission Integration

Four integration points in `src/services/message_handler.py`:

| Operation | Where | Permission Call | Denial Response |
|-----------|-------|----------------|-----------------|
| List tasks | `_handle_text` before calling `_handle_list_tasks` | `check_permission(db, phone, 'tasks', 'read')` | `"אין לך הרשאה לצפות במשימות 🔒"` |
| Create task | `_handle_text` before calling `_handle_create_task` | `check_permission(db, phone, 'tasks', 'write')` | `"אין לך הרשאה ליצור משימות 🔒"` |
| Complete task | `_handle_text` before calling `_handle_complete_task` | `check_permission(db, phone, 'tasks', 'write')` | `"אין לך הרשאה לעדכן משימות 🔒"` |
| Store document | `handle_incoming_message` before calling `_handle_media` | `check_permission(db, phone, 'documents', 'write')` | `"אין לך הרשאה להעלות מסמכים 🔒"` |

Implementation approach:
- Import `check_permission` from `src.services.auth`
- The `phone` parameter is already available in both `handle_incoming_message` and `_handle_text`
- `_handle_text` needs the `phone` parameter added to its signature (currently receives `db, member, message_text`)
- On denial: call `log_action(db, actor_id=member.id, action='permission_denied', resource_type=..., details={'attempted_action': ..., 'resource_type': ...})` then return the denial string
- The `_save_conversation` call still happens (denial is a valid conversation exchange)

Key change to `_handle_text` signature:
```python
def _handle_text(db: Session, member, phone: str, message_text: str) -> str:
```

And the caller in `handle_incoming_message`:
```python
response = _handle_text(db, member, phone, message_text)
```

### 11. New Test Cases

Added to `fortress/tests/test_message_handler.py` as new functions (existing tests untouched):

| Test | Setup | Assertion |
|------|-------|-----------|
| `test_child_can_read_tasks` | Mock member with role `child`, mock `check_permission` → `True` | Task list returned |
| `test_child_cannot_upload_document` | Mock member with role `child`, mock `check_permission` → `False` | `"🔒"` in response, `log_action` called with `permission_denied` |
| `test_grandparent_cannot_create_task` | Mock member with role `grandparent`, mock `check_permission` → `False` | `"🔒"` in response, `log_action` called with `permission_denied` |
| `test_parent_can_do_all_operations` | Mock member with role `parent`, mock `check_permission` → `True` | All operations succeed |

Each test patches `check_permission` alongside the existing `get_family_member_by_phone` mock pattern. The existing tests continue to work because they already mock `get_family_member_by_phone` — we need to also patch `check_permission` to return `True` in the existing tests' mock chain. However, per Requirement 9.2, we cannot modify existing test files. 

**Backward compatibility strategy**: The permission check in the handler calls `check_permission` which queries the DB. In existing tests, the DB is a `MagicMock(spec=Session)`. The mock DB's `.query()` chain will return a `MagicMock` by default, which is truthy. We need to verify this works, or alternatively patch `check_permission` at the module level in the new tests only. The existing tests mock `get_family_member_by_phone` at the module level — `check_permission` also calls `get_family_member_by_phone` internally, but since we import and call `check_permission` directly in the handler, we should patch it at `src.services.message_handler.check_permission`. This way existing tests that don't patch it will get the real function, which will call `db.query(...)` on the mock DB. The mock DB's query chain returns MagicMock objects, and `MagicMock().first()` returns a MagicMock (truthy), so `check_permission` will return `True` by default with a mock DB — existing tests pass without modification.

## Data Models

### System Account Row

| Column | Value |
|--------|-------|
| `id` | `00000000-0000-0000-0000-000000000000` |
| `name` | `Fortress System` |
| `phone` | `0000000000` |
| `role` | `other` |
| `is_active` | `true` |

This uses the existing `family_members` table schema — no schema changes needed.

### Seed Template Data Shape

The seed template inserts rows into the existing `family_members` table:

```sql
INSERT INTO family_members (name, phone, role, is_active)
VALUES ('[NAME]', '[PHONE]', 'parent', true)
ON CONFLICT (phone) DO UPDATE SET
    name = EXCLUDED.name,
    role = EXCLUDED.role,
    is_active = EXCLUDED.is_active;
```

### Permission Denial Audit Log Entry

Uses the existing `audit_log` table:

| Column | Value |
|--------|-------|
| `actor_id` | The denied member's UUID |
| `action` | `'permission_denied'` |
| `resource_type` | `'tasks'` or `'documents'` |
| `resource_id` | `NULL` |
| `details` | `{"attempted_action": "read"/"write", "resource_type": "tasks"/"documents"}` |

No new tables or columns are introduced in this phase.


## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Migration idempotency

*For any* number of times (≥1) the system account migration SQL is applied against a database, the resulting state of the `family_members` table should be identical to applying it exactly once — one row with phone `'0000000000'`, name `'Fortress System'`, role `'other'`, and `is_active = true`.

**Validates: Requirements 1.4, 1.5**

### Property 2: Seed insert idempotency

*For any* valid set of family member seed data (name, phone, role), applying the seed INSERT statements multiple times should produce the same `family_members` table state as applying them once — specifically, the count of rows matching each phone number should be exactly 1, and the name/role/is_active values should match the last applied values.

**Validates: Requirements 2.7**

### Property 3: Permission denial blocks operation and returns lock message

*For any* active family member and *for any* operation type (list tasks, create task, complete task, upload document), if `check_permission` returns `False` for that member's phone and the corresponding resource_type/action pair, then `handle_incoming_message` should return a string containing `"🔒"` and should NOT invoke the underlying service function (list_tasks, create_task, complete_task, process_document).

**Validates: Requirements 8.1, 8.2, 8.3, 8.4**

### Property 4: Permission denial produces audit log entry

*For any* active family member and *for any* operation type where `check_permission` returns `False`, the message handler should call `log_action` with `action='permission_denied'` and details containing the `resource_type` and `attempted_action`.

**Validates: Requirements 8.5**

### Property 5: Permitted operations succeed

*For any* active family member and *for any* operation type (list tasks, create task, complete task, upload document), if `check_permission` returns `True`, then the handler should invoke the underlying service function and return a response that does NOT contain `"🔒"`.

**Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.9**

### Property 6: Gitignore preserves existing rules

*For any* line in the original `.gitignore` file, that line should still be present in the updated `.gitignore` file after Phase 3.5 changes are applied.

**Validates: Requirements 5.4**

## Error Handling

### Setup Script Errors

| Condition | Behavior |
|-----------|----------|
| Docker not installed/running | Print `❌ Docker is not running...`, exit 1 |
| `docker compose` not available | Print `❌ docker compose not found...`, exit 1 |
| DB health timeout (30 retries × 2s) | Print `❌ Database did not become healthy...`, exit 1 |
| Migration failure | `set -e` causes immediate exit with non-zero code |
| Seed script missing | Print warning `⚠️`, continue (non-fatal) |
| API health check fails | Print `❌ API not responding`, continue (informational) |
| WAHA check fails | Print `❌ WAHA not responding`, continue (informational) |

All script errors use `set -euo pipefail` to fail fast on any unhandled error.

### Message Handler Permission Errors

| Condition | Behavior |
|-----------|----------|
| `check_permission` returns `False` | Return Hebrew denial message with 🔒, log `permission_denied` to audit, save conversation |
| `check_permission` raises exception | Not expected (queries mock/real DB), but if it does, the existing exception handling in the router layer catches it and returns 200 to WAHA |

Permission denials are not errors — they are expected access control behavior. The denial response is saved as a normal conversation record with an appropriate intent tag.

### Migration Errors

| Condition | Behavior |
|-----------|----------|
| `ON CONFLICT` on system account phone | `DO NOTHING` — silently skip, idempotent |
| Transaction failure | `BEGIN/COMMIT` ensures atomicity — partial state is rolled back |

## Testing Strategy

### Dual Testing Approach

This phase uses both unit tests and property-based tests:

- **Unit tests** (pytest): Verify specific examples, edge cases, and integration points. The existing 48 tests plus new permission-denial tests.
- **Property-based tests** (Hypothesis): Verify universal properties across randomized inputs, particularly around permission enforcement logic.

### Property-Based Testing Configuration

- **Library**: [Hypothesis](https://hypothesis.readthedocs.io/) for Python
- **Minimum iterations**: 100 per property test (via `@settings(max_examples=100)`)
- **Tag format**: Each test includes a docstring comment: `Feature: deployment-preparation, Property {N}: {title}`
- **Each correctness property is implemented by a single property-based test function**

### Unit Tests (Existing + New)

**Existing (48 tests, unmodified):**
All existing tests in `test_message_handler.py`, `test_tasks.py`, `test_auth.py`, `test_health.py`, `test_phone.py`, `test_recurring.py`, `test_whatsapp_client.py` continue to pass. The existing tests mock `get_family_member_by_phone` at the module level. Since `check_permission` is called directly in the handler (not through the mock), and the mock DB's `.query()` chain returns truthy MagicMock objects, `check_permission` will return `True` by default — existing tests pass without modification.

**New unit tests (added to `test_message_handler.py`):**

| Test | Description |
|------|-------------|
| `test_child_can_read_tasks` | Child role with `check_permission` → True can list tasks |
| `test_child_cannot_upload_document` | Child role with `check_permission` → False gets 🔒 denial, audit logged |
| `test_grandparent_cannot_create_task` | Grandparent role with `check_permission` → False gets 🔒 denial, audit logged |
| `test_parent_can_do_all_operations` | Parent role with `check_permission` → True succeeds for all operations |

### Property-Based Tests

New file: `fortress/tests/test_message_handler_properties.py`

| Test | Property | Strategy |
|------|----------|----------|
| `test_permission_denial_blocks_and_returns_lock` | Property 3 | Generate random (operation_type, phone, member_name) tuples. Mock `check_permission` → False. Assert response contains 🔒 and service function not called. |
| `test_permission_denial_produces_audit_log` | Property 4 | Same generation strategy. Assert `log_action` called with `action='permission_denied'`. |
| `test_permitted_operations_succeed` | Property 5 | Generate random (operation_type, phone, member_name) tuples. Mock `check_permission` → True. Assert response does NOT contain 🔒. |
| `test_migration_idempotency` | Property 1 | Generate random number of applications (1-5). Apply migration SQL. Assert single row with expected values. (Requires test DB — may be integration-level.) |
| `test_seed_idempotency` | Property 2 | Generate random family member data. Apply seed SQL multiple times. Assert row count and values match single application. (Requires test DB — may be integration-level.) |

For Properties 1 and 2 (SQL idempotency), these are best validated as integration tests against a real PostgreSQL instance. The property-based tests for Properties 3, 4, and 5 are pure unit tests that can run without a database.

### Test Generation Strategy for Permission Properties

```python
from hypothesis import strategies as st

# Strategy: generate a random operation type
operation_st = st.sampled_from([
    ("משימות", "tasks", "read"),           # list tasks
    ("משימה חדשה: test", "tasks", "write"), # create task
    ("סיום משימה 1", "tasks", "write"),     # complete task
])

# Strategy: generate a random phone number (Israeli format)
phone_st = st.from_regex(r"9725[0-9]{8}", fullmatch=True)

# Strategy: generate a random member name
name_st = st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L",)))
```

Media (document upload) is tested separately since it uses a different code path (`has_media=True`).
