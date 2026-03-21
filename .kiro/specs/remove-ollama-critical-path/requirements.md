# Requirements Document

## Introduction

Fortress 2.0 currently uses Ollama for intent classification on every message that does not match a keyword. This adds 1-3 seconds latency and consumes 5GB RAM for a task that the same LLM generating the response can handle. This feature removes Ollama from the critical message-processing path by combining intent classification and response generation into a single LLM call, reducing non-keyword message latency by approximately 50%.

## Glossary

- **Intent_Detector**: The service (`intent_detector.py`) that classifies incoming WhatsApp messages into one of 8 intent categories using keyword matching and, currently, an Ollama LLM fallback.
- **Workflow_Engine**: The LangGraph StateGraph (`workflow_engine.py`) that orchestrates message processing through a pipeline of nodes: intent detection, permission checking, memory loading, action dispatch, response generation, memory saving, and conversation persistence.
- **Unified_Handler**: A new service (`unified_handler.py`) that combines intent classification and response generation into a single LLM call for messages that do not match any keyword.
- **Model_Dispatcher**: The service (`model_dispatch.py`) that routes LLM requests to providers (OpenRouter, Bedrock, Ollama) based on intent sensitivity.
- **System_Prompts**: The module (`system_prompts.py`) containing predefined prompt templates for LLM interactions.
- **Unified_LLM_Node**: A new LangGraph node in the Workflow_Engine that invokes the Unified_Handler for messages classified as "needs_llm".
- **OllamaClient**: The async HTTP client (`llm_client.py`) for Ollama REST API communication. Retained for future use and as a last-resort generation fallback in Model_Dispatcher.
- **Keyword_Match**: The synchronous function `_match_keywords()` in Intent_Detector that matches messages against known Hebrew and English keywords.
- **needs_llm**: A new intent string returned by Intent_Detector when no keyword matches, indicating the message requires LLM-based classification and response.

## Requirements

### Requirement 1: Unified Classification and Response Prompt

**User Story:** As a developer, I want a single Hebrew prompt that instructs the LLM to classify intent AND generate a response in one call, so that non-keyword messages are handled in a single round-trip instead of two.

#### Acceptance Criteria

1. THE System_Prompts module SHALL contain a UNIFIED_CLASSIFY_AND_RESPOND constant of type `str`.
2. WHEN the UNIFIED_CLASSIFY_AND_RESPOND prompt is sent to an LLM, THE LLM SHALL return a JSON object containing an "intent" field (one of the 8 valid intents) and a "response" field (Hebrew text).
3. THE UNIFIED_CLASSIFY_AND_RESPOND prompt SHALL instruct the LLM to extract task details (title, due_date, category, priority) when the classified intent is "create_task".
4. THE UNIFIED_CLASSIFY_AND_RESPOND prompt SHALL be written in Hebrew for user-facing instruction portions.

### Requirement 2: Synchronous Intent Detection Without Ollama

**User Story:** As a developer, I want intent detection to be synchronous and instantaneous, so that no network call is made during the intent classification step.

#### Acceptance Criteria

1. THE Intent_Detector SHALL expose a synchronous function `detect_intent(text: str, has_media: bool) -> str` with no `llm_client` parameter.
2. WHEN `has_media` is True, THE Intent_Detector SHALL return "upload_document".
3. WHEN a Keyword_Match succeeds, THE Intent_Detector SHALL return the matched intent string.
4. WHEN no Keyword_Match succeeds and `has_media` is False, THE Intent_Detector SHALL return "needs_llm".
5. THE Intent_Detector module SHALL NOT import OllamaClient.
6. THE Intent_Detector module SHALL NOT contain the `_detect_intent_with_llm` function.
7. THE Intent_Detector SHALL complete execution without any network calls or awaitable operations.

### Requirement 3: Unified LLM Handler

**User Story:** As a developer, I want a handler that sends a message to the LLM with the unified prompt and parses the structured JSON response, so that intent classification and response generation happen in one call.

#### Acceptance Criteria

1. THE Unified_Handler SHALL expose an async function `handle_with_llm(message_text: str, member_name: str, memories: list, dispatcher: ModelDispatcher) -> tuple[str, str, dict | None]` that returns (intent, response_text, task_details_or_none).
2. WHEN the Unified_Handler receives a message, THE Unified_Handler SHALL send the message to the Model_Dispatcher with the UNIFIED_CLASSIFY_AND_RESPOND prompt.
3. WHEN the LLM returns valid JSON with an "intent" field matching one of the 8 valid intents, THE Unified_Handler SHALL return that intent and the "response" field text.
4. WHEN the LLM returns an "intent" of "create_task", THE Unified_Handler SHALL also return the extracted task details as a dict.
5. IF the LLM returns invalid JSON, THEN THE Unified_Handler SHALL return ("unknown", a Hebrew fallback message, None).
6. IF the LLM returns an intent not in the valid set, THEN THE Unified_Handler SHALL default the intent to "unknown".
7. THE Unified_Handler SHALL log the classified intent, response length, and elapsed time.

### Requirement 4: Workflow Engine Conditional Routing

**User Story:** As a developer, I want the workflow engine to route "needs_llm" messages through a unified LLM node that classifies and responds in one step, so that the two-call flow is replaced by a single-call flow.

#### Acceptance Criteria

1. THE Workflow_Engine intent_node SHALL call the synchronous `detect_intent(text, has_media)` function without any LLM client argument.
2. WHEN intent_node returns "needs_llm", THE Workflow_Engine SHALL route the message to the Unified_LLM_Node.
3. WHEN intent_node returns any intent other than "needs_llm", THE Workflow_Engine SHALL route the message to permission_node (existing behavior).
4. THE Unified_LLM_Node SHALL call `handle_with_llm()` and set the state "intent" and "response" fields from the result.
5. WHEN the Unified_LLM_Node receives a "create_task" intent with task details, THE Unified_LLM_Node SHALL create the task via the task service.
6. AFTER the Unified_LLM_Node completes, THE Workflow_Engine SHALL route to permission_node so that permission checks are applied to the LLM-classified intent.
7. WHEN permission is granted after Unified_LLM_Node, THE Workflow_Engine SHALL skip action_node (response is already generated) and proceed to response_node.
8. WHEN permission is denied after Unified_LLM_Node, THE Workflow_Engine SHALL replace the LLM-generated response with the denial message.
9. THE Workflow_Engine intent_node SHALL NOT import or instantiate OllamaClient.

### Requirement 5: Ollama Removal from Intent Path Only

**User Story:** As a developer, I want Ollama removed only from the intent classification path while keeping it available as a generation fallback, so that the system retains its full fallback chain.

#### Acceptance Criteria

1. THE Intent_Detector module SHALL NOT import OllamaClient or any reference to Ollama.
2. THE Workflow_Engine intent_node SHALL NOT instantiate OllamaClient.
3. THE OllamaClient class in `llm_client.py` SHALL remain unchanged.
4. THE Model_Dispatcher SHALL continue to include Ollama as a fallback provider in its dispatch chain.
5. THE docker-compose.yml Ollama service definition SHALL remain unchanged.
6. THE health endpoint Ollama check SHALL remain unchanged.

### Requirement 6: Test Coverage

**User Story:** As a developer, I want comprehensive tests covering the new synchronous intent detection, unified handler, and updated workflow, so that all changes are verified and existing functionality is preserved.

#### Acceptance Criteria

1. THE test suite for Intent_Detector SHALL remove all tests that mock OllamaClient for LLM fallback (the 3 existing LLM fallback tests).
2. THE test suite for Intent_Detector SHALL include tests verifying that `detect_intent` returns "needs_llm" when no keyword matches and `has_media` is False.
3. THE test suite for Intent_Detector SHALL verify that `detect_intent` is a synchronous function (not a coroutine).
4. THE test suite SHALL include a new `test_unified_handler.py` module testing `handle_with_llm()` for valid JSON responses, invalid JSON responses, create_task with task details, and unknown intent fallback.
5. THE test suite SHALL include a new `test_workflow_engine.py` module testing the conditional routing: keyword match goes to permission_node, "needs_llm" goes to Unified_LLM_Node.
6. WHEN all tests are executed, THE test suite SHALL have all 130 existing tests passing (minus the 3 removed Ollama mock tests, plus new tests).

### Requirement 7: Documentation Update

**User Story:** As a developer, I want the architecture documentation to reflect the new message flow, so that the team understands the current system design.

#### Acceptance Criteria

1. THE architecture.md SHALL update the message flow diagram to show the new conditional routing: keyword match → permission_node, "needs_llm" → Unified_LLM_Node → permission_node.
2. THE architecture.md SHALL remove references to Ollama performing intent classification in the message flow.
3. THE architecture.md SHALL document the Unified_LLM_Node and its role in the workflow.
4. THE architecture.md SHALL update the Intent_Detector service description to reflect synchronous keyword-only detection with "needs_llm" fallback.
5. THE architecture.md SHALL retain all references to Ollama as a generation fallback provider in Model_Dispatcher and the health endpoint.
