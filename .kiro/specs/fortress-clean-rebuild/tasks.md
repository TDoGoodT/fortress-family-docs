# Implementation Plan: Fortress Clean Rebuild

## Overview

Ground-up rebuild of Fortress as a FastAPI + PostgreSQL 16 + Docker system. Legacy code is archived to `_legacy/`, and a new `fortress/` directory is created with a flat service architecture, phone-based auth, audit logging, WhatsApp webhook, and health endpoint. Implementation follows the design spec order: archive → structure → Docker/infra → database → application code → tests → documentation.

## Tasks

- [x] 1. Archive legacy code and create new directory structure (Design Spec 1)
  - [x] 1.1 Archive all existing files to `_legacy/`
    - Move all files and folders at the repo root (except `.git/`, `.gitignore`, and `.kiro/`) into a new `_legacy/` directory, preserving the original folder structure
    - After the move, the repo root should contain only `_legacy/`, `.git/`, `.gitignore`, and `.kiro/`
    - _Requirements: 1.1, 1.2, 1.3_

  - [x] 1.2 Create the `fortress/` directory structure
    - Create `fortress/src/` with empty `__init__.py`
    - Create `fortress/src/models/` with empty `__init__.py`
    - Create `fortress/src/routers/` with empty `__init__.py`
    - Create `fortress/src/services/` with empty `__init__.py`
    - Create `fortress/src/utils/` with empty `__init__.py`
    - Create `fortress/migrations/`
    - Create `fortress/scripts/`
    - Create `fortress/tests/` with empty `__init__.py`
    - Create `fortress/docs/`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 1.3 Update `.gitignore`
    - Ensure `.gitignore` contains: `.env`, `__pycache__/`, `*.pyc`, `.pytest_cache/`
    - _Requirements: 2.7_

- [x] 2. Docker and infrastructure files (Design Spec 2)
  - [x] 2.1 Create `fortress/docker-compose.yml`
    - Define `db` service using `postgres:16-alpine` with health check, named volume `fortress_data`, and env vars from `.env`
    - Define `fortress` service that builds from local Dockerfile, depends on healthy `db`, maps port 8000
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 2.2 Create `fortress/Dockerfile`
    - Use `python:3.12-slim` base image
    - Install dependencies from `requirements.txt`
    - Copy `src/` directory into the container
    - Expose port 8000 and run uvicorn as default command
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [x] 2.3 Create `fortress/requirements.txt`
    - Pin all dependencies: fastapi==0.115.0, uvicorn==0.30.0, sqlalchemy==2.0.35, psycopg2-binary==2.9.9, python-dotenv==1.0.1, httpx==0.27.0, pydantic==2.9.0, pytest==8.3.0, hypothesis==6.112.0
    - One dependency per line
    - _Requirements: 6.1, 6.2_

  - [x] 2.4 Create `fortress/.env.example`
    - Define `DB_PASSWORD` with placeholder, `STORAGE_PATH` with default local path, `LOG_LEVEL` with default `INFO`
    - _Requirements: 5.1, 5.2, 5.3_


- [x] 3. Database migration (Design Spec 3)
  - [x] 3.1 Create `fortress/migrations/001_initial_schema.sql`
    - Wrap entire migration in `BEGIN`/`COMMIT` transaction
    - Create `family_members` table with id (UUID PK, default gen_random_uuid()), name (TEXT NOT NULL), phone (TEXT UNIQUE NOT NULL), role (TEXT NOT NULL, CHECK IN parent/child/grandparent/other), is_active (BOOLEAN DEFAULT true), created_at (TIMESTAMPTZ DEFAULT now()), updated_at (TIMESTAMPTZ DEFAULT now())
    - Create `permissions` table with id (UUID PK), role (TEXT NOT NULL), resource_type (TEXT NOT NULL), can_read (BOOLEAN DEFAULT false), can_write (BOOLEAN DEFAULT false), UNIQUE on (role, resource_type)
    - Create `documents` table with all columns per design: id, uploaded_by (FK to family_members), file_path, original_filename, doc_type, vendor, amount (NUMERIC), currency (TEXT DEFAULT 'ILS'), doc_date, description, ai_summary, raw_text, source (CHECK IN whatsapp/email/filesystem/manual), metadata (JSONB DEFAULT '{}'), created_at
    - Create `transactions` table with id, document_id (FK to documents), category, amount (NUMERIC NOT NULL), currency (TEXT DEFAULT 'ILS'), direction (CHECK IN income/expense), transaction_date, description, created_at
    - Create `audit_log` table with id (BIGSERIAL PK), actor_id (FK to family_members), action (TEXT NOT NULL), resource_type, resource_id, details (JSONB DEFAULT '{}'), created_at
    - Create `conversations` table with id (UUID PK), family_member_id (FK to family_members), message_in, message_out, intent, metadata (JSONB DEFAULT '{}'), created_at
    - Insert default permission matrix: parent(finance rw, documents rw, tasks rw), child(finance none, documents r, tasks rw), grandparent(finance none, documents r, tasks r)
    - Create indexes on phone, foreign keys, timestamps, and frequently queried columns per design
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8_

  - [x] 3.2 Create `fortress/scripts/apply_migrations.sh`
    - Create `schema_migrations` tracking table if not exists
    - Iterate `migrations/*.sql` files in alphabetical order
    - Skip already-applied migrations
    - Apply new migrations via `psql`
    - Record applied migration filename and timestamp in `schema_migrations`
    - Exit with code 1 on failure, print `FAILED: <filename>`
    - Make the script executable (`chmod +x`)
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [x] 3.3 Create `fortress/scripts/backup.sh`
    - Create a placeholder backup script with TODO comments describing future backup functionality
    - This is the ONLY file allowed to have placeholder/TODO content
    - _Requirements: 2.3_

- [x] 4. Checkpoint — Verify infrastructure files
  - Ensure all infrastructure files (docker-compose.yml, Dockerfile, requirements.txt, .env.example, migration SQL, scripts) are complete and syntactically correct. Ask the user if questions arise.


- [x] 5. Application code — config, database, models (Design Spec 4)
  - [x] 5.1 Create `fortress/src/config.py`
    - Load environment variables via `python-dotenv`
    - Export `DATABASE_URL` (with fallback to `postgresql://fortress:fortress_dev@localhost:5432/fortress`), `STORAGE_PATH`, `LOG_LEVEL`
    - Use type hints throughout, follow PEP 8
    - _Requirements: 5.1, 5.2, 5.3_

  - [x] 5.2 Create `fortress/src/database.py`
    - Create SQLAlchemy `engine` from `DATABASE_URL`
    - Create `SessionLocal` session factory
    - Implement `get_db()` FastAPI dependency that yields DB sessions with proper cleanup in `finally` block
    - Implement `test_connection() -> bool` health check function
    - Use type hints throughout
    - _Requirements: 7.2, 7.3_

  - [x] 5.3 Create `fortress/src/models/__init__.py` and `fortress/src/models/schema.py`
    - Define SQLAlchemy 2.0 `mapped_column` style ORM models for all 6 tables: `FamilyMember`, `Permission`, `Document`, `Transaction`, `AuditLog`, `Conversation`
    - Match all column types, constraints, defaults, and foreign keys exactly as specified in the design data models section
    - Use type hints throughout
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

- [x] 6. Application code — utils, services, routers, main (Design Spec 4)
  - [x] 6.1 Create `fortress/src/utils/ids.py`
    - Implement `generate_id() -> str` that returns `str(uuid.uuid4())`
    - _Requirements: 2.1_

  - [x] 6.2 Create `fortress/src/services/auth.py`
    - Implement `get_family_member_by_phone(db: Session, phone: str) -> FamilyMember | None`
    - Implement `get_permissions_for_role(db: Session, role: str) -> list[Permission]`
    - Implement `check_permission(db: Session, phone: str, resource_type: str, action: str) -> bool` where action is "read" or "write"
    - Return `False` if member not found, not active, or no matching permission
    - Use type hints throughout
    - _Requirements: 11.1, 11.2, 11.3, 11.4_

  - [x] 6.3 Create `fortress/src/services/audit.py`
    - Implement `log_action(db: Session, actor_id: UUID, action: str, resource_type: str | None = None, resource_id: UUID | None = None, details: dict | None = None) -> None`
    - Create `AuditLog` record and commit to database
    - Use type hints throughout
    - _Requirements: 12.1, 12.2, 12.3_

  - [x] 6.4 Create `fortress/src/services/documents.py`
    - Implement `async def process_document(db: Session, file_path: str, uploaded_by: UUID, source: str) -> Document`
    - Placeholder implementation that creates a minimal document record (will be expanded with AI/OCR later)
    - This function must be complete and working, not a TODO stub
    - Use type hints throughout
    - _Requirements: 2.1_

  - [x] 6.5 Create `fortress/src/routers/health.py`
    - Implement `GET /health` endpoint returning `{"status": "ok", "service": "fortress", "version": "2.0.0", "database": "connected"|"disconnected"}`
    - Use `test_connection()` from database module to determine database status
    - _Requirements: 7.1_

  - [x] 6.6 Create `fortress/src/routers/whatsapp.py`
    - Implement `POST /webhook/whatsapp` endpoint that accepts any JSON body, logs it, and returns `{"status": "received"}`
    - _Requirements: 7.4_

  - [x] 6.7 Create `fortress/src/main.py`
    - Create FastAPI app with `title="Fortress"`, `version="2.0.0"`
    - Include health and whatsapp routers
    - On startup: test DB connection and log result; if DB fails, log warning but do not crash
    - Configure uvicorn to run on port 8000
    - _Requirements: 7.1, 7.2, 7.3, 7.5_

- [x] 7. Checkpoint — Verify application code
  - Ensure all Python source files have no syntax errors, proper type hints, and no imports from `_legacy/`. Ensure all tests pass. Ask the user if questions arise.


- [x] 8. Tests (Design Spec 5)
  - [x] 8.1 Create `fortress/tests/conftest.py`
    - Set up shared pytest fixtures: FastAPI TestClient, mocked SQLAlchemy session, sample FamilyMember and Permission objects
    - _Requirements: 13.1, 14.1_

  - [x] 8.2 Create `fortress/tests/test_health.py` — unit tests
    - Test GET `/health` returns 200 with `{"status": "ok"}` and correct service/version fields
    - Test health endpoint reports database status correctly (connected vs disconnected)
    - _Requirements: 13.1, 13.2_

  - [ ]* 8.3 Write property test for health endpoint consistency
    - **Property 3: Health endpoint consistency**
    - Generate random app states, verify GET `/health` always returns 200 with `"status": "ok"`, `"service": "fortress"`, `"version": "2.0.0"`
    - Add to `fortress/tests/test_health.py` or create `fortress/tests/test_health_properties.py`
    - Use `@settings(max_examples=100)`
    - Tag: `# Feature: fortress-clean-rebuild, Property 3: Health endpoint consistency`
    - **Validates: Requirements 7.1**

  - [ ]* 8.4 Write property test for webhook accepting arbitrary JSON
    - **Property 4: Webhook accepts arbitrary JSON**
    - Generate random JSON objects via `st.dictionaries(st.text(), st.text() | st.integers() | st.booleans())`, POST to `/webhook/whatsapp`, verify 200 with `"status": "received"`
    - Add to `fortress/tests/test_webhook_properties.py`
    - Use `@settings(max_examples=100)`
    - Tag: `# Feature: fortress-clean-rebuild, Property 4: Webhook accepts arbitrary JSON`
    - **Validates: Requirements 7.4**

  - [x] 8.5 Create `fortress/tests/test_auth.py` — unit tests
    - Test `get_family_member_by_phone` with known phone returns correct FamilyMember
    - Test `get_family_member_by_phone` with unknown phone returns None
    - Test `check_permission` returns True for active member with matching permission
    - Test `check_permission` returns False for inactive member, missing member, or missing permission
    - _Requirements: 14.1, 14.2_

  - [ ]* 8.6 Write property test for auth lookup correctness
    - **Property 7: Auth lookup correctness**
    - Generate random phone numbers and FamilyMember records, verify `get_family_member_by_phone` returns correct result or None
    - Add to `fortress/tests/test_auth_properties.py`
    - Use `@settings(max_examples=100)`
    - Tag: `# Feature: fortress-clean-rebuild, Property 7: Auth lookup correctness`
    - **Validates: Requirements 11.1, 11.2**

  - [ ]* 8.7 Write property test for permission check correctness
    - **Property 8: Permission check correctness**
    - Generate random (phone, resource_type, action) tuples with known permission state using `st.sampled_from` for roles/resources/actions
    - Verify `check_permission` returns True iff member exists, is active, and has matching permission flag
    - Add to `fortress/tests/test_auth_properties.py`
    - Use `@settings(max_examples=100)`
    - Tag: `# Feature: fortress-clean-rebuild, Property 8: Permission check correctness`
    - **Validates: Requirements 11.3, 11.4**

  - [ ]* 8.8 Write property test for audit log round trip
    - **Property 9: Audit log round trip**
    - Generate random audit entries via `st.uuids()`, `st.text()`, `st.dictionaries()`, log them via `log_action`, query back, verify all fields match with non-null id and created_at
    - Add to `fortress/tests/test_audit_properties.py`
    - Use `@settings(max_examples=100)`
    - Tag: `# Feature: fortress-clean-rebuild, Property 9: Audit log round trip`
    - **Validates: Requirements 12.1, 12.2, 12.3**

- [x] 9. Checkpoint — Verify all tests
  - Run `pytest fortress/tests/ -v` and ensure all unit tests pass. Ensure property tests are correctly structured. Ask the user if questions arise.


- [x] 10. Documentation (Design Spec 6)
  - [x] 10.1 Create `fortress/README.md`
    - Short summary of what Fortress is
    - Instructions for running with Docker Compose (`docker compose up`)
    - Instructions for applying migrations (`scripts/apply_migrations.sh`)
    - Overview of the project structure
    - Current status section describing the rebuild state
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

  - [x] 10.2 Create `fortress/docs/architecture.md`
    - High-level architecture overview: FastAPI + PostgreSQL 16 + Docker Compose
    - Description of the service layer (auth, audit, documents)
    - Database schema summary (6 tables)
    - Key design decisions from the design document
    - _Requirements: 2.5_

- [x] 11. Final checkpoint — Verify complete implementation
  - Ensure all files are complete and working (no TODOs except `backup.sh`)
  - Ensure no Python file imports or references `_legacy/`
  - Ensure all Python files have type hints and follow PEP 8
  - Ensure all SQL is wrapped in BEGIN/COMMIT transactions
  - Ensure all tests pass. Ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Every file must be complete and working — no TODOs except `fortress/scripts/backup.sh`
- No Python file may import or reference `_legacy/`
- All Python code must use type hints and follow PEP 8
- All SQL migrations must be wrapped in BEGIN/COMMIT transactions
- Property tests use Hypothesis with `@settings(max_examples=100)`
- Checkpoints ensure incremental validation between phases
