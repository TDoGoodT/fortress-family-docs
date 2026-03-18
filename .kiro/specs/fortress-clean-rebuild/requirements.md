# Requirements Document

## Introduction

Fortress 2.0 is a clean rebuild of the Fortress family intelligence system. The existing legacy codebase is archived into `_legacy/`, and a new, simpler, value-first architecture is built from scratch using FastAPI, PostgreSQL 16, and Docker. The system runs on a Mac Mini M4 (24GB RAM, 1TB SSD) and manages household documents, finances, and family queries via WhatsApp. This rebuild prioritizes simplicity, working code, and a clear project structure over the complex event-sourced architecture of the legacy system.

## Glossary

- **Fortress**: The family intelligence system being rebuilt — a sovereign, local-first household knowledge infrastructure
- **Legacy_Code**: All existing files and folders in the repository (excluding `.git/` and `.gitignore`) that must be archived before the rebuild
- **Archive_Directory**: The `_legacy/` folder at the repo root where all legacy code is preserved
- **App_Service**: The FastAPI-based Python application that serves as the Fortress 2.0 backend
- **Database_Service**: The PostgreSQL 16 container running via Docker Compose
- **Migration_Runner**: A bash script that applies SQL migration files to the database in order, tracking which have been applied
- **WhatsApp_Webhook**: The HTTP endpoint that receives incoming WhatsApp messages for processing
- **Health_Endpoint**: The HTTP endpoint that reports the operational status of the App_Service
- **Auth_Service**: The service responsible for looking up family members by phone number and checking permissions
- **Audit_Service**: The service responsible for writing entries to the audit log
- **Document_Service**: The service responsible for document processing operations
- **Family_Member**: A person registered in the system with a phone number and family role (parent, child, grandparent, or other)
- **Permission**: A role-based access control record that maps a family role to read/write permissions on a resource type

## Requirements

### Requirement 1: Archive Legacy Code

**User Story:** As a developer, I want all existing code moved into an `_legacy/` folder, so that the repo root is clean for the new architecture without losing any historical code.

#### Acceptance Criteria

1. WHEN the archive operation is performed, THE Archive_Directory SHALL contain all files and folders that previously existed at the repo root, preserving the original folder structure
2. WHEN the archive operation is complete, THE repo root SHALL contain only `_legacy/`, `.git/`, and `.gitignore`
3. THE Archive_Directory SHALL preserve every file from the legacy codebase without deletion or modification

### Requirement 2: New Project Structure

**User Story:** As a developer, I want a well-organized project structure under `fortress/`, so that the codebase is easy to navigate and maintain.

#### Acceptance Criteria

1. THE Fortress project SHALL contain a `fortress/src/` directory with `main.py`, `config.py`, `database.py`, and sub-packages `models/`, `routers/`, `services/`, and `utils/`
2. THE Fortress project SHALL contain a `fortress/migrations/` directory for SQL migration files
3. THE Fortress project SHALL contain a `fortress/scripts/` directory for operational scripts
4. THE Fortress project SHALL contain a `fortress/tests/` directory for test files
5. THE Fortress project SHALL contain a `fortress/docs/` directory with an `architecture.md` overview
6. THE Fortress project SHALL contain `docker-compose.yml`, `.env.example`, `README.md`, `requirements.txt`, and a `Dockerfile` at the `fortress/` root
7. THE Fortress project SHALL NOT import or reference any code from the Archive_Directory

### Requirement 3: Docker Compose Configuration

**User Story:** As a developer, I want a Docker Compose setup with PostgreSQL and the app service, so that I can run the entire system with a single command.

#### Acceptance Criteria

1. THE docker-compose.yml SHALL define a Database_Service using the `postgres:16-alpine` image
2. THE docker-compose.yml SHALL define an App_Service that builds from the local Dockerfile
3. THE App_Service SHALL depend on the Database_Service and wait for database readiness before starting
4. THE Database_Service SHALL persist data using a named Docker volume
5. THE docker-compose.yml SHALL load environment variables from a `.env` file

### Requirement 4: Database Schema

**User Story:** As a developer, I want a well-defined initial database schema, so that the core data model is established from day one.

#### Acceptance Criteria

1. THE 001_initial_schema.sql migration SHALL create a `family_members` table with columns for id (UUID primary key, default gen_random_uuid()), name (TEXT NOT NULL), phone (TEXT UNIQUE NOT NULL), role (TEXT NOT NULL, CHECK IN ('parent', 'child', 'grandparent', 'other')), is_active (BOOLEAN DEFAULT true), created_at (TIMESTAMPTZ DEFAULT now()), and updated_at (TIMESTAMPTZ DEFAULT now())
2. THE 001_initial_schema.sql migration SHALL create a `permissions` table with columns for id (UUID primary key, default gen_random_uuid()), role (TEXT NOT NULL), resource_type (TEXT NOT NULL), can_read (BOOLEAN DEFAULT false), can_write (BOOLEAN DEFAULT false), with a UNIQUE constraint on (role, resource_type)
3. THE 001_initial_schema.sql migration SHALL create a `documents` table with columns for id (UUID primary key, default gen_random_uuid()), uploaded_by (UUID FK to family_members), file_path (TEXT NOT NULL), original_filename (TEXT), doc_type (TEXT), vendor (TEXT), amount (NUMERIC), currency (TEXT DEFAULT 'ILS'), doc_date (DATE), description (TEXT), ai_summary (TEXT), raw_text (TEXT), source (TEXT NOT NULL, CHECK IN ('whatsapp', 'email', 'filesystem', 'manual')), metadata (JSONB DEFAULT '{}'), and created_at (TIMESTAMPTZ DEFAULT now())
4. THE 001_initial_schema.sql migration SHALL create a `transactions` table with columns for id (UUID primary key, default gen_random_uuid()), document_id (UUID FK to documents), category (TEXT), amount (NUMERIC NOT NULL), currency (TEXT DEFAULT 'ILS'), direction (TEXT NOT NULL, CHECK IN ('income', 'expense')), transaction_date (DATE), description (TEXT), and created_at (TIMESTAMPTZ DEFAULT now())
5. THE 001_initial_schema.sql migration SHALL create an `audit_log` table with columns for id (BIGSERIAL PRIMARY KEY), actor_id (UUID FK to family_members), action (TEXT NOT NULL), resource_type (TEXT), resource_id (UUID), details (JSONB DEFAULT '{}'), and created_at (TIMESTAMPTZ DEFAULT now())
6. THE 001_initial_schema.sql migration SHALL create a `conversations` table with columns for id (UUID primary key, default gen_random_uuid()), family_member_id (UUID FK to family_members), message_in (TEXT), message_out (TEXT), intent (TEXT), metadata (JSONB DEFAULT '{}'), and created_at (TIMESTAMPTZ DEFAULT now())
7. THE 001_initial_schema.sql migration SHALL insert default permissions: parent role with finance(read+write), documents(read+write), tasks(read+write); child role with finance(none), documents(read), tasks(read+write); grandparent role with finance(none), documents(read), tasks(read)
8. THE 001_initial_schema.sql migration SHALL create indexes on frequently queried columns including phone number, foreign keys, and timestamps

### Requirement 5: Environment Configuration

**User Story:** As a developer, I want a clear environment configuration template, so that I know which variables are required to run the system.

#### Acceptance Criteria

1. THE .env.example file SHALL define a `DB_PASSWORD` variable with a placeholder value
2. THE .env.example file SHALL define a `STORAGE_PATH` variable with a default local path
3. THE .env.example file SHALL define a `LOG_LEVEL` variable with a default value of `INFO`

### Requirement 6: Python Dependencies

**User Story:** As a developer, I want a pinned list of Python dependencies, so that the project environment is reproducible.

#### Acceptance Criteria

1. THE requirements.txt SHALL include fastapi, uvicorn, sqlalchemy, psycopg2-binary, python-dotenv, httpx, pydantic, pytest, and hypothesis
2. THE requirements.txt SHALL list each dependency on a separate line

### Requirement 7: FastAPI Application

**User Story:** As a developer, I want a minimal FastAPI application with health check and webhook endpoints, so that the system has a working HTTP interface from the start.

#### Acceptance Criteria

1. WHEN a GET request is sent to `/health`, THE App_Service SHALL return a JSON response with status "ok" and a 200 HTTP status code
2. WHEN the App_Service starts, THE App_Service SHALL test the database connection and log the result
3. IF the database connection fails on startup, THEN THE App_Service SHALL log an error message and continue running
4. WHEN a POST request is sent to the WhatsApp webhook endpoint, THE App_Service SHALL accept the request and return a 200 HTTP status code
5. THE App_Service SHALL use uvicorn as the ASGI server on port 8000

### Requirement 8: Migration Runner Script

**User Story:** As a developer, I want a simple bash script to apply SQL migrations, so that database schema changes are tracked and applied in order.

#### Acceptance Criteria

1. WHEN the Migration_Runner is executed, THE Migration_Runner SHALL create a `schema_migrations` tracking table if it does not exist
2. WHEN the Migration_Runner encounters a `.sql` file that has not been applied, THE Migration_Runner SHALL execute the SQL file against the database
3. WHEN the Migration_Runner encounters a `.sql` file that has already been applied, THE Migration_Runner SHALL skip the file
4. THE Migration_Runner SHALL apply migration files in alphabetical order
5. WHEN a migration fails, THE Migration_Runner SHALL stop execution and report the error
6. THE Migration_Runner SHALL record each successfully applied migration filename and timestamp in the `schema_migrations` table

### Requirement 9: Dockerfile

**User Story:** As a developer, I want a Dockerfile for the app service, so that the application runs in a consistent containerized environment.

#### Acceptance Criteria

1. THE Dockerfile SHALL use `python:3.12-slim` as the base image
2. THE Dockerfile SHALL install Python dependencies from requirements.txt
3. THE Dockerfile SHALL copy the `src/` directory into the container
4. THE Dockerfile SHALL run uvicorn on port 8000 as the default command
5. THE Dockerfile SHALL expose port 8000

### Requirement 10: README Documentation

**User Story:** As a developer, I want a concise README, so that anyone opening the repo understands what Fortress is and how to run it.

#### Acceptance Criteria

1. THE README.md SHALL describe what Fortress is in a short summary
2. THE README.md SHALL include instructions for running the system using Docker Compose
3. THE README.md SHALL include instructions for applying database migrations
4. THE README.md SHALL include an overview of the project structure
5. THE README.md SHALL include a section describing the current status of the rebuild

### Requirement 11: Auth Service

**User Story:** As a developer, I want a phone-based authentication service, so that incoming WhatsApp messages can be mapped to family members with appropriate permissions.

#### Acceptance Criteria

1. WHEN a phone number is provided, THE Auth_Service SHALL look up the corresponding Family_Member record in the database
2. IF no Family_Member is found for the given phone number, THEN THE Auth_Service SHALL return a clear "not found" result
3. WHEN a Family_Member is found, THE Auth_Service SHALL retrieve the role-based Permission records matching the Family_Member's role (parent, child, grandparent, or other)
4. THE Auth_Service SHALL provide a method to check whether a Family_Member's role has can_read or can_write permission for a given resource type

### Requirement 12: Audit Logging

**User Story:** As a developer, I want an audit logging service, so that all significant actions in the system are recorded for accountability.

#### Acceptance Criteria

1. WHEN a significant action occurs, THE Audit_Service SHALL write a record to the audit_log table with the actor_id, action, resource_type, resource_id, and details
2. THE Audit_Service SHALL rely on BIGSERIAL for auto-incrementing audit log entry IDs
3. THE Audit_Service SHALL record the timestamp of each audit log entry automatically

### Requirement 13: Health Check Test

**User Story:** As a developer, I want a test for the health check endpoint, so that I can verify the API is responding correctly.

#### Acceptance Criteria

1. WHEN the health check test is executed, THE test SHALL send a GET request to `/health` and verify the response status is 200
2. WHEN the health check test is executed, THE test SHALL verify the response body contains status "ok"

### Requirement 14: Auth Service Test

**User Story:** As a developer, I want tests for the auth service, so that I can verify phone-based family member lookup works correctly.

#### Acceptance Criteria

1. WHEN the auth test is executed with a known phone number, THE test SHALL verify that the correct Family_Member is returned
2. WHEN the auth test is executed with an unknown phone number, THE test SHALL verify that a "not found" result is returned
