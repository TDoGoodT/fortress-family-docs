# Implementation Plan: Model Router with OpenRouter Fallbacks

## Overview

Add a 3-tier model routing architecture to Fortress with OpenRouter as a middle tier between Ollama (local) and Bedrock (cloud). Implementation follows a bottom-up approach: config → clients → policy → dispatcher → integration → infrastructure → tests → docs.

## Tasks

- [x] 1. Add OpenRouter configuration variables
  - [x] 1.1 Add OPENROUTER_API_KEY, OPENROUTER_MODEL, and OPENROUTER_FALLBACK_MODEL to `fortress/src/config.py`
    - `OPENROUTER_API_KEY`: str, default `""`
    - `OPENROUTER_MODEL`: str, default `"meta-llama/llama-3.1-70b-instruct:free"`
    - `OPENROUTER_FALLBACK_MODEL`: str, default `"google/gemma-2-9b-it:free"`
    - _Requirements: 2.1, 2.2, 2.3_

- [x] 2. Implement OpenRouterClient
  - [x] 2.1 Create `fortress/src/services/openrouter_client.py` with the OpenRouterClient class
    - Async `generate(prompt, system_prompt, model)` method using httpx.AsyncClient
    - Async `is_available()` method returning `(bool, str | None)`
    - Endpoint: `https://openrouter.ai/api/v1/chat/completions`
    - Headers: Authorization Bearer, HTTP-Referer, X-Title: Fortress
    - 30-second timeout, returns HEBREW_FALLBACK on any error
    - Logs every request: model, prompt_len, response time
    - Returns `(False, None)` immediately from `is_available` if API key is empty
    - Returns HEBREW_FALLBACK immediately from `generate` if API key is empty
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9_

- [x] 3. Implement RoutingPolicy
  - [x] 3.1 Create `fortress/src/services/routing_policy.py` with pure functions
    - Define `SENSITIVITY_MAP`: greeting→low, list_tasks/create_task/complete_task/list_documents/unknown→medium, ask_question/upload_document→high
    - Define `ROUTE_MAP`: low→[openrouter, bedrock, ollama], medium→[openrouter, bedrock, ollama], high→[bedrock, ollama]
    - `get_sensitivity(intent)` returns sensitivity level, defaults to "high" for unknown intents
    - `get_route(intent)` returns ordered provider list
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10_

- [x] 4. Implement ModelDispatcher
  - [x] 4.1 Create `fortress/src/services/model_dispatch.py` with the ModelDispatcher class
    - Constructor accepts optional `bedrock_client`, `openrouter_client`, `ollama_client`
    - Async `dispatch(prompt, system_prompt, intent, context)` method
    - Calls `get_route(intent)` to get provider order
    - For "openrouter": skip if OPENROUTER_API_KEY is empty, call generate, treat HEBREW_FALLBACK as failure
    - For "bedrock": use "sonnet" if intent is "ask_question", else "haiku", treat HEBREW_FALLBACK as failure
    - For "ollama": call generate, treat HEBREW_FALLBACK as failure
    - Returns HEBREW_FALLBACK if all providers fail
    - Logs each attempt: intent, provider, success/failure
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8_

- [x] 5. Checkpoint - Verify new services
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Update workflow engine to use ModelDispatcher
  - [x] 6.1 Modify `action_node` in `fortress/src/services/workflow_engine.py` to use ModelDispatcher
    - Replace `bedrock = BedrockClient()` with `dispatcher = ModelDispatcher(...)` instantiation
    - Update action handler signatures from `bedrock: BedrockClient` to `dispatcher: ModelDispatcher`
    - Each handler calls `dispatcher.dispatch(prompt, system_prompt, intent)` instead of `bedrock.generate(prompt, system_prompt, model)`
    - `memory_save_node` continues using BedrockClient directly (unchanged)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 7. Update Docker Compose and .env.example
  - [x] 7.1 Add OpenRouter env vars to `fortress/.env.example`
    - Add `OPENROUTER_API_KEY=` with comment about optional OpenRouter integration
    - Add `OPENROUTER_MODEL=meta-llama/llama-3.1-70b-instruct:free`
    - Add `OPENROUTER_FALLBACK_MODEL=google/gemma-2-9b-it:free`
    - _Requirements: 2.4, 7.1_
  - [x] 7.2 Add OPENROUTER_API_KEY to `fortress/docker-compose.yml` fortress service environment
    - Use `${OPENROUTER_API_KEY:-}` syntax
    - _Requirements: 2.5, 7.2_

- [x] 8. Update health endpoint for OpenRouter
  - [x] 8.1 Modify `fortress/src/routers/health.py` to include OpenRouter status
    - Import OpenRouterClient and OPENROUTER_API_KEY
    - If no API key: report `"no_key"` and `"not configured"`
    - If API key set: call `is_available()`, report `"connected"` or `"disconnected"`
    - Add `openrouter` and `openrouter_model` fields to response dict
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 9. Checkpoint - Verify integration
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Write unit tests for OpenRouterClient
  - [x] 10.1 Create `fortress/tests/test_openrouter_client.py`
    - Test successful generation: mock httpx to return valid response, verify returned text
    - Test timeout handling: mock httpx to raise TimeoutException, verify HEBREW_FALLBACK
    - Test HTTP error handling: mock httpx to return 500, verify HEBREW_FALLBACK
    - Test connection error: mock httpx to raise ConnectError, verify HEBREW_FALLBACK
    - Test `is_available` with valid key: mock successful HTTP response, verify `(True, model_name)`
    - Test `is_available` with empty key: verify `(False, None)` without HTTP call
    - Test request headers: verify Authorization, HTTP-Referer, X-Title headers are sent
    - Test default model used when none specified
    - Test custom model used when explicitly provided
    - Test empty API key on generate returns fallback without HTTP call
    - _Requirements: 9.1, 9.5_

- [x] 11. Write unit tests for RoutingPolicy
  - [x] 11.1 Create `fortress/tests/test_routing_policy.py`
    - Test `get_sensitivity("greeting")` returns "low"
    - Test `get_sensitivity` for medium intents (list_tasks, create_task, complete_task, list_documents, unknown)
    - Test `get_sensitivity` for high intents (ask_question, upload_document)
    - Test `get_route("greeting")` returns `["openrouter", "bedrock", "ollama"]`
    - Test `get_route("list_tasks")` returns `["openrouter", "bedrock", "ollama"]`
    - Test `get_route("ask_question")` returns `["bedrock", "ollama"]`
    - Test `get_route("upload_document")` returns `["bedrock", "ollama"]`
    - Test high sensitivity routes never contain "openrouter"
    - Test unknown/unrecognized intent defaults to "high" sensitivity
    - Test every known intent has a sensitivity mapping
    - _Requirements: 9.2_

- [x] 12. Write unit tests for ModelDispatcher
  - [x] 12.1 Create `fortress/tests/test_model_dispatch.py`
    - Test successful dispatch to first provider (openrouter succeeds)
    - Test fallback: openrouter fails → bedrock succeeds
    - Test fallback: openrouter fails → bedrock fails → ollama succeeds
    - Test all providers fail → returns HEBREW_FALLBACK
    - Test Hebrew fallback response from provider treated as failure
    - Test high sensitivity intent skips openrouter, goes to bedrock
    - Test `ask_question` intent uses bedrock sonnet model
    - Test non-ask_question intent uses bedrock haiku model
    - Test empty API key skips openrouter provider
    - Test dispatch logs each attempt (verify log calls)
    - _Requirements: 9.3_

- [x] 13. Update health endpoint tests
  - [x] 13.1 Add OpenRouter tests to `fortress/tests/test_health.py`
    - Test OpenRouter connected: mock `is_available` returning `(True, model_name)`, verify "connected" and model name
    - Test OpenRouter disconnected: mock `is_available` returning `(False, None)`, verify "disconnected"
    - Test OpenRouter no key: mock empty OPENROUTER_API_KEY, verify "no_key" and "not configured"
    - Update existing test mocks to also mock OpenRouter (so existing 8 tests continue passing)
    - _Requirements: 9.4, 9.6_

- [x] 14. Checkpoint - Run full test suite
  - Ensure all 91 existing tests plus all new tests pass. Ask the user if questions arise.

- [x] 15. Update documentation
  - [x] 15.1 Update `fortress/README.md` with 3-tier routing description
    - Add OpenRouter to the Architecture section as a middle tier
    - Describe cost tiers: Ollama (free/local), OpenRouter ($0–2/month), Bedrock ($5–15/month)
    - Add `openrouter_client.py`, `routing_policy.py`, `model_dispatch.py` to Project Structure
    - Add new test files to Project Structure
    - _Requirements: 10.1_
  - [x] 15.2 Update `fortress/docs/architecture.md` with routing policy and dispatch flow
    - Update the Model Routing table to include OpenRouter as a provider tier
    - Add Routing Policy section describing sensitivity classification and provider ordering
    - Add Model Dispatcher section describing the dispatch flow and fallback chain
    - Update Graceful Degradation section with full fallback chain: preferred provider → next provider → ... → hardcoded Hebrew
    - Update the ASCII architecture diagram to include OpenRouter
    - _Requirements: 10.2, 10.3, 10.4_

- [x] 16. Final checkpoint - Full verification
  - Run the complete test suite. Ensure all 91 existing tests plus all new tests pass. Ask the user if questions arise.

## Notes

- All tests are required (not optional) per user instructions
- No property-based tests — unit tests only
- All 91 existing tests must continue to pass unchanged
- OpenRouter is optional: system works without an API key by skipping the provider
- `memory_save_node` always uses BedrockClient directly (never routed through dispatcher)
- Implementation language: Python (matching existing codebase)
