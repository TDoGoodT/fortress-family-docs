# Phase 4A Hotfix — Bugfix Design

## Overview

Six operational bugs block Fortress 2.0 deployment: a hardcoded WAHA API key in `whatsapp_client.py`, missing env passthrough in Docker Compose, missing `WAHA_API_KEY` in `config.py`, a migration script that can fail on first run, no structured logging in three core services, and an incomplete `.env.example`. This hotfix addresses all six with minimal, targeted changes. No model, prompt, intent logic, task extraction, health endpoint, or documentation changes.

## Glossary

- **Bug_Condition (C)**: The set of conditions across six files that cause deployment failures or operational blindness
- **Property (P)**: Correct behavior after fix — config-driven API keys, env passthrough, structured logging, clean `.env.example`
- **Preservation**: All 87 existing tests pass; message delivery, error handling, intent detection, permission checks, and LLM fallback remain unchanged
- **WAHA_API_KEY**: Environment variable for authenticating with the WAHA WhatsApp gateway
- **Structured logging**: INFO-level log lines with intent, method, timing, and message preview fields

## Bug Details

### Bug Condition

The bugs manifest across six files when the system is deployed to production. The WhatsApp client uses a hardcoded API key, Docker Compose doesn't pass WAHA credentials, `config.py` lacks the `WAHA_API_KEY` variable, the migration script can fail on fresh databases, core services produce no structured logs, and `.env.example` is incomplete.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type DeploymentContext
  OUTPUT: boolean

  RETURN (input.file == "whatsapp_client.py" AND hardcodedApiKeyPresent(input))
         OR (input.file == "docker-compose.yml" AND missingEnvPassthrough(input, "WAHA_API_KEY"))
         OR (input.file == "docker-compose.yml" AND missingWahaCredentials(input))
         OR (input.file == "config.py" AND NOT hasVariable(input, "WAHA_API_KEY"))
         OR (input.file == "apply_migrations.sh" AND freshDatabase(input))
         OR (input.file IN ["intent_detector.py", "model_router.py", "llm_client.py"] AND NOT hasStructuredLogging(input))
         OR (input.file == ".env.example" AND missingVariables(input))
END FUNCTION
```

### Examples

- `whatsapp_client.py` sends `X-Api-Key: 25c6dd6765b6446da432f32d2353d5f5` in every environment → should read from `config.WAHA_API_KEY`, omit header if empty
- `docker-compose.yml` fortress service has no `WAHA_API_KEY` env → should pass `WAHA_API_KEY=${WAHA_API_KEY:-}`
- `docker-compose.yml` waha service has no `WHATSAPP_API_KEY`, `WAHA_DASHBOARD_USERNAME`, `WAHA_DASHBOARD_PASSWORD` → should pass all three
- `config.py` has no `WAHA_API_KEY` variable → should define `WAHA_API_KEY: str = os.getenv("WAHA_API_KEY", "")`
- `apply_migrations.sh` queries `schema_migrations` before creating it on fresh DB → table creation must precede queries (already present in current code, requirement documents this must remain)
- `intent_detector.py` logs nothing on intent classification → should log intent, method, message preview
- `.env.example` missing `WAHA_API_KEY` entry, has formatting issues → should list all variables cleanly

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- `send_text_message` and `send_reply` deliver messages via WAHA `/api/sendText` and return True/False
- Network errors are caught, logged, and return False without raising
- Intent detection: media → `upload_document`, keyword match before LLM fallback, same keyword rules
- Model router: permission checks, handler dispatch table, conversation saving
- LLM client: Ollama `/api/generate` calls, timeout/connection error → Hebrew fallback
- Migration script: already-applied migrations are skipped
- All 87 existing tests pass without modification

**Scope:**
All inputs that do NOT involve the six bug conditions should be completely unaffected. This includes:
- Message content parsing and intent classification logic
- Task creation/completion/listing logic
- Health endpoint behavior
- System prompts and LLM model selection

## Hypothesized Root Cause

Based on the bug description, the root causes are straightforward:

1. **Hardcoded API Key**: Developer committed a development API key directly in `whatsapp_client.py` line 28/42 instead of reading from config
2. **Missing Docker Compose Env**: The `fortress` service environment block was written before `WAHA_API_KEY` was needed; the `waha` service block omits dashboard credentials and API key passthrough
3. **Missing Config Variable**: `config.py` was written before WAHA API key auth was implemented — the variable was never added
4. **Migration Script**: The `CREATE TABLE IF NOT EXISTS schema_migrations` already exists in the current script. The requirement documents that it must remain. No code change needed here.
5. **No Structured Logging**: The three services use `logger.error`/`logger.exception` for errors but have no INFO-level operational logging for normal flow
6. **Incomplete .env.example**: File was not updated when WAHA auth variables were introduced; has spacing inconsistencies

## Correctness Properties

Property 1: Bug Condition — API Key From Config

_For any_ call to `send_text_message` or `send_reply` where `config.WAHA_API_KEY` is set to a non-empty string, the function SHALL include `X-Api-Key: {config.WAHA_API_KEY}` in the request headers. Where `WAHA_API_KEY` is empty or unset, the function SHALL NOT include the `X-Api-Key` header.

**Validates: Requirements 2.1, 2.2**

Property 2: Preservation — Message Delivery Behavior

_For any_ call to `send_text_message` or `send_reply` with valid phone and text, the function SHALL continue to POST to WAHA `/api/sendText` with the correct payload structure and return True on 200/201, False on error, preserving all existing delivery and error-handling behavior.

**Validates: Requirements 3.1, 3.2**

Property 3: Bug Condition — Docker Compose Env Passthrough

_For any_ deployment using `docker-compose.yml`, the fortress service SHALL receive `WAHA_API_KEY` and the waha service SHALL receive `WHATSAPP_API_KEY`, `WAHA_DASHBOARD_USERNAME`, and `WAHA_DASHBOARD_PASSWORD` from the host environment.

**Validates: Requirements 2.3, 2.4**

Property 4: Bug Condition — Config Variable Exists

_For any_ import of `src.config`, the module SHALL export `WAHA_API_KEY` read from the `WAHA_API_KEY` environment variable with empty string default.

**Validates: Requirements 2.5**

Property 5: Bug Condition — Structured Logging

_For any_ message processed through intent detection, model routing, or LLM generation, the system SHALL emit INFO-level log lines with structured context (intent, method, timing, message preview).

**Validates: Requirements 2.7, 2.8, 2.9**

Property 6: Preservation — Intent Detection and Routing Logic

_For any_ message input, the intent detection keywords, LLM fallback logic, permission checks, handler dispatch, and LLM model/prompt selection SHALL remain identical to the pre-fix behavior.

**Validates: Requirements 3.3, 3.4, 3.5, 3.6, 3.7**

## Fix Implementation

### Changes Required

**File**: `fortress/src/config.py`

**Change**: Add `WAHA_API_KEY` variable
```python
WAHA_API_KEY: str = os.getenv("WAHA_API_KEY", "")
```

---

**File**: `fortress/src/services/whatsapp_client.py`

**Function**: `send_text_message`, `send_reply`

**Specific Changes**:
1. Import `WAHA_API_KEY` from `src.config`
2. Remove hardcoded `"25c6dd6765b6446da432f32d2353d5f5"` from both functions
3. Build headers conditionally: include `X-Api-Key` only when `WAHA_API_KEY` is non-empty
4. Pass the conditional headers dict to `client.post()`

---

**File**: `fortress/docker-compose.yml`

**Specific Changes**:
1. Add `WAHA_API_KEY: ${WAHA_API_KEY:-}` to fortress service environment
2. Add `WHATSAPP_API_KEY=${WAHA_API_KEY:-}` to waha service environment
3. Add `WAHA_DASHBOARD_USERNAME=${WAHA_DASHBOARD_USERNAME:-admin}` to waha service environment
4. Add `WAHA_DASHBOARD_PASSWORD=${WAHA_DASHBOARD_PASSWORD:-fortress}` to waha service environment

---

**File**: `fortress/scripts/apply_migrations.sh`

**Change**: No change needed — the `CREATE TABLE IF NOT EXISTS schema_migrations` statement already exists before the migration loop. Requirement 2.6 documents that this must remain.

---

**File**: `fortress/src/services/intent_detector.py`

**Function**: `detect_intent`

**Specific Changes**:
1. After keyword match: `logger.info("Intent: %s | method: keyword | msg: %s", intent, text[:50])`
2. After LLM fallback: `logger.info("Intent: %s | method: llm | msg: %s", intent, text[:50])`
3. After media check: `logger.info("Intent: upload_document | method: media | msg: %s", text[:50])`

---

**File**: `fortress/src/services/model_router.py`

**Function**: `route_message`

**Specific Changes**:
1. Log intent after detection: `logger.info("Routing: intent=%s phone=%s", intent, phone)`
2. Log permission denial when it occurs
3. Log handler dispatch

---

**File**: `fortress/src/services/llm_client.py`

**Function**: `OllamaClient.generate`

**Specific Changes**:
1. Log request: `logger.info("LLM request: model=%s prompt_len=%d", self.model, len(prompt))`
2. Log response timing: `logger.info("LLM response: model=%s time=%.2fs len=%d", self.model, elapsed, len(result))`
3. Keep existing error logging as-is

---

**File**: `fortress/.env.example`

**Specific Changes**: Clean up formatting, ensure all variables present with correct defaults:
```
DB_PASSWORD=fortress_dev
STORAGE_PATH=./storage
LOG_LEVEL=info
WAHA_API_URL=http://waha:3000
WAHA_API_KEY=
WAHA_DASHBOARD_USERNAME=admin
WAHA_DASHBOARD_PASSWORD=
ADMIN_PHONE=972542364393
OLLAMA_API_URL=http://ollama:11434
OLLAMA_MODEL=llama3.1:8b
```

## Testing Strategy

### Validation Approach

Two-phase: verify bugs exist on unfixed code, then verify fixes work and preserve existing behavior. All 87 existing tests must continue to pass. Two new tests are added for WhatsApp client API key behavior.

### Exploratory Bug Condition Checking

**Goal**: Confirm the hardcoded API key and missing config variable before fixing.

**Test Cases**:
1. **Hardcoded Key Test**: Inspect `whatsapp_client.py` source — confirm `25c6dd6765b6446da432f32d2353d5f5` is hardcoded (will fail on unfixed code)
2. **Missing Config Test**: Attempt `from src.config import WAHA_API_KEY` — confirm ImportError (will fail on unfixed code)
3. **Docker Compose Inspection**: Verify fortress service env block lacks `WAHA_API_KEY` (will fail on unfixed code)

**Expected Counterexamples**:
- API key is hardcoded string, not read from config
- `config.py` has no `WAHA_API_KEY` attribute

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed code produces expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := fixedFunction(input)
  ASSERT expectedBehavior(result)
END FOR
```

**New Tests (2 tests added to `test_whatsapp_client.py`)**:
1. `test_send_text_message_includes_api_key_when_set` — patch `WAHA_API_KEY` to a value, verify `X-Api-Key` header is sent
2. `test_send_text_message_omits_api_key_when_empty` — patch `WAHA_API_KEY` to empty string, verify no `X-Api-Key` header

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed code produces the same result as the original.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT originalFunction(input) = fixedFunction(input)
END FOR
```

**Test Cases**:
1. **Existing send_text_message tests**: 3 existing tests verify payload structure, success/failure returns
2. **Existing send_reply tests**: 1 existing test verifies reply_to payload
3. **All 87 existing tests**: Full test suite run confirms no regressions

### Unit Tests

- 2 new tests for WhatsApp client API key conditional header behavior
- 87 existing tests unchanged and passing

### Property-Based Tests

- Not required for this hotfix — the changes are config/logging only, well covered by unit tests

### Integration Tests

- Manual: deploy with Docker Compose, verify WAHA receives API key, verify structured logs appear in `docker logs fortress-app`
