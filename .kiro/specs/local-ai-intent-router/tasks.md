# Implementation Plan: Local AI + Intent Router

## Overview

Transform Fortress from keyword-matching to AI-powered intent detection by adding Ollama as a local LLM service, creating an intent detector with keyword + LLM fallback, a model router for intent-based dispatch, and a dedicated async LLM client. The existing message handler becomes a thin auth layer delegating to the new router. All 52 existing tests must continue to pass.

## Tasks

- [x] 1. Update configuration and environment
  - [x] 1.1 Add OLLAMA_API_URL and OLLAMA_MODEL to `src/config.py`
    - Add `OLLAMA_API_URL: str = os.getenv("OLLAMA_API_URL", "http://localhost:11434")`
    - Add `OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.1:8b")`
    - _Requirements: 3.1, 3.2_
  - [x] 1.2 Update `.env.example` with new Ollama variables
    - Add `OLLAMA_API_URL=http://ollama:11434` and `OLLAMA_MODEL=llama3.1:8b`
    - _Requirements: 1.4_

- [x] 2. Create system prompts module
  - [x] 2.1 Create `src/prompts/__init__.py` and `src/prompts/system_prompts.py`
    - Define `FORTRESS_BASE` prompt (Hebrew-speaking family assistant identity)
    - Define `INTENT_CLASSIFIER` prompt (classify messages into intent categories)
    - Define `TASK_EXTRACTOR` prompt (extract title, due_date, category from Hebrew text)
    - Define `TASK_RESPONDER` prompt (format tasks as WhatsApp-appropriate Hebrew)
    - Re-export all constants from `__init__.py`
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [x] 3. Create LLM client
  - [x] 3.1 Create `src/services/llm_client.py` with `OllamaClient` class
    - Implement `__init__` with config defaults for base_url and model
    - Implement `generate(prompt, system_prompt)` using `httpx.AsyncClient` with 30s timeout, POST to `/api/generate` with `stream=False`
    - Implement `is_available()` querying GET `/api/tags` and checking model presence
    - Return Hebrew fallback `"מצטער, לא הצלחתי לעבד את הבקשה. נסה שוב."` on timeout or connection error
    - Log all errors with full context
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_
  - [ ]* 3.2 Write unit tests for LLM client in `tests/test_llm_client.py`
    - Test correct HTTP payload sent to `/api/generate` (model, prompt, system, stream=False)
    - Test timeout error returns Hebrew fallback message
    - Test connection error returns Hebrew fallback message
    - Test `is_available` returns True when model is in tags list
    - Test `is_available` returns False when model is not in tags list
    - Test `is_available` returns False on connection error
    - _Requirements: 10.3_

- [x] 4. Checkpoint — Verify LLM client tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Create intent detector
  - [x] 5.1 Create `src/services/intent_detector.py`
    - Define `INTENTS` dict mapping all 8 intents to `"local"` tier
    - Implement `detect_intent(text, has_media, llm_client)` with keyword matching in priority order: has_media → upload_document, משימות/tasks → list_tasks, משימה חדשה:/new task: prefix → create_task, סיום משימה/done/בוצע → complete_task, שלום/היי/hello/בוקר טוב → greeting, מסמכים/documents → list_documents
    - LLM fallback when no keyword matches using INTENT_CLASSIFIER prompt
    - Return `"unknown"` on LLM failure
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9_
  - [ ]* 5.2 Write unit tests for intent detector in `tests/test_intent_detector.py`
    - Test media messages classify as `upload_document` regardless of text
    - Test each Hebrew keyword maps to correct intent
    - Test each English keyword maps to correct intent
    - Test `create_task` prefix matching (Hebrew and English)
    - Test LLM fallback is invoked when no keyword matches
    - Test LLM failure returns `unknown`
    - Test INTENTS dict contains all 8 required intents
    - _Requirements: 10.1_

- [x] 6. Create model router
  - [x] 6.1 Create `src/services/model_router.py` with `route_message` function
    - Accept db, member, phone, message_text, has_media, media_file_path
    - Detect intent via intent_detector
    - Check permissions per intent (tasks→read/write, documents→read/write)
    - Dispatch to handler per intent: list_tasks, create_task, complete_task, greeting, upload_document, list_documents, ask_question, unknown
    - Use LLM for task formatting (TASK_RESPONDER), task extraction (TASK_EXTRACTOR), greetings, and ask_question
    - Audit-log permission denials with `action="permission_denied"`
    - Save Conversation record for every message with detected intent
    - Return Hebrew `🔒` message on permission denial
    - Return Hebrew help message on unknown intent
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10, 6.11, 6.12_
  - [ ]* 6.2 Write unit tests for model router in `tests/test_model_router.py`
    - Test list_tasks intent routes to task listing handler
    - Test create_task intent extracts details and creates task
    - Test complete_task intent marks task done
    - Test greeting intent generates response with member name
    - Test upload_document intent delegates to document processing
    - Test list_documents intent returns document summary
    - Test ask_question intent generates LLM response
    - Test unknown intent returns Hebrew help message
    - Test permission denied returns `🔒` and audit logs
    - Test conversation record saved for every interaction with correct intent
    - Test unknown member handling
    - _Requirements: 10.2_

- [x] 7. Checkpoint — Verify new component tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Refactor message handler and update existing tests
  - [x] 8.1 Refactor `src/services/message_handler.py` to thin auth layer
    - Keep `handle_incoming_message` signature identical (no changes to whatsapp.py)
    - Keep unknown phone → Hebrew rejection + save conversation
    - Keep inactive member → Hebrew inactive message + save conversation
    - For active members: delegate to `route_message()` from model_router
    - Remove all keyword matching, `_handle_text`, `_handle_list_tasks`, `_handle_create_task`, `_handle_complete_task`, `_handle_media` functions
    - Keep `_save_conversation` only for unknown/inactive paths (router saves its own)
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_
  - [x] 8.2 Update `tests/test_message_handler.py` to mock `route_message`
    - Update mocks to patch `route_message` instead of individual handlers
    - Keep all existing assertion patterns (Hebrew content, permission markers)
    - Ensure all 12 existing message handler tests pass with updated mocks
    - _Requirements: 10.5_

- [x] 9. Update health endpoint
  - [x] 9.1 Update `src/routers/health.py` to include Ollama status
    - Import and instantiate `OllamaClient`
    - Call `is_available()` to check connectivity and model status
    - Add `ollama` field: `"connected"` or `"disconnected"`
    - Add `ollama_model` field: model name or `"not loaded"`
    - Make the endpoint async to support the async `is_available` call
    - _Requirements: 9.1, 9.2_
  - [x] 9.2 Update `tests/test_health.py` with Ollama field assertions
    - Mock `OllamaClient.is_available` in existing tests
    - Add test for `ollama: "connected"` and `ollama_model` when available
    - Add test for `ollama: "disconnected"` and `ollama_model: "not loaded"` when unavailable
    - Ensure existing 4 health tests still pass
    - _Requirements: 10.4_

- [x] 10. Checkpoint — Verify all 52 existing tests still pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Update Docker Compose and setup script
  - [x] 11.1 Update `docker-compose.yml` with Ollama service
    - Add `ollama` service: image `ollama/ollama:latest`, container name `fortress-ollama`, restart `unless-stopped`, port `11434:11434`, volume `ollama_data:/root/.ollama`, memory reservation 6G
    - Add `OLLAMA_API_URL: http://ollama:11434` to fortress service environment
    - Add `ollama_data` to volumes section
    - _Requirements: 1.1, 1.2, 1.3_
  - [x] 11.2 Create `scripts/setup_ollama.sh`
    - Make executable
    - Poll Ollama API health endpoint until ready (max 30 retries, 2s interval)
    - Pull `llama3.1:8b` model via POST `/api/pull`
    - Verify model in `/api/tags` response
    - Print success/failure messages to stdout/stderr
    - Exit non-zero on timeout or pull failure
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

- [x] 12. Update documentation
  - [x] 12.1 Update `README.md` with Ollama architecture and setup
    - Document Ollama service in architecture section
    - Add setup script instructions and model download note
    - Update phase status to reflect Phase 4A
    - Update project structure to show new files
    - _Requirements: 11.1_
  - [x] 12.2 Update `docs/architecture.md` with AI components
    - Add Ollama container to architecture diagram
    - Document Intent_Detector, Model_Router, LLM_Client, System_Prompts
    - Update message flow to show intent detection → LLM-powered response
    - _Requirements: 11.2_

- [x] 13. Final checkpoint — Run full test suite
  - Ensure all 52 existing tests + all new tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- No property-based tests (Hypothesis) — unit tests only per user preference
- All LLM interactions are mocked in tests — no real Ollama instance needed
- The message handler signature stays identical so whatsapp.py requires zero changes
- Hebrew fallback messages ensure family members never see raw errors
