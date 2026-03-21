# Implementation Plan: Remove Ollama from Critical Path

## Overview

Replace the two-call message flow (Ollama intent classification → LLM response generation) with a single-call flow for non-keyword messages. Make `detect_intent` synchronous and keyword-only, add a unified LLM handler, and update the workflow engine with conditional routing. All changes are in Python.

## Tasks

- [x] 1. Make intent_detector.py synchronous and keyword-only
  - [x] 1.1 Modify `fortress/src/services/intent_detector.py`
    - Remove `OllamaClient` import and `INTENT_CLASSIFIER` import
    - Remove `_detect_intent_with_llm()` function entirely
    - Change `detect_intent` from `async def detect_intent(text, has_media, llm_client)` to `def detect_intent(text, has_media) -> str`
    - When no keyword matches and `has_media` is False, return `"needs_llm"` instead of calling LLM
    - Keep `_match_keywords()`, `INTENTS`, and `VALID_INTENTS` unchanged
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [x] 1.2 Update `fortress/tests/test_intent_detector.py`
    - Remove the 3 Ollama LLM fallback tests: `test_llm_fallback_invoked`, `test_llm_failure_returns_unknown`, `test_llm_invalid_intent_returns_unknown`
    - Remove `_mock_llm()` helper function
    - Remove all `@pytest.mark.asyncio` decorators and change all `async def` tests to plain `def`
    - Remove `llm_client=llm` / `llm` arguments from all `detect_intent()` calls; remove `await`
    - Remove `AsyncMock` and `MagicMock` imports (no longer needed)
    - Add `test_no_keyword_returns_needs_llm`: verify `detect_intent("מה מזג האוויר?", False)` returns `"needs_llm"`
    - Add `test_detect_intent_is_sync`: verify `detect_intent` is not a coroutine function using `inspect.iscoroutinefunction`
    - Add `test_no_ollama_import`: verify `intent_detector` module source has no `OllamaClient` reference
    - Add `test_no_llm_fallback_function`: verify `_detect_intent_with_llm` does not exist via `hasattr`
    - _Requirements: 6.1, 6.2, 6.3_

- [x] 2. Checkpoint — Run tests, verify intent_detector changes
  - Run `pytest fortress/tests/test_intent_detector.py -v` and ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Add UNIFIED_CLASSIFY_AND_RESPOND prompt and routing policy update
  - [x] 3.1 Add `UNIFIED_CLASSIFY_AND_RESPOND` constant to `fortress/src/prompts/system_prompts.py`
    - Hebrew prompt instructing the LLM to: classify intent into one of 8 valid intents, generate a Hebrew response, extract task details (title, due_date, category, priority) when intent is `create_task`
    - Instruct LLM to return structured JSON: `{"intent": "...", "response": "...", "task_data": {...}}`
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [x] 3.2 Add `"needs_llm"` to `SENSITIVITY_MAP` in `fortress/src/services/routing_policy.py`
    - Add `"needs_llm": "medium"` to the `SENSITIVITY_MAP` dict
    - This gives the unified handler the `openrouter → bedrock → ollama` fallback chain
    - _Requirements: design section 6_

- [x] 4. Create unified_handler.py service
  - [x] 4.1 Create `fortress/src/services/unified_handler.py`
    - Implement `async def handle_with_llm(message_text, member_name, memories, dispatcher) -> tuple[str, str, dict | None]`
    - Send `message_text` with `UNIFIED_CLASSIFY_AND_RESPOND` prompt to `ModelDispatcher.dispatch()` using intent `"needs_llm"`
    - Parse JSON response: extract `intent`, `response`, and optional `task_data`
    - Validate intent against `VALID_INTENTS` from `intent_detector`
    - On invalid JSON → return `("unknown", Hebrew fallback message, None)`
    - On invalid intent → default to `"unknown"`, keep response text
    - Log classified intent, response length, and elapsed time
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

  - [x]* 4.2 Create `fortress/tests/test_unified_handler.py`
    - `test_valid_json_greeting`: mock dispatcher returning valid JSON with greeting intent, verify correct tuple (Property 3)
    - `test_valid_json_ask_question`: mock dispatcher returning ask_question intent (Property 3)
    - `test_create_task_with_task_data`: mock dispatcher returning create_task with task_data dict (Property 4)
    - `test_create_task_without_task_data`: create_task intent with no task_data returns None third element (Property 4)
    - `test_invalid_json_returns_fallback`: dispatcher returns non-JSON string, verify ("unknown", fallback, None) (Property 5)
    - `test_invalid_intent_defaults_unknown`: unrecognized intent string defaults to "unknown" (Property 5)
    - `test_dispatcher_called_with_unified_prompt`: verify dispatcher.dispatch receives UNIFIED_CLASSIFY_AND_RESPOND (Property 3)
    - `test_logging_output`: verify intent, response length, elapsed time are logged (Req 3.7)
    - _Requirements: 6.4_

- [x] 5. Checkpoint — Run tests, verify unified_handler
  - Run `pytest fortress/tests/test_unified_handler.py -v` and ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Update workflow_engine.py with new nodes and conditional routing
  - [x] 6.1 Modify `fortress/src/services/workflow_engine.py`
    - Add `task_data: dict | None` and `from_unified: bool` fields to `WorkflowState` TypedDict
    - Update `initial_state` in `run_workflow` to include `task_data: None` and `from_unified: False`
    - Remove `OllamaClient` import
    - Import `handle_with_llm` from `unified_handler` and `load_memories` for unified_llm_node
    - Change `intent_node` from async to sync-compatible: call `detect_intent(text, has_media)` without OllamaClient, without await
    - Add `unified_llm_node`: async node that loads memories, calls `handle_with_llm()`, sets `intent`, `response`, `task_data`, and `from_unified=True` in state
    - Add `task_create_node`: async node that creates task from `task_data` in state using `create_task` from tasks service
    - Add `_intent_router` conditional: returns `"unified_llm_node"` when intent is `"needs_llm"`, otherwise `"permission_node"`
    - Modify `_permission_router` to handle unified path: granted + `from_unified` + `task_data` → `"task_create_node"`, granted + `from_unified` → `"response_node"`, granted + keyword → `"memory_load_node"`, denied → `"response_node"`
    - Update `_build_graph()`: add `unified_llm_node` and `task_create_node` nodes, replace `intent_node → permission_node` edge with conditional edges via `_intent_router`, update `_permission_router` conditional edges to include new targets
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 5.2_

  - [x]* 6.2 Create `fortress/tests/test_workflow_engine.py`
    - `test_keyword_routes_to_permission_node`: mock detect_intent returning a keyword intent, verify permission_node is reached and unified_llm_node is not (Property 6)
    - `test_needs_llm_routes_to_unified_node`: mock detect_intent returning "needs_llm", verify unified_llm_node is called (Property 6)
    - `test_unified_node_sets_state`: verify unified_llm_node sets intent, response, from_unified in state (Property 7)
    - `test_unified_node_stores_task_data_no_create`: verify task_data stored, create_task not called in unified_llm_node (Property 7)
    - `test_task_created_after_permission_granted`: verify task_create_node calls create_task when permission granted and task_data present (Property 8)
    - `test_task_not_created_when_denied`: verify no task creation on permission denial (Property 8)
    - `test_unified_path_skips_action_node`: verify from_unified + granted skips action_node (Property 9)
    - `test_denial_replaces_unified_response`: verify denial message overrides LLM response (Property 10)
    - `test_no_ollama_in_workflow_engine`: verify OllamaClient not imported in workflow_engine module (Property 11)
    - `test_ollama_in_fallback_chain`: verify routing_policy still includes "ollama" in all route lists (Property 12)
    - _Requirements: 6.5_

- [x] 7. Checkpoint — Run full test suite
  - Run `pytest fortress/tests/ -v` and ensure all tests pass (existing 127 + new ~22 = ~149 total)
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Update documentation
  - [x] 8.1 Update `fortress/docs/architecture.md`
    - Update the message flow diagram to show conditional routing: keyword match → permission_node, "needs_llm" → unified_llm_node → permission_node
    - Remove references to Ollama performing intent classification in the message flow
    - Document the unified_llm_node and task_create_node and their roles in the workflow
    - Update the Intent Detector service description to reflect synchronous keyword-only detection with "needs_llm" fallback
    - Update the System Prompts description to mention UNIFIED_CLASSIFY_AND_RESPOND
    - Retain all references to Ollama as a generation fallback provider in Model Dispatcher and health endpoint
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 8.2 Update root `README.md` roadmap table
    - Update the Architecture diagram to remove "Ollama (local intent detection)" and replace with the new flow description
    - Update the Status section to reflect Phase 4B.6 completion with "✅ Complete" and final test count
    - _Requirements: 7.1_

- [x] 9. Final checkpoint — Full test suite and git push
  - Run `pytest fortress/tests/ -v` and confirm all tests pass with final count
  - Run `git add -A && git commit -m "feat: remove Ollama from critical path — unified classify+respond"` and `git push origin main`
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- All code is Python 3.12 — no language selection needed
- Ollama remains in docker-compose, health checks, and ModelDispatcher fallback chain — only removed from intent classification path
