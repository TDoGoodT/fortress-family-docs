# Design Document: Model Router with OpenRouter Fallbacks

## Overview

This feature introduces a 3-tier model routing architecture to Fortress, adding OpenRouter as a middle tier between the existing Ollama (local) and Bedrock (cloud) providers. The design adds three new services (`OpenRouterClient`, `RoutingPolicy`, `ModelDispatcher`), updates the workflow engine's `action_node` to use the dispatcher, extends the health endpoint, and updates configuration/infrastructure files.

The core principle: route requests based on data sensitivity. HIGH sensitivity intents (ask_question, upload_document) never leave Bedrock. LOW/MEDIUM sensitivity intents prefer OpenRouter (cheap/free) with Bedrock as fallback. The system degrades gracefully — if OpenRouter is unavailable or unconfigured, it's simply skipped.

```
                    ┌─────────────────┐
                    │  Incoming Msg   │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  Intent Node    │ ← Ollama (classify)
                    │  (unchanged)    │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │ Routing Policy  │ ← Maps intent → sensitivity → provider order
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │ Model Dispatcher│ ← Tries providers in order
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
        ┌───────────┐ ┌───────────┐ ┌───────────┐
        │ OpenRouter │ │  Bedrock  │ │  Ollama   │
        │ (free/cheap│ │ (Claude)  │ │ (local)   │
        │  models)   │ │ haiku/    │ │ fallback) │
        └───────────┘ │ sonnet    │ └───────────┘
                      └───────────┘
```

## Architecture

### New Files

| File | Purpose |
|------|---------|
| `fortress/src/services/openrouter_client.py` | Async HTTP client for OpenRouter API |
| `fortress/src/services/routing_policy.py` | Intent → sensitivity → provider ordering |
| `fortress/src/services/model_dispatch.py` | Unified dispatch with fallback chain |
| `fortress/tests/test_openrouter_client.py` | Unit tests for OpenRouter client |
| `fortress/tests/test_routing_policy.py` | Unit tests for routing policy |
| `fortress/tests/test_model_dispatch.py` | Unit tests for model dispatcher |

### Modified Files

| File | Change |
|------|--------|
| `fortress/src/config.py` | Add OPENROUTER_API_KEY, OPENROUTER_MODEL, OPENROUTER_FALLBACK_MODEL |
| `fortress/src/services/workflow_engine.py` | action_node uses ModelDispatcher instead of BedrockClient |
| `fortress/src/routers/health.py` | Add OpenRouter status fields |
| `fortress/.env.example` | Add OpenRouter env vars with comments |
| `fortress/docker-compose.yml` | Pass OPENROUTER_API_KEY to fortress service |
| `fortress/tests/test_health.py` | Add OpenRouter health check tests |
| `fortress/README.md` | Describe 3-tier routing |
| `fortress/docs/architecture.md` | Update routing table, degradation section, dispatch flow |

### Unchanged

- `memory_save_node` continues using `BedrockClient` directly (memory content is always sensitive)
- `response_node` remains a pass-through
- `intent_node` still uses Ollama for classification
- Legacy `model_router.py` kept for backward compatibility
- All 91 existing tests remain unmodified and passing

## Components and Interfaces

### 1. OpenRouterClient (`fortress/src/services/openrouter_client.py`)

```python
class OpenRouterClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        fallback_model: str | None = None,
    ) -> None: ...

    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        model: str | None = None,
    ) -> str:
        """Send chat completion request to OpenRouter.
        Returns response text or HEBREW_FALLBACK on any error."""
        ...

    async def is_available(self) -> tuple[bool, str | None]:
        """Check connectivity. Returns (False, None) if no API key configured."""
        ...
```

Implementation details:
- Uses `httpx.AsyncClient` with 30-second timeout
- Endpoint: `https://openrouter.ai/api/v1/chat/completions`
- Headers: `Authorization: Bearer {api_key}`, `HTTP-Referer: https://fortress.local`, `X-Title: Fortress`
- Request body follows OpenAI chat completions format:
  ```json
  {
    "model": "meta-llama/llama-3.1-70b-instruct:free",
    "messages": [
      {"role": "system", "content": "<system_prompt>"},
      {"role": "user", "content": "<prompt>"}
    ]
  }
  ```
- Logs every request: model, prompt_len, response time
- Returns `HEBREW_FALLBACK` on timeout, HTTP error, connection error, or any exception
- `is_available` sends a lightweight models list request to verify connectivity; returns `(False, None)` immediately if API key is empty

### 2. RoutingPolicy (`fortress/src/services/routing_policy.py`)

Pure functions with no external dependencies:

```python
SensitivityLevel = Literal["low", "medium", "high"]
Provider = Literal["openrouter", "bedrock", "ollama"]

SENSITIVITY_MAP: dict[str, SensitivityLevel] = {
    "greeting": "low",
    "list_tasks": "medium",
    "create_task": "medium",
    "complete_task": "medium",
    "list_documents": "medium",
    "unknown": "medium",
    "ask_question": "high",
    "upload_document": "high",
}

ROUTE_MAP: dict[SensitivityLevel, list[Provider]] = {
    "low": ["openrouter", "bedrock", "ollama"],
    "medium": ["openrouter", "bedrock", "ollama"],
    "high": ["bedrock", "ollama"],
}

def get_sensitivity(intent: str) -> SensitivityLevel:
    """Return the sensitivity level for an intent. Defaults to 'high' for unknown intents."""
    ...

def get_route(intent: str) -> list[Provider]:
    """Return the ordered provider list for an intent."""
    ...
```

Design decision: Unknown/unrecognized intents default to "high" sensitivity (fail-safe). This ensures any new intent added in the future won't accidentally route to OpenRouter until explicitly classified.

### 3. ModelDispatcher (`fortress/src/services/model_dispatch.py`)

```python
class ModelDispatcher:
    def __init__(
        self,
        bedrock_client: BedrockClient | None = None,
        openrouter_client: OpenRouterClient | None = None,
        ollama_client: OllamaClient | None = None,
    ) -> None: ...

    async def dispatch(
        self,
        prompt: str,
        system_prompt: str,
        intent: str,
        context: dict | None = None,
    ) -> str:
        """Try providers in routing order until one succeeds.
        Returns HEBREW_FALLBACK if all fail."""
        ...
```

Dispatch logic:
1. Call `get_route(intent)` to get ordered provider list
2. For each provider in order:
   - **"openrouter"**: Skip if `OPENROUTER_API_KEY` is empty. Call `OpenRouterClient.generate()`. If result equals `HEBREW_FALLBACK`, treat as failure and continue.
   - **"bedrock"**: Call `BedrockClient.generate()` with model="sonnet" if intent is "ask_question", else model="haiku". If result equals `HEBREW_FALLBACK`, treat as failure and continue.
   - **"ollama"**: Call `OllamaClient.generate()`. If result equals `HEBREW_FALLBACK`, treat as failure and continue.
3. If all providers fail, return `HEBREW_FALLBACK`
4. Log each attempt: intent, provider, success/failure

### 4. Workflow Engine Changes (`fortress/src/services/workflow_engine.py`)

The `action_node` function changes from directly instantiating `BedrockClient` to using `ModelDispatcher`:

```python
async def action_node(state: WorkflowState) -> dict:
    intent = state["intent"]
    # ... handler dispatch remains the same ...
    # But handlers receive ModelDispatcher instead of BedrockClient
```

Each action handler's signature changes from accepting `bedrock: BedrockClient` to accepting `dispatcher: ModelDispatcher`. The handlers call `dispatcher.dispatch(prompt, system_prompt, intent)` instead of `bedrock.generate(prompt, system_prompt, model)`.

Exception: `memory_save_node` continues to instantiate `BedrockClient` directly, since memory extraction is always sensitive.

### 5. Health Endpoint Changes (`fortress/src/routers/health.py`)

Add OpenRouter status check:

```python
@router.get("/health")
async def health() -> dict:
    # ... existing checks ...

    # OpenRouter check
    openrouter_api_key = OPENROUTER_API_KEY
    if not openrouter_api_key:
        openrouter_status = "no_key"
        openrouter_model = "not configured"
    else:
        client = OpenRouterClient()
        ok, model = await client.is_available()
        openrouter_status = "connected" if ok else "disconnected"
        openrouter_model = model or "not available"

    return {
        # ... existing fields ...
        "openrouter": openrouter_status,
        "openrouter_model": openrouter_model,
    }
```

### 6. Config Changes (`fortress/src/config.py`)

```python
# OpenRouter
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-70b-instruct:free")
OPENROUTER_FALLBACK_MODEL: str = os.getenv("OPENROUTER_FALLBACK_MODEL", "google/gemma-2-9b-it:free")
```

## Data Models

No new database tables or schema changes. The feature operates entirely at the service layer.

Existing data flow is preserved:
- `Conversation` records still store `intent` field (unchanged)
- `Memory` records still extracted by Bedrock (unchanged)
- All existing ORM models remain untouched

### Configuration Data

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `OPENROUTER_API_KEY` | str | `""` | OpenRouter API key (empty = disabled) |
| `OPENROUTER_MODEL` | str | `meta-llama/llama-3.1-70b-instruct:free` | Primary OpenRouter model |
| `OPENROUTER_FALLBACK_MODEL` | str | `google/gemma-2-9b-it:free` | Fallback OpenRouter model |

### Sensitivity Classification

| Intent | Sensitivity | Provider Order |
|--------|------------|----------------|
| greeting | low | openrouter → bedrock → ollama |
| list_tasks | medium | openrouter → bedrock → ollama |
| create_task | medium | openrouter → bedrock → ollama |
| complete_task | medium | openrouter → bedrock → ollama |
| list_documents | medium | openrouter → bedrock → ollama |
| unknown | medium | openrouter → bedrock → ollama |
| ask_question | high | bedrock → ollama |
| upload_document | high | bedrock → ollama |


## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

Since this feature uses unit tests exclusively (no property-based testing), the correctness properties below are verified through specific example-based tests.

### Property 1: High sensitivity intents never route to OpenRouter

*For any* intent classified as "high" sensitivity (ask_question, upload_document), the provider list returned by `get_route()` must never contain "openrouter".

**Validates: Requirements 3.4, 3.7, 3.10**

### Property 2: OpenRouter client returns Hebrew fallback on all error types

*For any* error condition (timeout, HTTP error, connection error, unexpected exception), `OpenRouterClient.generate()` must return the Hebrew fallback message `"מצטער, לא הצלחתי לעבד את הבקשה. נסה שוב."`.

**Validates: Requirements 1.7**

### Property 3: Dispatcher fallback chain exhaustion returns Hebrew fallback

*For any* intent, if all providers in the routing order fail (return Hebrew fallback), `ModelDispatcher.dispatch()` must return the Hebrew fallback message.

**Validates: Requirements 4.6**

### Property 4: Dispatcher treats Hebrew fallback response as failure

*For any* provider that returns the Hebrew fallback string, the dispatcher must treat it as a failure and proceed to the next provider in the chain.

**Validates: Requirements 4.8**

### Property 5: Bedrock model selection per intent

*For any* dispatch where the provider is "bedrock", the model must be "sonnet" when intent is "ask_question" and "haiku" for all other intents.

**Validates: Requirements 4.4, 4.5**

### Property 6: Empty API key skips OpenRouter

*For any* dispatch call when `OPENROUTER_API_KEY` is empty, the dispatcher must skip the "openrouter" provider without making any HTTP requests and proceed to the next provider.

**Validates: Requirements 8.1, 8.2, 8.3**

### Property 7: Every intent maps to exactly one sensitivity level

*For any* known intent string, `get_sensitivity()` returns exactly one of "low", "medium", or "high".

**Validates: Requirements 3.1**

### Property 8: OpenRouter request format compliance

*For any* call to `OpenRouterClient.generate()`, the HTTP request must include the Authorization header, HTTP-Referer header, X-Title header set to "Fortress", and use the OpenAI-compatible chat completions body format.

**Validates: Requirements 1.3, 1.4**

### Property 9: Health endpoint reports correct OpenRouter status

*For any* state of the OpenRouter configuration (no key, key + reachable, key + unreachable), the health endpoint must report the correct `openrouter` field value ("no_key", "connected", or "disconnected") and the correct `openrouter_model` field.

**Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5**

### Property 10: memory_save_node uses Bedrock directly

*For any* workflow execution, `memory_save_node` must use `BedrockClient` directly and never route through `ModelDispatcher`.

**Validates: Requirements 5.4**

## Error Handling

### OpenRouterClient Errors

| Error Type | Handling | Result |
|-----------|----------|--------|
| `httpx.TimeoutException` | Log error, return fallback | `HEBREW_FALLBACK` |
| `httpx.HTTPStatusError` (4xx/5xx) | Log status code, return fallback | `HEBREW_FALLBACK` |
| `httpx.ConnectError` | Log connection failure, return fallback | `HEBREW_FALLBACK` |
| Any other `Exception` | Log with traceback, return fallback | `HEBREW_FALLBACK` |
| Empty API key on `generate()` | Return fallback immediately (no HTTP call) | `HEBREW_FALLBACK` |
| Empty API key on `is_available()` | Return `(False, None)` immediately | No HTTP call |

### ModelDispatcher Errors

| Scenario | Handling | Result |
|----------|----------|--------|
| First provider fails | Log failure, try next provider | Continue chain |
| Provider returns `HEBREW_FALLBACK` | Treat as failure, try next | Continue chain |
| All providers fail | Log exhaustion | Return `HEBREW_FALLBACK` |
| OpenRouter skipped (no key) | Log skip, proceed to next | Continue chain |
| Unexpected exception in dispatch | Catch, log, return fallback | `HEBREW_FALLBACK` |

### Health Endpoint Errors

| Scenario | Handling | Result |
|----------|----------|--------|
| No API key | Skip HTTP check | `"no_key"` |
| OpenRouter unreachable | Catch exception | `"disconnected"` |
| OpenRouter reachable | Report status | `"connected"` |

All error handling follows the existing Fortress pattern: catch broadly, log specifically, return Hebrew fallback. The system never crashes or returns 500 errors to WAHA.

## Testing Strategy

All tests use **unit testing only** with `pytest` and `pytest-asyncio`. No property-based testing. All external API calls (OpenRouter, Bedrock, Ollama) are mocked using `unittest.mock`.

### Test Files

#### `fortress/tests/test_openrouter_client.py`

Tests for `OpenRouterClient`:
- Successful generation: mock httpx to return valid response, verify returned text
- Timeout handling: mock httpx to raise `TimeoutException`, verify `HEBREW_FALLBACK` returned
- HTTP error handling: mock httpx to return 500, verify `HEBREW_FALLBACK` returned
- Connection error: mock httpx to raise `ConnectError`, verify `HEBREW_FALLBACK` returned
- `is_available` with valid key: mock successful HTTP response, verify `(True, model_name)`
- `is_available` with empty key: verify `(False, None)` returned without HTTP call
- Request headers: verify Authorization, HTTP-Referer, X-Title headers are sent
- Default model used when none specified
- Custom model used when explicitly provided
- Empty API key on generate returns fallback without HTTP call

#### `fortress/tests/test_routing_policy.py`

Tests for `RoutingPolicy`:
- `get_sensitivity("greeting")` returns `"low"`
- `get_sensitivity("list_tasks")` returns `"medium"` (and other medium intents)
- `get_sensitivity("ask_question")` returns `"high"` (and upload_document)
- `get_route("greeting")` returns `["openrouter", "bedrock", "ollama"]`
- `get_route("list_tasks")` returns `["openrouter", "bedrock", "ollama"]`
- `get_route("ask_question")` returns `["bedrock", "ollama"]`
- `get_route("upload_document")` returns `["bedrock", "ollama"]`
- High sensitivity routes never contain "openrouter"
- Unknown/unrecognized intent defaults to "high" sensitivity
- Every known intent has a sensitivity mapping

#### `fortress/tests/test_model_dispatch.py`

Tests for `ModelDispatcher`:
- Successful dispatch to first provider (openrouter succeeds)
- Fallback: openrouter fails → bedrock succeeds
- Fallback: openrouter fails → bedrock fails → ollama succeeds
- All providers fail → returns `HEBREW_FALLBACK`
- Hebrew fallback response from provider treated as failure
- High sensitivity intent skips openrouter, goes to bedrock
- `ask_question` intent uses bedrock sonnet model
- Non-ask_question intent uses bedrock haiku model
- Empty API key skips openrouter provider
- Dispatch logs each attempt (verify log calls)

#### `fortress/tests/test_health.py` (updated)

Add tests alongside existing ones:
- OpenRouter connected: mock `is_available` returning `(True, model_name)`, verify `"connected"` and model name in response
- OpenRouter disconnected: mock `is_available` returning `(False, None)`, verify `"disconnected"` in response
- OpenRouter no key: mock empty `OPENROUTER_API_KEY`, verify `"no_key"` and `"not configured"` in response
- All existing 8 health tests continue to pass unchanged

### Test Constraints

- All external HTTP calls mocked (httpx for OpenRouter, boto3 for Bedrock, httpx for Ollama)
- No real network requests in any test
- All 91 existing tests must continue to pass
- New tests follow existing patterns in `conftest.py` (TestClient, mock_db fixtures)
- Each test file is independent and can run in isolation
