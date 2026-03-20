# Requirements Document

## Introduction

Phase 4B upgrades Fortress from a local-only Ollama LLM backend to a hybrid architecture using AWS Bedrock (Claude 3.5 Haiku/Sonnet) for Hebrew generation, LangGraph for workflow orchestration, and a three-tier memory system. The local Ollama model is demoted to English-only intent classification. This phase also fixes the ADMIN_PHONE vs SYSTEM_PHONE confusion and the echo prevention logic in the WhatsApp webhook.

## Glossary

- **Fortress**: The FastAPI application container serving as the family intelligence system
- **Bedrock_Client**: The async service that communicates with AWS Bedrock runtime API to invoke Claude models
- **Ollama_Client**: The existing async HTTP client for the local Ollama LLM, used only for English intent classification after this phase
- **Workflow_Engine**: The LangGraph-based StateGraph that orchestrates message processing through a sequence of nodes (intent → permission → memory load → action → response → memory save → conversation save)
- **Memory_Service**: The service responsible for saving, loading, filtering, and expiring memory records while enforcing exclusion rules
- **Memory**: A database record storing a contextual fact extracted from a conversation, with a tier (short/medium/long/permanent), a category (preference/goal/fact/habit/context), and optional expiration
- **Memory_Exclusion**: A database record defining a pattern that must never be stored as a memory (e.g., passwords, credit card numbers, PII)
- **Intent_Detector**: The service that classifies incoming messages into intent categories using keyword matching with Ollama LLM fallback
- **Message_Handler**: The thin authentication layer that identifies the sender and delegates to the Workflow_Engine
- **Model_Router**: The existing intent-based dispatch service, replaced by Workflow_Engine in this phase
- **WAHA**: The self-hosted WhatsApp Web bridge container that receives and sends WhatsApp messages
- **Health_Endpoint**: The GET /health API endpoint reporting system component status
- **ADMIN_PHONE**: The phone number of the family administrator (human)
- **SYSTEM_PHONE**: The phone number of the Fortress WhatsApp account (the bot's own number)

## Requirements

### Requirement 1: AWS Bedrock Client

**User Story:** As the Fortress system, I want to call AWS Bedrock Claude models for Hebrew text generation, so that responses are coherent and high-quality in Hebrew.

#### Acceptance Criteria

1. THE Bedrock_Client SHALL expose an async `generate` method accepting a prompt string, an optional system_prompt string, and a model selector string defaulting to "haiku"
2. WHEN the model selector is "haiku", THE Bedrock_Client SHALL invoke the Bedrock model ID `anthropic.claude-3-5-haiku-20241022-v1:0`
3. WHEN the model selector is "sonnet", THE Bedrock_Client SHALL invoke the Bedrock model ID `anthropic.claude-3-5-sonnet-20241022-v2:0`
4. THE Bedrock_Client SHALL read AWS credentials from environment variables or the `~/.aws/credentials` file using the profile name "fortress"
5. THE Bedrock_Client SHALL set a 30-second timeout on all Bedrock API calls
6. IF a Bedrock API call fails or times out, THEN THE Bedrock_Client SHALL return the Hebrew fallback message "מצטער, לא הצלחתי לעבד את הבקשה. נסה שוב."
7. THE Bedrock_Client SHALL log each request with the model name, prompt length, and response time in seconds
8. THE Bedrock_Client SHALL expose an async `is_available` method that returns a boolean indicating whether Bedrock is reachable
9. THE Bedrock_Client SHALL use type hints on all method signatures and return types
10. THE Bedrock_Client SHALL use the boto3 `bedrock-runtime` client to invoke models

### Requirement 2: Configuration Updates

**User Story:** As a developer, I want all AWS and phone identity settings centralized in config.py, so that deployment configuration is consistent and clear.

#### Acceptance Criteria

1. THE Fortress config module SHALL expose an `AWS_REGION` variable defaulting to "us-east-1"
2. THE Fortress config module SHALL expose an `AWS_PROFILE` variable defaulting to "fortress"
3. THE Fortress config module SHALL expose a `BEDROCK_HAIKU_MODEL` variable defaulting to "anthropic.claude-3-5-haiku-20241022-v1:0"
4. THE Fortress config module SHALL expose a `BEDROCK_SONNET_MODEL` variable defaulting to "anthropic.claude-3-5-sonnet-20241022-v2:0"
5. THE Fortress config module SHALL expose a `SYSTEM_PHONE` variable (the bot's own WhatsApp number) distinct from `ADMIN_PHONE` (the human administrator's number)
6. THE Fortress .env.example file SHALL include entries for AWS_REGION, AWS_PROFILE, SYSTEM_PHONE, and ADMIN_PHONE with descriptive comments

### Requirement 3: Echo Prevention Fix

**User Story:** As the Fortress system, I want to use the WAHA `fromMe` field for echo prevention instead of phone number comparison, so that the bot reliably ignores its own outgoing messages.

#### Acceptance Criteria

1. WHEN the WAHA payload contains `fromMe` set to true, THE WhatsApp webhook handler SHALL ignore the message and return status "ignored" with reason "echo"
2. THE WhatsApp webhook handler SHALL remove the existing phone-based echo prevention that compares the sender phone to ADMIN_PHONE
3. THE WhatsApp webhook handler SHALL continue to process messages where `fromMe` is false or absent

### Requirement 4: Memory Database Schema

**User Story:** As the Fortress system, I want database tables for storing conversational memories and exclusion patterns, so that the memory system has persistent storage.

#### Acceptance Criteria

1. THE migration file SHALL create a `memories` table with columns: id (UUID primary key), family_member_id (UUID foreign key to family_members), content (TEXT), category (TEXT NOT NULL with CHECK constraint allowing only 'preference', 'goal', 'fact', 'habit', 'context'), memory_type (TEXT NOT NULL with CHECK constraint allowing only 'short', 'medium', 'long', 'permanent'), expires_at (TIMESTAMPTZ nullable), source (TEXT with CHECK constraint allowing only 'conversation', 'document', 'manual', 'system'), confidence (NUMERIC default 1.0), last_accessed_at (TIMESTAMPTZ nullable), access_count (INT default 0), is_active (BOOLEAN default true), metadata (JSONB default '{}'), created_at (TIMESTAMPTZ default now())
2. THE migration file SHALL create a `memory_exclusions` table with columns: id (UUID primary key), pattern (TEXT NOT NULL), description (TEXT), exclusion_type (TEXT NOT NULL with CHECK constraint allowing only 'keyword', 'category', 'regex'), family_member_id (UUID nullable foreign key to family_members, null means applies to all members), is_active (BOOLEAN default true), created_at (TIMESTAMPTZ default now())
3. THE migration file SHALL insert default exclusion patterns for: credit card numbers, passwords (Hebrew and English), PIN codes, ID numbers, access codes, credentials, and secrets
4. THE migration file SHALL create indexes on memories(family_member_id), memories(memory_type), memories(category), memories(expires_at), memories(is_active), memory_exclusions(is_active), and memory_exclusions(exclusion_type)
5. THE migration file SHALL enforce a CHECK constraint on memories.memory_type allowing only 'short', 'medium', 'long', or 'permanent' values
6. THE migration file SHALL enforce a CHECK constraint on memories.category allowing only 'preference', 'goal', 'fact', 'habit', or 'context' values

### Requirement 5: Memory ORM Models

**User Story:** As a developer, I want SQLAlchemy ORM models for the memory tables, so that the memory service can interact with the database using the same patterns as existing models.

#### Acceptance Criteria

1. THE Memory ORM model SHALL use SQLAlchemy 2.0 `mapped_column` style consistent with existing models in schema.py
2. THE Memory ORM model SHALL define a relationship to FamilyMember via the family_member_id foreign key
3. THE MemoryExclusion ORM model SHALL use SQLAlchemy 2.0 `mapped_column` style consistent with existing models in schema.py
4. THE FamilyMember ORM model SHALL define a reverse relationship to Memory records

### Requirement 6: Memory Service

**User Story:** As the Fortress system, I want a memory service that saves, loads, filters, and expires memories while enforcing exclusion rules, so that the AI can maintain conversational context without storing sensitive data.

#### Acceptance Criteria

1. THE Memory_Service SHALL expose a `save_memory` function that creates a Memory record in the database after passing exclusion checks
2. WHEN a memory content string matches any active Memory_Exclusion pattern, THE Memory_Service `save_memory` function SHALL reject the memory and return None
3. THE Memory_Service SHALL expose a `load_memories` function that returns active, non-expired memories for a given family member, ordered by last_accessed_at DESC then created_at DESC
4. THE Memory_Service SHALL expose a `cleanup_expired` function that deletes all Memory records where expires_at is in the past
5. THE Memory_Service SHALL expose an `extract_memories_from_message` function that uses Bedrock_Client to identify facts worth remembering from a conversation exchange
6. THE Memory_Service `save_memory` function SHALL calculate expires_at based on memory_type: "short" with 7-day expiry, "medium" with 90-day expiry, "long" with 365-day expiry, and "permanent" with no expiry (null expires_at)
7. THE Memory_Service `extract_memories_from_message` function SHALL assign memory_type "short" for transient context, "medium" for recurring preferences, "long" for important facts, and "permanent" for critical facts (allergies, birthdays, family relationships)
8. THE Memory_Service `load_memories` function SHALL update last_accessed_at to the current timestamp and increment access_count for each returned memory, enabling relevance-based ranking
9. THE Memory_Service `check_exclusion` function SHALL support exclusion_type "keyword" with case-insensitive substring matching and exclusion_type "regex" with re.search matching; exclusion_type "category" SHALL NOT be used for content matching (reserved for manual tagging)
10. THE Memory_Service SHALL use type hints on all function signatures and return types

### Requirement 7: LangGraph Workflow Engine

**User Story:** As the Fortress system, I want a LangGraph-based workflow engine replacing the model_router, so that message processing follows a structured, extensible graph of nodes with clear state transitions.

#### Acceptance Criteria

1. THE Workflow_Engine SHALL define a LangGraph StateGraph with nodes: intent_node, permission_node, memory_load_node, action_node, response_node, memory_save_node, and conversation_save_node
2. THE Workflow_Engine intent_node SHALL use the existing Intent_Detector with Ollama_Client for English-only intent classification
3. THE Workflow_Engine permission_node SHALL check permissions using the existing auth service and return a Hebrew denial message when access is denied
4. THE Workflow_Engine memory_load_node SHALL call Memory_Service.load_memories to retrieve relevant context for the current family member
5. THE Workflow_Engine action_node SHALL dispatch to the appropriate handler based on detected intent, using Bedrock_Client for all Hebrew text generation
6. WHEN the intent is a simple task (greeting, task confirmation, unknown), THE Workflow_Engine action_node SHALL use the Bedrock Haiku model
7. WHEN the intent is a complex question (ask_question), THE Workflow_Engine action_node SHALL use the Bedrock Sonnet model
8. THE Workflow_Engine memory_save_node SHALL call Memory_Service.extract_memories_from_message and save extracted memories
9. THE Workflow_Engine conversation_save_node SHALL save the conversation record to the database with the detected intent
10. THE Workflow_Engine SHALL expose a `run_workflow` async function accepting the same parameters as the existing `route_message` function
11. IF any node in the Workflow_Engine raises an exception, THEN THE Workflow_Engine SHALL return the Hebrew fallback message and log the error

### Requirement 8: Message Handler Integration

**User Story:** As a developer, I want the message handler to call the new Workflow_Engine instead of the old model_router, so that all messages flow through the LangGraph pipeline.

#### Acceptance Criteria

1. THE Message_Handler SHALL import and call `run_workflow` from the Workflow_Engine instead of `route_message` from the Model_Router
2. THE Message_Handler SHALL preserve the existing authentication logic (unknown phone rejection, inactive member rejection)
3. THE Message_Handler SHALL pass all existing parameters (db, member, phone, message_text, has_media, media_file_path) to the Workflow_Engine

### Requirement 9: System Prompts for Bedrock

**User Story:** As the Fortress system, I want dedicated prompt templates for Bedrock-powered memory extraction and task extraction, so that Claude models produce structured, reliable output.

#### Acceptance Criteria

1. THE system_prompts module SHALL include a `MEMORY_EXTRACTOR` prompt that instructs the model to extract facts from a conversation and return a JSON array with fields: content, memory_type, and confidence
2. THE system_prompts module SHALL include a `TASK_EXTRACTOR_BEDROCK` prompt that instructs the model to extract task details from Hebrew text and return a JSON object with fields: title, due_date, category, and priority
3. THE `TASK_EXTRACTOR_BEDROCK` prompt SHALL specify that the model must handle Hebrew input and produce Hebrew output for the title field
4. THE existing prompts (FORTRESS_BASE, INTENT_CLASSIFIER, TASK_EXTRACTOR, TASK_RESPONDER) SHALL remain unchanged for backward compatibility

### Requirement 10: Docker Compose Updates

**User Story:** As a developer deploying Fortress, I want the Docker Compose file to mount AWS credentials into the fortress container, so that Bedrock_Client can authenticate with AWS.

#### Acceptance Criteria

1. THE Docker Compose fortress service SHALL mount `~/.aws` from the host as a read-only volume at `/root/.aws` inside the container
2. THE Docker Compose fortress service SHALL include the `AWS_REGION` and `AWS_PROFILE` environment variables
3. THE Docker Compose fortress service SHALL include the `SYSTEM_PHONE` environment variable
4. THE existing Docker Compose services (db, ollama, waha) SHALL remain unchanged

### Requirement 11: Health Endpoint Updates

**User Story:** As an operator, I want the health endpoint to report Bedrock connectivity status alongside Ollama and database status, so that I can monitor all AI backends.

#### Acceptance Criteria

1. THE Health_Endpoint SHALL include a "bedrock" field reporting "connected" or "disconnected" based on Bedrock_Client.is_available()
2. THE Health_Endpoint SHALL continue to report "ollama" and "database" status as before
3. THE Health_Endpoint SHALL report the Bedrock model name when connected

### Requirement 12: Test Coverage

**User Story:** As a developer, I want comprehensive tests for all new components with mocked AWS calls, so that the test suite validates behavior without requiring real cloud services.

#### Acceptance Criteria

1. THE test suite SHALL include tests for Bedrock_Client.generate covering successful response, timeout fallback, and error fallback scenarios
2. THE test suite SHALL include tests for Bedrock_Client.is_available covering reachable and unreachable scenarios
3. THE test suite SHALL include tests for Memory_Service.save_memory covering successful save and exclusion rejection
4. THE test suite SHALL include tests for Memory_Service.load_memories covering filtering by member and excluding expired records
5. THE test suite SHALL include tests for Memory_Service.extract_memories_from_message covering successful extraction
6. THE test suite SHALL include tests for Workflow_Engine.run_workflow covering the greeting, list_tasks, create_task, and permission_denied flows
7. THE test suite SHALL mock all boto3 and AWS calls so that no real Bedrock invocations occur during testing
8. THE existing 89 tests SHALL continue to pass without modification, or with minimal updates to accommodate the model_router-to-workflow import change
9. THE test suite SHALL include a test verifying that the updated message handler delegates to `run_workflow` instead of `route_message`

### Requirement 13: Documentation Updates

**User Story:** As a developer or operator, I want updated documentation reflecting the new architecture, so that onboarding and troubleshooting are accurate.

#### Acceptance Criteria

1. THE README.md SHALL describe the hybrid AI architecture (Bedrock for Hebrew generation, Ollama for intent classification)
2. THE docs/architecture.md SHALL include an updated message flow diagram showing the LangGraph workflow nodes
3. THE docs/architecture.md SHALL document the Memory_Service and its three-tier memory model
4. THE docs/setup.md SHALL include AWS credential configuration steps (IAM user, profile setup, required Bedrock model access)
5. THE docs/setup.md SHALL document the SYSTEM_PHONE vs ADMIN_PHONE distinction

### Requirement 14: New Python Dependencies

**User Story:** As a developer, I want the required Python packages for AWS and LangGraph added to requirements.txt, so that the application can be built and deployed with all dependencies.

#### Acceptance Criteria

1. THE requirements.txt SHALL include boto3 version 1.35.0
2. THE requirements.txt SHALL include langchain version 0.3.0
3. THE requirements.txt SHALL include langchain-aws version 0.2.0
4. THE requirements.txt SHALL include langchain-community version 0.3.0
5. THE requirements.txt SHALL include langgraph version 0.2.0
6. THE existing dependencies in requirements.txt SHALL remain unchanged
