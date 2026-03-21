# Requirements Document

## Introduction

Fortress currently routes ALL Hebrew text generation through AWS Bedrock (Claude), which is expensive for simple interactions and creates a single point of failure. This feature introduces a 3-tier model routing architecture with OpenRouter as a middle tier for cheap/free models, a routing policy based on data sensitivity, and a fallback chain so the system degrades gracefully when any provider is unavailable.

**Tier 1: Ollama (Local)** — Free, intent classification only (English).
**Tier 2: OpenRouter (Free/Cheap models)** — $0–2/month, greetings, task formatting, simple responses, non-sensitive data only.
**Tier 3: Bedrock (Claude)** — $5–15/month, financial queries, document classification, contract analysis, complex reasoning, sensitive/personal data.

**Fallback chain:** Bedrock fails → OpenRouter → Ollama → hardcoded Hebrew.

## Glossary

- **Fortress**: The FastAPI application container serving as the family intelligence system.
- **OpenRouter_Client**: An async HTTP client that communicates with the OpenRouter API using the OpenAI-compatible chat completions format.
- **Routing_Policy**: A service that maps intents to data sensitivity levels and returns an ordered list of LLM providers for each intent.
- **Model_Dispatcher**: A service that accepts a prompt, system prompt, intent, and context, then tries each provider in the ordered route until one succeeds.
- **Workflow_Engine**: The LangGraph StateGraph pipeline that orchestrates message processing through 7 nodes.
- **Bedrock_Client**: The existing async client for AWS Bedrock Claude models (Haiku and Sonnet).
- **Ollama_Client**: The existing async client for the local Ollama LLM used for intent classification.
- **Health_Endpoint**: The GET /health route that reports connectivity status for all system dependencies.
- **Sensitivity_Level**: A classification of data sensitivity for an intent — one of "low", "medium", or "high".
- **Provider**: An LLM backend — one of "openrouter", "bedrock", or "ollama".
- **Fallback_Chain**: The ordered sequence of providers attempted when the preferred provider fails.
- **Hebrew_Fallback**: A hardcoded Hebrew error message returned when all LLM providers fail: "מצטער, לא הצלחתי לעבד את הבקשה. נסה שוב."

## Requirements

### Requirement 1: OpenRouter Client

**User Story:** As a system operator, I want Fortress to communicate with OpenRouter's API, so that cheap or free models can handle simple Hebrew generation tasks.

#### Acceptance Criteria

1. THE OpenRouter_Client SHALL expose an async `generate` method that accepts a prompt, a system prompt, and an optional model identifier, and returns a string response.
2. THE OpenRouter_Client SHALL expose an async `is_available` method that returns a tuple of (bool, str | None) indicating connectivity status and the configured model name.
3. THE OpenRouter_Client SHALL send requests to the OpenRouter API using the OpenAI-compatible chat completions format at `https://openrouter.ai/api/v1/chat/completions`.
4. THE OpenRouter_Client SHALL include the `Authorization` header with the configured API key, the `HTTP-Referer` header, and the `X-Title` header set to "Fortress" in every request.
5. THE OpenRouter_Client SHALL use httpx.AsyncClient with a 30-second timeout for all HTTP requests.
6. THE OpenRouter_Client SHALL use the default model from the OPENROUTER_MODEL configuration value when no model is explicitly provided.
7. IF the OpenRouter API returns an error or the request times out, THEN THE OpenRouter_Client SHALL return the Hebrew_Fallback message.
8. THE OpenRouter_Client SHALL log every request with the model identifier, prompt length, and response time in seconds.
9. THE OpenRouter_Client SHALL use Python type hints on all public method signatures.

### Requirement 2: Configuration Updates

**User Story:** As a system operator, I want OpenRouter configuration values in the environment, so that I can control the API key and model selection without code changes.

#### Acceptance Criteria

1. THE Fortress SHALL read the `OPENROUTER_API_KEY` value from the environment, defaulting to an empty string.
2. THE Fortress SHALL read the `OPENROUTER_MODEL` value from the environment, defaulting to `meta-llama/llama-3.1-70b-instruct:free`.
3. THE Fortress SHALL read the `OPENROUTER_FALLBACK_MODEL` value from the environment, defaulting to `google/gemma-2-9b-it:free`.
4. THE Fortress SHALL include `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, and `OPENROUTER_FALLBACK_MODEL` in the `.env.example` file with descriptive comments.
5. THE Fortress SHALL pass the `OPENROUTER_API_KEY` environment variable to the fortress service in `docker-compose.yml`.

### Requirement 3: Routing Policy

**User Story:** As a system operator, I want intent-based routing rules that respect data sensitivity, so that sensitive data is never sent to cheaper providers.

#### Acceptance Criteria

1. THE Routing_Policy SHALL classify each intent into exactly one Sensitivity_Level: "low", "medium", or "high".
2. THE Routing_Policy SHALL classify the `greeting` intent as "low" sensitivity.
3. THE Routing_Policy SHALL classify the `list_tasks`, `create_task`, `complete_task`, `list_documents`, and `unknown` intents as "medium" sensitivity.
4. THE Routing_Policy SHALL classify the `ask_question` and `upload_document` intents as "high" sensitivity.
5. WHEN the Sensitivity_Level is "low", THE Routing_Policy SHALL return the provider order: ["openrouter", "bedrock", "ollama"].
6. WHEN the Sensitivity_Level is "medium", THE Routing_Policy SHALL return the provider order: ["openrouter", "bedrock", "ollama"].
7. WHEN the Sensitivity_Level is "high", THE Routing_Policy SHALL return the provider order: ["bedrock", "ollama"].
8. THE Routing_Policy SHALL expose a `get_route(intent)` function that returns the ordered list of providers for the given intent.
9. THE Routing_Policy SHALL expose a `get_sensitivity(intent)` function that returns the Sensitivity_Level for the given intent.
10. FOR ALL intents classified as "high" sensitivity, THE Routing_Policy SHALL exclude "openrouter" from the returned provider list.

### Requirement 4: Model Dispatch

**User Story:** As a system operator, I want a unified dispatch service that tries providers in order and falls back automatically, so that the system remains responsive even when a provider is down.

#### Acceptance Criteria

1. THE Model_Dispatcher SHALL expose an async `dispatch` method that accepts a prompt, a system prompt, an intent string, and an optional context dict, and returns a string response.
2. WHEN `dispatch` is called, THE Model_Dispatcher SHALL obtain the ordered provider list from the Routing_Policy for the given intent.
3. THE Model_Dispatcher SHALL attempt each provider in the ordered list sequentially until one returns a successful response.
4. WHEN the provider is "bedrock" and the intent is "ask_question", THE Model_Dispatcher SHALL use the "sonnet" model for generation.
5. WHEN the provider is "bedrock" and the intent is not "ask_question", THE Model_Dispatcher SHALL use the "haiku" model for generation.
6. IF all providers in the ordered list fail, THEN THE Model_Dispatcher SHALL return the Hebrew_Fallback message.
7. THE Model_Dispatcher SHALL log every dispatch attempt including the intent, the provider being tried, and whether the attempt succeeded or failed.
8. WHEN a provider returns the Hebrew_Fallback message, THE Model_Dispatcher SHALL treat the response as a failure and proceed to the next provider in the list.

### Requirement 5: Workflow Engine Integration

**User Story:** As a developer, I want the workflow engine to use the Model_Dispatcher instead of calling Bedrock directly, so that all Hebrew generation benefits from the routing and fallback logic.

#### Acceptance Criteria

1. THE Workflow_Engine action_node SHALL use Model_Dispatcher.dispatch() for all Hebrew text generation instead of calling Bedrock_Client directly.
2. THE Workflow_Engine action_node SHALL pass the detected intent to Model_Dispatcher.dispatch().
3. THE Workflow_Engine response_node SHALL continue to operate as a pass-through node with no direct LLM calls.
4. THE Workflow_Engine memory_save_node SHALL continue using Bedrock_Client directly for memory extraction, as memory content is always sensitive.
5. WHEN the Workflow_Engine action_node dispatches a request, THE Workflow_Engine SHALL pass the system prompt and user prompt to Model_Dispatcher.dispatch().

### Requirement 6: Health Endpoint Update

**User Story:** As a system operator, I want the health endpoint to report OpenRouter connectivity status, so that I can monitor all three LLM providers from a single endpoint.

#### Acceptance Criteria

1. THE Health_Endpoint SHALL include an `openrouter` field in the response with one of three values: "connected", "disconnected", or "no_key".
2. WHEN the OPENROUTER_API_KEY is empty, THE Health_Endpoint SHALL report the `openrouter` field as "no_key".
3. WHEN the OPENROUTER_API_KEY is set and the OpenRouter API is reachable, THE Health_Endpoint SHALL report the `openrouter` field as "connected".
4. WHEN the OPENROUTER_API_KEY is set and the OpenRouter API is unreachable, THE Health_Endpoint SHALL report the `openrouter` field as "disconnected".
5. THE Health_Endpoint SHALL include an `openrouter_model` field showing the configured model name or "not configured" when no API key is set.

### Requirement 7: Environment and Infrastructure Updates

**User Story:** As a system operator, I want the environment template and Docker Compose updated with OpenRouter settings, so that deployment is straightforward.

#### Acceptance Criteria

1. THE `.env.example` file SHALL include `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, and `OPENROUTER_FALLBACK_MODEL` entries with default values and comments.
2. THE `docker-compose.yml` SHALL pass the `OPENROUTER_API_KEY` environment variable to the fortress service using the `${OPENROUTER_API_KEY:-}` syntax.

### Requirement 8: Graceful Operation Without OpenRouter

**User Story:** As a system operator, I want the system to work without an OpenRouter API key, so that OpenRouter is an optional enhancement rather than a hard dependency.

#### Acceptance Criteria

1. WHEN the OPENROUTER_API_KEY is empty, THE Model_Dispatcher SHALL skip the "openrouter" provider in the fallback chain and proceed to the next provider.
2. WHEN the OPENROUTER_API_KEY is empty, THE OpenRouter_Client is_available method SHALL return (False, None) without making any HTTP requests.
3. WHEN the OPENROUTER_API_KEY is empty, THE Fortress SHALL continue to route all generation requests through Bedrock and Ollama as before.

### Requirement 9: Test Coverage

**User Story:** As a developer, I want comprehensive tests for all new services, so that routing logic and fallback behavior are verified.

#### Acceptance Criteria

1. THE test suite SHALL include tests for OpenRouter_Client covering: successful generation, timeout handling, HTTP error handling, and is_available checks.
2. THE test suite SHALL include tests for Routing_Policy covering: correct sensitivity classification for all intents, correct provider ordering for each sensitivity level, and verification that "high" sensitivity intents exclude "openrouter".
3. THE test suite SHALL include tests for Model_Dispatcher covering: successful dispatch to the first provider, fallback to the next provider on failure, fallback to Hebrew_Fallback when all providers fail, and correct Bedrock model selection per intent.
4. THE test suite SHALL include updated tests for the Health_Endpoint covering the new `openrouter` and `openrouter_model` fields.
5. THE test suite SHALL mock all external API calls (OpenRouter, Bedrock, Ollama) and make no real HTTP requests.
6. WHEN the full test suite is run, all 91 existing tests SHALL continue to pass alongside the new tests.

### Requirement 10: Documentation Updates

**User Story:** As a developer, I want the README and architecture docs updated to reflect the 3-tier routing, so that the system design is accurately documented.

#### Acceptance Criteria

1. THE README.md SHALL describe the 3-tier model routing architecture (Ollama, OpenRouter, Bedrock) with their respective roles and cost tiers.
2. THE architecture.md SHALL include a description of the routing policy, the dispatch flow, and the fallback chain.
3. THE architecture.md SHALL update the Model Routing table to include OpenRouter as a provider tier.
4. THE architecture.md SHALL update the Graceful Degradation section to describe the full fallback chain: Bedrock → OpenRouter → Ollama → hardcoded Hebrew.
