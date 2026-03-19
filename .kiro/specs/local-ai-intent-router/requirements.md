# Requirements Document

## Introduction

Phase 4A adds local AI capabilities to Fortress by integrating Ollama as a local LLM service and replacing the hardcoded keyword-based message handler with an AI-powered intent detection and model routing system. The architecture supports future multi-model routing (e.g., Bedrock) but routes all requests to the local Ollama model for now. The system runs on a Mac Mini M4 (24GB RAM) alongside the existing three Docker services.

## Glossary

- **Fortress_App**: The FastAPI application container (fortress-app) that processes WhatsApp messages and manages household data
- **Ollama_Service**: The Ollama Docker container (fortress-ollama) providing local LLM inference via REST API on port 11434
- **Intent_Detector**: Service that classifies incoming WhatsApp messages into predefined intent categories using keyword matching and LLM fallback
- **Model_Router**: Service that receives a detected intent, resolves the appropriate model tier, checks permissions, dispatches to the correct handler, and returns a response
- **LLM_Client**: Async HTTP client that communicates with the Ollama REST API for text generation
- **Setup_Script**: Bash script (`scripts/setup_ollama.sh`) that waits for Ollama readiness and pulls the required model
- **System_Prompts**: Predefined prompt templates stored in `src/prompts/` that guide LLM behavior for intent classification, task extraction, and response generation
- **Intent**: A classified category representing the user's goal (e.g., list_tasks, create_task, greeting, ask_question)
- **Model_Tier**: A routing label (currently only "local") that maps an intent to a specific LLM backend
- **Health_Endpoint**: The GET /health API endpoint that reports system component status
- **Conversation_Record**: A row in the conversations table storing the incoming message, outgoing response, and detected intent

## Requirements

### Requirement 1: Ollama Docker Service Integration

**User Story:** As a system administrator, I want Ollama running as a Docker Compose service, so that the Fortress application has access to a local LLM without external API dependencies.

#### Acceptance Criteria

1. THE docker-compose.yml SHALL include an ollama service using the `ollama/ollama:latest` image with container name `fortress-ollama`, restart policy `unless-stopped`, port mapping `11434:11434`, volume `ollama_data:/root/.ollama`, and memory reservation of 6GB
2. THE docker-compose.yml SHALL declare `ollama_data` as a named volume
3. THE Fortress_App service environment SHALL include `OLLAMA_API_URL=http://ollama:11434`
4. THE .env.example file SHALL include `OLLAMA_API_URL` and `OLLAMA_MODEL` variables

### Requirement 2: Ollama Model Setup Script

**User Story:** As a system administrator, I want an automated setup script, so that the required LLM model is pulled and verified after the Ollama container starts.

#### Acceptance Criteria

1. THE Setup_Script SHALL be located at `scripts/setup_ollama.sh` and be executable
2. WHEN executed, THE Setup_Script SHALL wait for the Ollama_Service container to become ready by polling the Ollama API health endpoint
3. WHEN the Ollama_Service is ready, THE Setup_Script SHALL pull the `llama3.1:8b` model
4. AFTER pulling the model, THE Setup_Script SHALL verify the model is available by querying the Ollama API model list
5. WHEN the setup succeeds, THE Setup_Script SHALL print a success message to stdout
6. IF the Ollama_Service does not become ready within a timeout period, THEN THE Setup_Script SHALL print a failure message to stderr and exit with a non-zero code
7. IF the model pull fails, THEN THE Setup_Script SHALL print a failure message to stderr and exit with a non-zero code

### Requirement 3: Ollama Configuration

**User Story:** As a developer, I want Ollama connection settings managed through environment variables, so that the LLM endpoint and model are configurable without code changes.

#### Acceptance Criteria

1. THE Fortress_App config module SHALL expose an `OLLAMA_API_URL` setting with default value `http://localhost:11434`
2. THE Fortress_App config module SHALL expose an `OLLAMA_MODEL` setting with default value `llama3.1:8b`

### Requirement 4: Intent Detection

**User Story:** As a family member, I want my WhatsApp messages understood by intent rather than exact keywords, so that I can communicate naturally in Hebrew or English.

#### Acceptance Criteria

1. THE Intent_Detector SHALL define an INTENTS dictionary mapping each intent name to a Model_Tier value, containing at minimum: `list_tasks`, `create_task`, `complete_task`, `greeting`, `upload_document`, `list_documents`, `ask_question`, and `unknown`, all mapped to the `local` tier
2. WHEN a message contains the Hebrew keyword `משימות` or the English keyword `tasks`, THE Intent_Detector SHALL classify the intent as `list_tasks`
3. WHEN a message starts with `משימה חדשה:` or `new task:`, THE Intent_Detector SHALL classify the intent as `create_task`
4. WHEN a message contains `סיום משימה`, `done`, or `בוצע`, THE Intent_Detector SHALL classify the intent as `complete_task`
5. WHEN a message contains `שלום`, `היי`, `hello`, or `בוקר טוב`, THE Intent_Detector SHALL classify the intent as `greeting`
6. WHEN a message contains `מסמכים` or `documents`, THE Intent_Detector SHALL classify the intent as `list_documents`
7. WHEN the message has associated media, THE Intent_Detector SHALL classify the intent as `upload_document`
8. WHEN no keyword match is found, THE Intent_Detector SHALL fall back to LLM-based classification by sending the message to the Ollama_Service with an intent classification prompt
9. IF the LLM-based classification fails or times out, THEN THE Intent_Detector SHALL return the `unknown` intent

### Requirement 5: Local LLM Client

**User Story:** As a developer, I want a dedicated async client for Ollama API communication, so that LLM calls are centralized with consistent timeout and error handling.

#### Acceptance Criteria

1. THE LLM_Client SHALL send generation requests to the Ollama_Service via HTTP POST to the `/api/generate` endpoint, including prompt, system_prompt, and context parameters
2. THE LLM_Client SHALL use `httpx.AsyncClient` with a 30-second timeout for all requests
3. THE LLM_Client SHALL provide an `is_available` method that queries the Ollama `/api/tags` endpoint and verifies the configured model is listed
4. IF a generation request fails due to timeout, THEN THE LLM_Client SHALL log the error and return a Hebrew fallback message
5. IF a generation request fails due to connection error, THEN THE LLM_Client SHALL log the error and return a Hebrew fallback message

### Requirement 6: Model Router

**User Story:** As a family member, I want my messages routed to the appropriate handler based on intent, so that I receive accurate and context-aware responses in Hebrew.

#### Acceptance Criteria

1. THE Model_Router SHALL accept a database session, phone number, message text, has_media flag, and optional media_url, and return a response string
2. WHEN a message is received, THE Model_Router SHALL detect the intent using the Intent_Detector, look up the Model_Tier, identify the family member, check permissions, route to the appropriate handler, save the Conversation_Record, and return the response
3. WHEN the intent is `list_tasks`, THE Model_Router SHALL check read permission on the `tasks` resource, retrieve open tasks, and use the LLM_Client to generate a natural Hebrew response listing the tasks
4. WHEN the intent is `create_task`, THE Model_Router SHALL check write permission on the `tasks` resource, use the LLM_Client to extract task details (title, optional due date, optional category) from the natural language message, create the task, and return a Hebrew confirmation
5. WHEN the intent is `complete_task`, THE Model_Router SHALL check write permission on the `tasks` resource, identify the target task, mark it complete, and return a Hebrew confirmation
6. WHEN the intent is `greeting`, THE Model_Router SHALL use the LLM_Client to generate a friendly Hebrew greeting that includes the family member name
7. WHEN the intent is `upload_document`, THE Model_Router SHALL check write permission on the `documents` resource and delegate to the existing document processing flow
8. WHEN the intent is `list_documents`, THE Model_Router SHALL check read permission on the `documents` resource and return a Hebrew summary of recent documents
9. WHEN the intent is `ask_question`, THE Model_Router SHALL use the LLM_Client to generate a Hebrew response based on available context
10. WHEN the intent is `unknown`, THE Model_Router SHALL return a Hebrew message indicating the request was not understood and suggesting available commands
11. IF a permission check fails, THEN THE Model_Router SHALL log the denial via the audit service and return a Hebrew permission-denied message
12. THE Model_Router SHALL save a Conversation_Record for every processed message, including the detected intent

### Requirement 7: Message Handler Refactoring

**User Story:** As a developer, I want the message handler to be a thin routing layer, so that message processing logic is cleanly separated into the intent detector and model router.

#### Acceptance Criteria

1. THE message handler SHALL identify the family member by phone number using the auth service
2. WHEN the phone number is not recognized, THE message handler SHALL return a Hebrew unknown-sender message
3. WHEN the family member is inactive, THE message handler SHALL return a Hebrew inactive-account message
4. WHEN the family member is active, THE message handler SHALL delegate all message processing to the Model_Router
5. THE message handler SHALL not contain any keyword matching or intent detection logic

### Requirement 8: System Prompts

**User Story:** As a developer, I want system prompts organized in a dedicated module, so that LLM behavior is consistent, maintainable, and tuned for Hebrew WhatsApp interactions.

#### Acceptance Criteria

1. THE System_Prompts module SHALL be located in `src/prompts/` directory
2. THE System_Prompts module SHALL define a `FORTRESS_BASE` prompt establishing the system identity as a Hebrew-speaking family assistant for WhatsApp
3. THE System_Prompts module SHALL define an `INTENT_CLASSIFIER` prompt that instructs the LLM to classify messages into the defined intent categories
4. THE System_Prompts module SHALL define a `TASK_EXTRACTOR` prompt that instructs the LLM to extract structured task details (title, due_date, category) from natural language Hebrew messages
5. THE System_Prompts module SHALL define a `TASK_RESPONDER` prompt that instructs the LLM to format task information as concise WhatsApp-appropriate Hebrew messages

### Requirement 9: Health Check Ollama Status

**User Story:** As a system administrator, I want the health endpoint to report Ollama connectivity, so that I can monitor all system dependencies from a single endpoint.

#### Acceptance Criteria

1. THE Health_Endpoint SHALL include an `ollama` field with value `connected` when the Ollama_Service is reachable and the configured model is loaded, or `disconnected` when the Ollama_Service is unreachable
2. THE Health_Endpoint SHALL include an `ollama_model` field with the configured model name when the model is loaded, or `not loaded` when the model is unavailable

### Requirement 10: Test Coverage

**User Story:** As a developer, I want comprehensive tests for all new components, so that the AI integration is verified and regressions are caught.

#### Acceptance Criteria

1. THE test suite SHALL include tests for the Intent_Detector verifying: media messages classify as `upload_document`, keyword messages classify to correct intents, and LLM fallback is invoked when no keyword matches
2. THE test suite SHALL include tests for the Model_Router verifying: messages route to the correct handler per intent, permission-denied responses are returned when access is denied, unknown members receive rejection messages, and Conversation_Records are saved for every interaction
3. THE test suite SHALL include tests for the LLM_Client verifying: correct HTTP payload is sent to Ollama, timeout errors return a Hebrew fallback message, connection errors return a Hebrew fallback message, and `is_available` correctly reports model availability
4. THE test suite SHALL update existing health endpoint tests to verify the `ollama` and `ollama_model` fields are present in the response
5. THE existing 52 tests SHALL continue to pass without modification to their assertions

### Requirement 11: Documentation Updates

**User Story:** As a developer, I want updated documentation reflecting the AI architecture, so that the system design and setup instructions remain accurate.

#### Acceptance Criteria

1. THE README.md SHALL document the Ollama service in the architecture section, include setup script instructions, note the model download requirement, and update the phase status to reflect Phase 4A
2. THE architecture.md SHALL document the Ollama container, Intent_Detector, Model_Router, LLM_Client, System_Prompts module, and the updated message flow from WhatsApp through intent detection to LLM-powered response generation
