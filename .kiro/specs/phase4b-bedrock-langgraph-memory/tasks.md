# Implementation Plan: Phase 4B — Bedrock + LangGraph + Memory

## Overview

Transform Fortress from Ollama-only to a hybrid AI system: AWS Bedrock (Claude 3.5 Haiku/Sonnet) for Hebrew generation, Ollama demoted to intent-only, LangGraph StateGraph replacing model_router, and a three-tier memory system. Implementation follows the user's specified task order (4B.1 through 4B.15).

## Tasks

- [x] 1. Update requirements.txt with new dependencies
  - Add boto3==1.35.0, langchain==0.3.0, langchain-aws==0.2.0, langchain-community==0.3.0, langgraph==0.2.0
  - Preserve all existing dependencies unchanged
  - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6_

- [x] 2. Update config.py with AWS and phone settings
  - Add `AWS_REGION` (default "us-east-1"), `AWS_PROFILE` (default "fortress"), `BEDROCK_HAIKU_MODEL`, `BEDROCK_SONNET_MODEL`, and `SYSTEM_PHONE` variables
  - All variables read from environment with `os.getenv` and sensible defaults
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [ ] 3. Create BedrockClient service
  - [x] 3.1 Create `fortress/src/services/bedrock_client.py`
    - Implement `BedrockClient` class with `__init__`, async `generate`, and async `is_available` methods
    - Use `boto3.Session(profile_name=profile).client("bedrock-runtime", region_name=region)` for AWS access
    - `generate` accepts prompt, system_prompt, and model selector ("haiku"/"sonnet"), maps to config model IDs
    - 30-second timeout via `botocore.config.Config(read_timeout=30)`
    - Return `HEBREW_FALLBACK` on any exception (timeout, credentials, throttling, etc.)
    - Log each request with model name, prompt length, and response time
    - `is_available` returns `(bool, str | None)` tuple
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10_

  - [ ]* 3.2 Write unit tests for BedrockClient (`fortress/tests/test_bedrock_client.py`)
    - Test generate success with mocked boto3 invoke_model
    - Test generate returns HEBREW_FALLBACK on timeout
    - Test generate returns HEBREW_FALLBACK on ClientError
    - Test generate returns HEBREW_FALLBACK on NoCredentialsError
    - Test model selector maps "haiku" and "sonnet" to correct model IDs
    - Test is_available returns (True, model_name) when reachable
    - Test is_available returns (False, None) when unreachable
    - _Requirements: 12.1, 12.2, 12.7_

- [x] 4. Fix echo prevention in WhatsApp router
  - In `fortress/src/routers/whatsapp.py`, replace `if phone == ADMIN_PHONE` echo check with `if payload.get("fromMe", False)` check
  - Remove the `ADMIN_PHONE` import if no longer needed in this file
  - _Requirements: 3.1, 3.2, 3.3_

- [x] 5. Create migration 004_memories.sql
  - Create `fortress/migrations/004_memories.sql`
  - Create `memories` table with all columns, CHECK constraints on memory_type and category
  - Create `memory_exclusions` table with all columns, CHECK constraint on exclusion_type
  - Insert default exclusion patterns (credit card, password, PIN, ID number, etc. in Hebrew and English, plus regex patterns)
  - Create all indexes: idx_memories_member, idx_memories_type, idx_memories_category, idx_memories_expires, idx_memories_active, idx_exclusions_active, idx_exclusions_type
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

- [x] 6. Add Memory and MemoryExclusion ORM models
  - Add `Memory` and `MemoryExclusion` classes to `fortress/src/models/schema.py` using SQLAlchemy 2.0 mapped_column style
  - Add `memories` reverse relationship to `FamilyMember`
  - Memory model: id, family_member_id (FK), content, category, memory_type, expires_at, source, confidence, last_accessed_at, access_count, is_active, memory_metadata (JSONB), created_at
  - MemoryExclusion model: id, pattern, description, exclusion_type, family_member_id (nullable FK), is_active, created_at
  - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [ ] 7. Create MemoryService
  - [x] 7.1 Create `fortress/src/services/memory_service.py`
    - Implement `save_memory(db, family_member_id, content, category, memory_type, source, confidence, metadata)` → `Memory | None`
    - Implement `load_memories(db, family_member_id, limit)` → `list[Memory]` with active/non-expired filtering, ordering, access tracking
    - Implement `cleanup_expired(db)` → `int` deleting past-due memories
    - Implement `extract_memories_from_message(db, family_member_id, message_in, message_out, bedrock)` → `list[Memory]` using Bedrock for extraction
    - Implement `check_exclusion(db, content, family_member_id)` → `bool` with keyword (case-insensitive substring) and regex matching
    - Expiration logic: short=7d, medium=90d, long=365d, permanent=None
    - Handle invalid regex patterns gracefully (log warning, skip)
    - Handle LLM extraction returning invalid JSON (log warning, return empty list)
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10_

  - [ ]* 7.2 Write unit tests for MemoryService (`fortress/tests/test_memory_service.py`)
    - Test save_memory creates record with correct expiration for each memory_type
    - Test save_memory returns None when content matches keyword exclusion
    - Test save_memory returns None when content matches regex exclusion
    - Test load_memories returns only active, non-expired memories in correct order
    - Test load_memories updates last_accessed_at and increments access_count
    - Test cleanup_expired removes past-due memories and leaves valid ones
    - Test extract_memories_from_message with mocked Bedrock response
    - Test check_exclusion with case-insensitive keyword matching
    - Test check_exclusion with regex matching
    - Test check_exclusion handles invalid regex gracefully
    - _Requirements: 12.3, 12.4, 12.5_

- [x] 8. Update system_prompts.py with Bedrock prompts
  - Add `MEMORY_EXTRACTOR` prompt: instructs Claude to extract facts from conversation, return JSON array of `{content, memory_type, category, confidence}`
  - Add `TASK_EXTRACTOR_BEDROCK` prompt: Hebrew-aware task extraction returning `{title, due_date, category, priority}` JSON
  - Existing prompts (FORTRESS_BASE, INTENT_CLASSIFIER, TASK_EXTRACTOR, TASK_RESPONDER) remain unchanged
  - _Requirements: 9.1, 9.2, 9.3, 9.4_

- [x] 9. Checkpoint — Verify foundation components
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Create WorkflowEngine with LangGraph
  - [x] 10.1 Create `fortress/src/services/workflow_engine.py`
    - Define `WorkflowState` TypedDict with: db, member, phone, message_text, has_media, media_file_path, intent, permission_granted, memories, response, error
    - Implement `intent_node`: calls `detect_intent` with `OllamaClient`
    - Implement `permission_node`: calls `check_permission`, sets denial message if denied
    - Implement `memory_load_node`: calls `load_memories` from MemoryService
    - Implement `action_node`: dispatches to handler based on intent, uses BedrockClient (haiku for simple intents, sonnet for ask_question)
    - Implement `response_node`: passes through or sets denial message
    - Implement `memory_save_node`: calls `extract_memories_from_message`
    - Implement `conversation_save_node`: saves Conversation record to DB
    - Build LangGraph StateGraph with conditional edge from permission_node (denied → response_node, granted → memory_load_node)
    - Expose `run_workflow(db, member, phone, message_text, has_media, media_file_path)` → `str`
    - Wrap entire graph execution in try/except, return HEBREW_FALLBACK on any error
    - Port all handler logic from model_router.py (list_tasks, create_task, complete_task, greeting, upload_document, list_documents, ask_question, unknown)
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 7.10, 7.11_

  - [ ]* 10.2 Write unit tests for WorkflowEngine (`fortress/tests/test_workflow_engine.py`)
    - Test run_workflow greeting flow returns Bedrock-generated response
    - Test run_workflow list_tasks flow fetches tasks and formats via Bedrock
    - Test run_workflow create_task flow extracts details and creates task
    - Test run_workflow permission_denied flow returns 🔒 message
    - Test run_workflow ask_question uses Sonnet model
    - Test run_workflow exception returns HEBREW_FALLBACK
    - Test conversation is saved with detected intent
    - All tests mock OllamaClient, BedrockClient, and DB
    - _Requirements: 12.6_

- [x] 11. Update message_handler.py to use WorkflowEngine
  - Replace `from src.services.model_router import route_message` with `from src.services.workflow_engine import run_workflow`
  - Replace `route_message(...)` call with `run_workflow(...)` call
  - Preserve existing auth logic (unknown phone rejection, inactive member rejection)
  - _Requirements: 8.1, 8.2, 8.3_

- [x] 12. Checkpoint — Verify workflow integration
  - Ensure all tests pass, ask the user if questions arise.
  - Update existing test_message_handler.py mocks: change `route_message` mock target to `run_workflow`
  - Verify existing test_model_router.py tests still pass (model_router.py is kept as-is, not deleted)
  - _Requirements: 12.8, 12.9_

- [x] 13. Update docker-compose.yml
  - Add `~/.aws:/root/.aws:ro` volume mount to fortress service
  - Add `AWS_REGION`, `AWS_PROFILE`, `SYSTEM_PHONE` environment variables to fortress service
  - Existing services (db, ollama, waha) remain unchanged
  - _Requirements: 10.1, 10.2, 10.3, 10.4_

- [x] 14. Update .env.example
  - Add entries for `AWS_REGION`, `AWS_PROFILE`, `SYSTEM_PHONE`, `BEDROCK_HAIKU_MODEL`, `BEDROCK_SONNET_MODEL` with descriptive comments
  - Preserve all existing entries
  - _Requirements: 2.6_

- [x] 15. Update health endpoint
  - Add Bedrock connectivity check to `fortress/src/routers/health.py`
  - Add "bedrock" field ("connected"/"disconnected") and "bedrock_model" field to health response
  - Preserve existing ollama and database status fields
  - _Requirements: 11.1, 11.2, 11.3_

  - [ ]* 15.1 Update health endpoint tests (`fortress/tests/test_health.py`)
    - Add mock for BedrockClient.is_available in all existing health tests
    - Add test for bedrock connected status
    - Add test for bedrock disconnected status
    - _Requirements: 12.8_

- [ ] 16. Create remaining unit tests
  - [ ]* 16.1 Create config tests (`fortress/tests/test_config.py`)
    - Test AWS_REGION, AWS_PROFILE, BEDROCK_HAIKU_MODEL, BEDROCK_SONNET_MODEL, SYSTEM_PHONE exist with correct defaults
    - _Requirements: 12.8_

- [x] 17. Update documentation
  - [x] 17.1 Update `fortress/README.md`
    - Describe hybrid AI architecture (Bedrock for Hebrew, Ollama for intent)
    - Update project structure to include new files (bedrock_client.py, memory_service.py, workflow_engine.py)
    - _Requirements: 13.1_

  - [x] 17.2 Update `fortress/docs/architecture.md`
    - Add updated message flow diagram showing LangGraph workflow nodes
    - Document MemoryService and three-tier memory model
    - Update service layer descriptions
    - _Requirements: 13.2, 13.3_

  - [x] 17.3 Update `fortress/docs/setup.md`
    - Add AWS credential configuration steps (IAM user, profile setup, Bedrock model access)
    - Document SYSTEM_PHONE vs ADMIN_PHONE distinction
    - _Requirements: 13.4, 13.5_

- [x] 18. Final checkpoint — Full regression
  - Ensure all tests pass (existing 89 + new tests), ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- model_router.py is kept as-is (not deleted) to preserve existing test_model_router.py tests
- All boto3/AWS calls are mocked in tests — no real Bedrock invocations during testing
- Unit tests only — no Hypothesis/property-based tests per user instruction
