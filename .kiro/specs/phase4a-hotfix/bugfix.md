# Bugfix Requirements Document

## Introduction

Phase 4A is a minimal hotfix addressing six operational bugs in the Fortress 2.0 WhatsApp bot deployment. These fixes target: hardcoded API keys in the WhatsApp client, missing WAHA configuration in Docker Compose, missing `WAHA_API_KEY` in application config, missing `schema_migrations` table auto-creation, lack of structured logging in core services, and an incomplete `.env.example`. No model changes, prompt changes, task extraction logic, health endpoint, documentation, or setup script changes are included — those are deferred to Phase 4B (Bedrock migration).

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the WhatsApp client sends a message THEN the system sends a hardcoded `X-Api-Key` header value (`25c6dd6765b6446da432f32d2353d5f5`) regardless of the deployment environment, leaking a secret in source code and breaking any environment with a different WAHA API key.

1.2 WHEN the fortress service starts via Docker Compose THEN the system does not pass `WAHA_API_KEY` to the fortress container, so the application cannot read the configured API key from the environment.

1.3 WHEN the waha service starts via Docker Compose THEN the system does not pass `WAHA_DASHBOARD_USERNAME`, `WAHA_DASHBOARD_PASSWORD`, or `WHATSAPP_API_KEY` environment variables, leaving the WAHA dashboard unsecured and API key authentication disabled.

1.4 WHEN `src/config.py` is loaded THEN the system does not define a `WAHA_API_KEY` configuration variable, so there is no way for application code to read the WAHA API key from the environment.

1.5 WHEN `scripts/apply_migrations.sh` runs against a fresh database THEN the system attempts to query `schema_migrations` before creating it, causing the migration script to fail on first run (the table creation already exists in the current script but this documents the requirement for it to remain).

1.6 WHEN the intent detector classifies a message THEN the system does not log the detected intent, detection method, or message preview, making production debugging difficult.

1.7 WHEN the model router processes a message THEN the system does not log routing decisions, permission checks, or LLM prompt/response details, making it hard to trace message flow.

1.8 WHEN the LLM client sends a request to Ollama THEN the system does not log request details, response timing, or structured error information, making performance monitoring impossible.

1.9 WHEN a developer reads `.env.example` THEN the file does not include `WAHA_API_KEY`, `WAHA_DASHBOARD_USERNAME`, or `WAHA_DASHBOARD_PASSWORD` entries, and has formatting inconsistencies, causing confusion during environment setup.

### Expected Behavior (Correct)

2.1 WHEN the WhatsApp client sends a message AND `WAHA_API_KEY` is set to a non-empty value THEN the system SHALL read the key from `config.WAHA_API_KEY` and send it as the `X-Api-Key` header.

2.2 WHEN the WhatsApp client sends a message AND `WAHA_API_KEY` is empty or unset THEN the system SHALL NOT include the `X-Api-Key` header in the request.

2.3 WHEN the fortress service starts via Docker Compose THEN the system SHALL pass `WAHA_API_KEY=${WAHA_API_KEY:-}` as an environment variable to the fortress container.

2.4 WHEN the waha service starts via Docker Compose THEN the system SHALL pass `WAHA_DASHBOARD_USERNAME=${WAHA_DASHBOARD_USERNAME:-admin}`, `WAHA_DASHBOARD_PASSWORD=${WAHA_DASHBOARD_PASSWORD:-fortress}`, and `WHATSAPP_API_KEY=${WAHA_API_KEY:-}` as environment variables.

2.5 WHEN `src/config.py` is loaded THEN the system SHALL define `WAHA_API_KEY: str = os.getenv("WAHA_API_KEY", "")` so application code can read the WAHA API key.

2.6 WHEN `scripts/apply_migrations.sh` runs THEN the system SHALL create the `schema_migrations` table with `CREATE TABLE IF NOT EXISTS` before iterating migration files, ensuring first-run success.

2.7 WHEN the intent detector classifies a message THEN the system SHALL log: `Intent: {intent} | method: {method} | msg: {message[:50]}` at INFO level.

2.8 WHEN the model router processes a message THEN the system SHALL log routing decisions, permission check results, and LLM prompt/response summaries at INFO level.

2.9 WHEN the LLM client sends a request THEN the system SHALL log request details and response timing at INFO level, and errors at ERROR level with structured context.

2.10 WHEN a developer reads `.env.example` THEN the file SHALL contain all required variables: `DB_PASSWORD`, `STORAGE_PATH`, `LOG_LEVEL`, `WAHA_API_URL`, `WAHA_API_KEY`, `WAHA_DASHBOARD_USERNAME`, `WAHA_DASHBOARD_PASSWORD`, `ADMIN_PHONE`, `OLLAMA_API_URL`, `OLLAMA_MODEL` with correct defaults.

### Unchanged Behavior (Regression Prevention)

3.1 WHEN the WhatsApp client sends a message with valid phone and text THEN the system SHALL CONTINUE TO deliver the message via WAHA `/api/sendText` endpoint and return True on success.

3.2 WHEN the WhatsApp client encounters a network error THEN the system SHALL CONTINUE TO catch the exception, log it, and return False without raising.

3.3 WHEN the intent detector receives a message with media THEN the system SHALL CONTINUE TO return `upload_document` intent.

3.4 WHEN the intent detector receives a keyword-matched message THEN the system SHALL CONTINUE TO return the correct intent via keyword matching before LLM fallback.

3.5 WHEN the model router receives a message for an intent requiring permissions THEN the system SHALL CONTINUE TO check permissions and deny access when unauthorized.

3.6 WHEN the LLM client calls Ollama and receives a valid response THEN the system SHALL CONTINUE TO return the response text.

3.7 WHEN the LLM client encounters a timeout or connection error THEN the system SHALL CONTINUE TO return the Hebrew fallback message.

3.8 WHEN `apply_migrations.sh` runs and a migration has already been applied THEN the system SHALL CONTINUE TO skip it and report "SKIP".

3.9 WHEN all 87 existing tests are run THEN the system SHALL CONTINUE TO pass without modification (except adding new WhatsApp client API key tests).
