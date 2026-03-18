# Implementation Plan: Deployment Preparation (Phase 3.5)

## Overview

Prepare Fortress 2.0 for Mac Mini M4 deployment: system account migration, seed template, gitignore hardening, local storage setup, Docker Compose bind-mount, permission enforcement in message handler, setup script, documentation, and full test pass.

## Tasks

- [x] 1. Create system account migration
  - [x] 1.1 Create `fortress/migrations/003_system_account.sql`
    - Wrap in `BEGIN; ... COMMIT;` transaction block
    - Insert row into `family_members`: fixed UUID `00000000-0000-0000-0000-000000000000`, name `'Fortress System'`, phone `'0000000000'`, role `'other'`, `is_active = true`
    - Use `ON CONFLICT (phone) DO NOTHING` for idempotent execution
    - Follow the pattern of existing migrations (001, 002)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x] 2. Create seed script template
  - [x] 2.1 Create `fortress/scripts/seed_family.sh.template`
    - Add header comments explaining copy → edit → run workflow
    - Include comment noting `seed_family.sh` is gitignored
    - Include comment specifying phone format: Israeli international without `+` prefix (e.g., `972501234567`)
    - Use `set -euo pipefail` as first executable line after shebang
    - Define `DB_URL` variable with default `postgresql://fortress:fortress_dev@localhost:5432/fortress`
    - Add placeholder `INSERT INTO family_members ... ON CONFLICT (phone) DO UPDATE SET` statements with `[NAME_1]`, `[PHONE_1]` style placeholders — no real PII
    - Add closing `SELECT` query to display current family members
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10_

- [x] 3. Update .gitignore
  - [x] 3.1 Append fortress deployment rules to root `.gitignore`
    - Add `fortress/scripts/seed_family.sh` to prevent committing personal data
    - Add `fortress/.env` to prevent committing environment secrets
    - Add `fortress/storage/*` with exception `!fortress/storage/.gitkeep`
    - Retain all existing ignore rules without modification
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [x] 4. Create storage directory and update Docker Compose
  - [x] 4.1 Create `fortress/storage/.gitkeep`
    - Empty file to ensure the storage directory is tracked in version control
    - _Requirements: 4.3_

  - [x] 4.2 Update `fortress/docker-compose.yml` for local storage bind mount
    - Change fortress service volume from `document_storage:/data/documents` to `${STORAGE_PATH:-./storage}:/data/documents`
    - Remove `document_storage` from the top-level `volumes:` section
    - _Requirements: 4.1, 4.5_

  - [x] 4.3 Update `fortress/.env.example`
    - Change `STORAGE_PATH=/data/documents` to `STORAGE_PATH=./storage`
    - _Requirements: 4.2_

- [x] 5. Checkpoint — Verify infrastructure changes
  - Ensure all infrastructure files are consistent (migration, seed template, gitignore, docker-compose, .env.example, storage/.gitkeep). Ask the user if questions arise.

- [x] 6. Add permission checks to message handler
  - [x] 6.1 Update `fortress/src/services/message_handler.py`
    - Import `check_permission` from `src.services.auth`
    - Add `phone` parameter to `_handle_text` signature: `def _handle_text(db, member, phone, message_text)`
    - Update the `_handle_text` call in `handle_incoming_message` to pass `phone`
    - Before list tasks (`"משימות"` / `"tasks"`): call `check_permission(db, phone, 'tasks', 'read')`, on denial return `"אין לך הרשאה לצפות במשימות 🔒"` and log via `log_action` with `action='permission_denied'`
    - Before create task (`"משימה חדשה"` / `"new task"`): call `check_permission(db, phone, 'tasks', 'write')`, on denial return `"אין לך הרשאה ליצור משימות 🔒"` and log
    - Before complete task (`"סיום משימה"` / `"done"`): call `check_permission(db, phone, 'tasks', 'write')`, on denial return `"אין לך הרשאה לעדכן משימות 🔒"` and log
    - Before store document (media message): call `check_permission(db, phone, 'documents', 'write')`, on denial return `"אין לך הרשאה להעלות מסמכים 🔒"` and log
    - On denial, save conversation via `_save_conversation` before returning
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [x] 7. Create Mac Mini setup script
  - [x] 7.1 Create `fortress/scripts/setup_mac_mini.sh`
    - Use `set -euo pipefail` after shebang
    - Check Docker is running (`docker info`), exit 1 with ❌ if not
    - Check `docker compose version` available, exit 1 with ❌ if not
    - If `.env` missing, create from `.env.example` and prompt for DB password or use default; if exists, print ✅ skip
    - Create `~/fortress_storage/documents` and `~/fortress_storage/backup` directories
    - Run `docker compose up -d`
    - Poll DB health via `docker compose exec db pg_isready` with retries (~30 × 2s), exit 1 with ❌ on timeout
    - Apply migrations via `docker compose exec db psql` against each migration file
    - If `scripts/seed_family.sh` exists, execute it; otherwise print ⚠️ warning
    - Check API health at `http://localhost:8000/health`, report ✅ or ❌
    - Check WAHA status at `http://localhost:3000/api/sessions`, report ✅ or ❌
    - Print summary with next steps
    - Idempotent — safe to re-run
    - Print ✅/❌ status at each step
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 3.12, 3.13, 3.14, 3.15, 3.16, 3.17, 3.18_

- [x] 8. Add permission tests to test_message_handler.py
  - [ ]* 8.1 Add `test_child_can_read_tasks` to `fortress/tests/test_message_handler.py`
    - Mock member with role `child`, patch `check_permission` → `True`, mock `list_tasks`
    - Assert task list is returned successfully
    - _Requirements: 8.6_

  - [ ]* 8.2 Add `test_child_cannot_upload_document` to `fortress/tests/test_message_handler.py`
    - Mock member with role `child`, patch `check_permission` → `False`
    - Assert response contains `"🔒"`, assert `log_action` called with `action='permission_denied'`
    - _Requirements: 8.7_

  - [ ]* 8.3 Add `test_grandparent_cannot_create_task` to `fortress/tests/test_message_handler.py`
    - Mock member with role `grandparent`, patch `check_permission` → `False`
    - Assert response contains `"🔒"`, assert `log_action` called with `action='permission_denied'`
    - _Requirements: 8.8_

  - [ ]* 8.4 Add `test_parent_can_do_all_operations` to `fortress/tests/test_message_handler.py`
    - Mock member with role `parent`, patch `check_permission` → `True`
    - Assert all operations succeed (list tasks, create task, complete task, document upload)
    - Do NOT modify any existing test functions
    - _Requirements: 8.9, 9.2, 9.3_

- [x] 9. Create setup documentation
  - [x] 9.1 Create `fortress/docs/setup.md`
    - Prerequisites section: Docker Desktop, git, curl
    - Quick Setup section referencing `setup_mac_mini.sh`
    - WhatsApp Setup section: WAHA dashboard, QR code scanning
    - Verification section: health check commands, DB connectivity
    - Troubleshooting section: Docker not running, DB connection failures, WAHA session issues
    - Backup section: backup script usage, recommended locations
    - No real personal data — placeholder values only
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

- [x] 10. Update README
  - [x] 10.1 Update `fortress/README.md`
    - Add Deployment section referencing `setup_mac_mini.sh` and `docs/setup.md`
    - Add First-Time Setup subsection with essential commands
    - Update Current Status to reflect Phase 3.5
    - Retain all existing content sections
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [x] 11. Final checkpoint — Run ALL tests
  - Run the full test suite: all 48 existing tests + new permission tests must pass
  - Verify no existing test files were modified (only new functions appended to `test_message_handler.py`)
  - Ensure all tests pass, ask the user if questions arise.
  - _Requirements: 9.1, 9.2, 9.3_

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- The design uses Python — all code tasks target the existing Python/FastAPI codebase
- Existing tests pass without modification because `check_permission` called on a `MagicMock(spec=Session)` DB returns truthy values by default
- No property-based tests (Hypothesis) are included per user request — unit tests only
- Each task references specific requirements for traceability
