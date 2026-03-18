# Requirements Document

## Introduction

Fortress 2.0 Phase 3.5 prepares the system for deployment on a Mac Mini M4. This phase adds a system account migration, a seed data template, a one-touch setup script, Docker Compose volume mount updates for local storage, gitignore hardening, setup documentation, README updates, and permission enforcement in the message handler. Existing Python source files are modified only to add permission checks in the message handler. All 48 existing tests must continue to pass; new permission-denial tests are added.

## Glossary

- **Fortress**: The FastAPI-based family intelligence system running via Docker Compose (PostgreSQL 16 + FastAPI + WAHA).
- **Setup_Script**: The `scripts/setup_mac_mini.sh` bash script that performs one-time deployment setup on a Mac Mini.
- **Migration_Runner**: The `scripts/apply_migrations.sh` bash script that applies SQL migrations in order and tracks state in `schema_migrations`.
- **Seed_Template**: The `scripts/seed_family.sh.template` file that operators copy, fill with real phone numbers, and execute to populate family members.
- **System_Account_Migration**: The `migrations/003_system_account.sql` file that inserts a system-level family member for automated operations.
- **Docker_Compose**: The `docker-compose.yml` file defining the three-service stack (db, fortress, waha).
- **Env_Example**: The `.env.example` file containing default environment variable values.
- **Gitignore**: The `.gitignore` file at the repository root controlling which files are excluded from version control.
- **Setup_Guide**: The `docs/setup.md` deployment documentation for Mac Mini operators.
- **README**: The `README.md` file at the fortress project root.
- **Message_Handler**: The `src/services/message_handler.py` module that processes incoming WhatsApp messages and dispatches to task, document, and conversation services.
- **Permission_Check**: A call to `check_permission(db, phone, resource_type, access_type)` in the Auth_Service that returns True/False for a given family member's access to a resource.

## Requirements

### Requirement 1: System Account Migration

**User Story:** As an operator, I want a database migration that creates a system account for automated operations, so that audit trails and automated tasks have a consistent actor identity.

#### Acceptance Criteria

1. WHEN the System_Account_Migration is applied, THE Migration_Runner SHALL insert a family member row with name 'Fortress System', phone '0000000000', role 'other', and is_active true.
2. THE System_Account_Migration SHALL use a fixed UUID as the primary key for the system account row.
3. THE System_Account_Migration SHALL wrap all statements in a BEGIN/COMMIT transaction block.
4. THE System_Account_Migration SHALL use ON CONFLICT (phone) DO NOTHING to ensure idempotent execution.
5. WHEN the System_Account_Migration is applied multiple times, THE Migration_Runner SHALL produce the same database state as a single application.

### Requirement 2: Seed Script Template

**User Story:** As an operator, I want a template seed script with placeholder data, so that I can copy it, fill in real phone numbers, and populate family members without committing personal data to version control.

#### Acceptance Criteria

1. THE Seed_Template SHALL contain header comments explaining the three-step process: copy to seed_family.sh, edit phone numbers, run the script.
2. THE Seed_Template SHALL include a comment noting that seed_family.sh is gitignored.
3. THE Seed_Template SHALL include a comment specifying the phone format as Israeli international without the + prefix (e.g., 972501234567).
4. THE Seed_Template SHALL use `set -euo pipefail` as the first executable line after the shebang.
5. THE Seed_Template SHALL define a DB_URL variable with a default PostgreSQL connection string for the fortress database.
6. THE Seed_Template SHALL contain INSERT INTO family_members statements with placeholder names and phone numbers.
7. THE Seed_Template SHALL use ON CONFLICT (phone) DO UPDATE SET to make each insert idempotent.
8. THE Seed_Template SHALL include a summary SELECT query at the end that displays the current family members.
9. THE Seed_Template SHALL be valid bash that executes without error once placeholder phone numbers are replaced with real values.
10. THE Seed_Template SHALL contain no real personal phone numbers or names — only clearly marked placeholder values.

### Requirement 3: Mac Mini Setup Script

**User Story:** As an operator, I want a single setup script that configures and starts Fortress on a Mac Mini, so that deployment is repeatable and requires minimal manual steps.

#### Acceptance Criteria

1. THE Setup_Script SHALL use `set -euo pipefail` as the first executable line after the shebang.
2. WHEN Docker is not installed or not running, THE Setup_Script SHALL print an error message with ❌ and exit with a non-zero code.
3. WHEN `docker compose` is not available, THE Setup_Script SHALL print an error message with ❌ and exit with a non-zero code.
4. WHEN .env does not exist, THE Setup_Script SHALL create .env from .env.example and prompt the operator for a database password or use the default value.
5. WHEN .env already exists, THE Setup_Script SHALL skip .env creation and print a status message with ✅.
6. THE Setup_Script SHALL create the directory ~/fortress_storage/documents if the directory does not exist.
7. THE Setup_Script SHALL create the directory ~/fortress_storage/backup if the directory does not exist.
8. THE Setup_Script SHALL run `docker compose up -d` to start all services.
9. WHEN the database container is started, THE Setup_Script SHALL poll the database health status with retries until the database is healthy or a timeout is reached.
10. IF the database does not become healthy within the retry limit, THEN THE Setup_Script SHALL print an error message with ❌ and exit with a non-zero code.
11. WHEN the database is healthy, THE Setup_Script SHALL apply all SQL migrations by executing the migration files against the database.
12. WHEN scripts/seed_family.sh exists, THE Setup_Script SHALL execute the seed script.
13. WHEN scripts/seed_family.sh does not exist, THE Setup_Script SHALL print a warning message advising the operator to create the seed script from the template.
14. THE Setup_Script SHALL check the API health endpoint at http://localhost:8000/health and report the result with ✅ or ❌.
15. THE Setup_Script SHALL check the WAHA status endpoint at http://localhost:3000/api/sessions and report the result with ✅ or ❌.
16. THE Setup_Script SHALL print a summary with next steps after all checks complete.
17. THE Setup_Script SHALL be idempotent — running the script multiple times shall produce the same result as running it once.
18. THE Setup_Script SHALL print clear status messages prefixed with ✅ for success and ❌ for failure at each step.

### Requirement 4: Docker Compose Volume Mounts for Local Storage

**User Story:** As an operator, I want the fortress app container to mount a configurable local path for document storage, so that documents persist on the host filesystem and are accessible for backup.

#### Acceptance Criteria

1. THE Docker_Compose SHALL configure the fortress app service to mount `${STORAGE_PATH:-./storage}:/data/documents` as a bind mount volume.
2. THE Env_Example SHALL include a STORAGE_PATH variable with a default value of `./storage`.
3. THE Fortress project SHALL contain a `storage/.gitkeep` file so the storage directory is tracked in version control.
4. THE Gitignore SHALL include rules to ignore all files under storage/ except storage/.gitkeep.
5. WHEN the STORAGE_PATH environment variable is not set, THE Docker_Compose SHALL default to `./storage` as the local mount path.

### Requirement 5: Gitignore Updates

**User Story:** As a developer, I want the .gitignore to exclude personal data files, environment files, storage artifacts, and Python cache files, so that sensitive and generated files are not committed to version control.

#### Acceptance Criteria

1. THE Gitignore SHALL include an entry to ignore `fortress/scripts/seed_family.sh` to prevent committing personal data.
2. THE Gitignore SHALL include an entry to ignore `fortress/.env` to prevent committing environment secrets.
3. THE Gitignore SHALL include entries to ignore `fortress/storage/*` with an exception for `fortress/storage/.gitkeep`.
4. THE Gitignore SHALL retain all existing ignore rules without modification.

### Requirement 6: Setup Documentation

**User Story:** As an operator, I want a deployment guide for the Mac Mini, so that I can follow step-by-step instructions to set up Fortress from scratch.

#### Acceptance Criteria

1. THE Setup_Guide SHALL include a prerequisites section listing required software (Docker Desktop, git, curl).
2. THE Setup_Guide SHALL include a quick setup section referencing the setup_mac_mini.sh script.
3. THE Setup_Guide SHALL include a WhatsApp setup section with instructions for connecting via WAHA dashboard and QR code scanning.
4. THE Setup_Guide SHALL include a verification section with commands to check API health and database connectivity.
5. THE Setup_Guide SHALL include a troubleshooting section covering common issues (Docker not running, database connection failures, WAHA session issues).
6. THE Setup_Guide SHALL include a backup section describing how to use the backup script and recommended backup locations.
7. THE Setup_Guide SHALL contain no real personal data — only placeholder values where examples are needed.

### Requirement 7: README Updates

**User Story:** As a developer, I want the README to reflect the current deployment capabilities, so that new contributors understand how to deploy Fortress.

#### Acceptance Criteria

1. THE README SHALL include a deployment section referencing the setup_mac_mini.sh script and docs/setup.md guide.
2. THE README SHALL include a first-time setup subsection with the essential commands to get Fortress running.
3. THE README SHALL reflect Phase 3.5 status in the current status section.
4. THE README SHALL retain all existing content sections without removing information.

### Requirement 8: Permission Checks in Message Handler

**User Story:** As an operator, I want the message handler to enforce role-based permissions before returning task or document information, so that family members only access resources their role allows.

#### Acceptance Criteria

1. BEFORE returning a task list (keywords "משימות" or "tasks"), THE Message_Handler SHALL call check_permission(db, phone, 'tasks', 'read') and IF the result is False, SHALL return "אין לך הרשאה לצפות במשימות 🔒".
2. BEFORE creating a task (keywords "משימה חדשה" or "new task"), THE Message_Handler SHALL call check_permission(db, phone, 'tasks', 'write') and IF the result is False, SHALL return "אין לך הרשאה ליצור משימות 🔒".
3. BEFORE completing a task (keywords "סיום משימה" or "done"), THE Message_Handler SHALL call check_permission(db, phone, 'tasks', 'write') and IF the result is False, SHALL return "אין לך הרשאה לעדכן משימות 🔒".
4. BEFORE storing a document (media message), THE Message_Handler SHALL call check_permission(db, phone, 'documents', 'write') and IF the result is False, SHALL return "אין לך הרשאה להעלות מסמכים 🔒".
5. WHEN a permission check fails, THE Message_Handler SHALL log the denial via the Audit_Service with action 'permission_denied', including the resource_type and attempted access type in the details.
6. THE test suite SHALL include a test verifying that a child role can read tasks (should succeed — child has tasks read permission).
7. THE test suite SHALL include a test verifying that a child role cannot upload documents via media message (should fail — child has documents read only).
8. THE test suite SHALL include a test verifying that a grandparent role cannot create a task (should fail — grandparent has tasks read only).
9. THE test suite SHALL include a test verifying that a parent role can perform all operations (task list, task create, task complete, document upload).

### Requirement 9: Backward Compatibility

**User Story:** As a developer, I want all existing tests to continue passing after deployment preparation changes, so that no regressions are introduced.

#### Acceptance Criteria

1. THE Fortress project SHALL pass all 48 existing tests without modification after all Phase 3.5 changes are applied.
2. THE Phase 3.5 changes SHALL NOT modify any existing test files under tests/.
3. THE new permission-denial tests SHALL be added as new test functions in test_message_handler.py without altering existing test functions.
