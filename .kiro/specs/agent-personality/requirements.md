# Requirements Document

## Introduction

The Agent Personality feature centralises all user-facing Hebrew text into a single personality module (`fortress/src/prompts/personality.py`). Every response the Fortress agent sends — greetings, task confirmations, error messages, permission denials — will originate from this module, ensuring a consistent warm, family-oriented WhatsApp tone. All existing hardcoded Hebrew strings in services will be replaced with personality templates, and every LLM system prompt will be prefixed with the personality definition.

## Glossary

- **Personality_Module**: The Python module `fortress/src/prompts/personality.py` containing the PERSONALITY constant, GREETINGS dict, TEMPLATES dict, and all formatting functions.
- **PERSONALITY**: A Hebrew string constant defining the agent's character traits (warm, family-oriented, WhatsApp-style, concise).
- **GREETINGS**: A dictionary mapping time-of-day ranges to Hebrew greeting strings.
- **TEMPLATES**: A dictionary mapping response-type keys to Hebrew template strings used for standard responses.
- **Template_Key**: One of the required keys in TEMPLATES: `task_created`, `task_completed`, `task_list_empty`, `task_list_header`, `document_saved`, `permission_denied`, `unknown_member`, `inactive_member`, `error_fallback`, `cant_understand`.
- **Workflow_Engine**: The LangGraph-based workflow engine at `fortress/src/services/workflow_engine.py`.
- **Unified_Handler**: The unified classify-and-respond handler at `fortress/src/services/unified_handler.py`.
- **Message_Handler**: The authentication layer at `fortress/src/services/message_handler.py`.
- **System_Prompts**: The LLM prompt templates module at `fortress/src/prompts/system_prompts.py`.
- **Member_Name**: The `name` field of a `FamilyMember` record, used to personalise responses.

## Requirements

### Requirement 1: Personality Module Definition

**User Story:** As a developer, I want a single personality module that defines the agent's tone, greetings, and response templates, so that all user-facing text is consistent and maintainable.

#### Acceptance Criteria

1. THE Personality_Module SHALL export a PERSONALITY constant containing a Hebrew string that defines the agent's warm, family-oriented, WhatsApp-style character.
2. THE Personality_Module SHALL export a GREETINGS dictionary mapping time-of-day ranges (morning, afternoon, evening, night) to Hebrew greeting strings.
3. THE Personality_Module SHALL export a TEMPLATES dictionary containing all ten Template_Key entries: `task_created`, `task_completed`, `task_list_empty`, `task_list_header`, `document_saved`, `permission_denied`, `unknown_member`, `inactive_member`, `error_fallback`, `cant_understand`.
4. THE Personality_Module SHALL export a `get_greeting(name, hour)` function that accepts a Member_Name and an integer hour (0–23) and returns a personalised Hebrew greeting from GREETINGS.
5. THE Personality_Module SHALL export a `format_task_created(title, due_date)` function that accepts a task title and an optional due date and returns a Hebrew confirmation string using TEMPLATES["task_created"].
6. THE Personality_Module SHALL export a `format_task_list(tasks)` function that accepts a list of task objects and returns a formatted Hebrew task list using TEMPLATES["task_list_header"], with priority emojis (🔴 urgent, 🟡 high, 🟢 normal, ⚪ low).
7. WHEN `format_task_list` receives an empty list, THE Personality_Module SHALL return the TEMPLATES["task_list_empty"] string.

### Requirement 2: Personality Prefix on LLM System Prompts

**User Story:** As a developer, I want every LLM system prompt to include the PERSONALITY prefix, so that the AI model generates responses consistent with the agent's defined character.

#### Acceptance Criteria

1. THE System_Prompts module SHALL import PERSONALITY from the Personality_Module.
2. THE System_Prompts module SHALL prepend PERSONALITY to the FORTRESS_BASE prompt.
3. THE System_Prompts module SHALL prepend PERSONALITY to the UNIFIED_CLASSIFY_AND_RESPOND prompt.
4. THE System_Prompts module SHALL prepend PERSONALITY to the TASK_RESPONDER prompt.

### Requirement 3: Personality Integration in Workflow Engine

**User Story:** As a user, I want the workflow engine to use personality-driven responses for all standard actions, so that every reply feels warm and consistent.

#### Acceptance Criteria

1. WHEN the Workflow_Engine handles a greeting intent via `action_node`, THE Workflow_Engine SHALL use `get_greeting()` from the Personality_Module to generate the response.
2. WHEN the Workflow_Engine creates a task via `action_node`, THE Workflow_Engine SHALL use `format_task_created()` from the Personality_Module to generate the confirmation response.
3. WHEN the Workflow_Engine lists tasks via `action_node`, THE Workflow_Engine SHALL use `format_task_list()` from the Personality_Module to generate the task list response.
4. WHEN the Workflow_Engine encounters an error, THE Workflow_Engine SHALL use TEMPLATES["error_fallback"] from the Personality_Module for the error response.
5. WHEN the Workflow_Engine denies permission, THE Workflow_Engine SHALL use TEMPLATES["permission_denied"] from the Personality_Module for the denial response.
6. WHEN the Workflow_Engine encounters an unknown intent, THE Workflow_Engine SHALL use TEMPLATES["cant_understand"] from the Personality_Module for the response.
7. THE Workflow_Engine SHALL contain zero hardcoded Hebrew response strings outside of Personality_Module references.

### Requirement 4: Personality Integration in Unified Handler

**User Story:** As a user, I want the unified LLM handler to use the personality system, so that AI-generated responses match the agent's character.

#### Acceptance Criteria

1. THE Unified_Handler SHALL include PERSONALITY from the Personality_Module in the system prompt passed to the LLM dispatcher.
2. WHEN the Unified_Handler encounters a total failure (empty or unparseable LLM output), THE Unified_Handler SHALL use TEMPLATES["error_fallback"] from the Personality_Module as the fallback message.

### Requirement 5: Personality Integration in Message Handler

**User Story:** As a user, I want the message handler's auth-layer responses to use personality templates, so that even rejection messages feel consistent.

#### Acceptance Criteria

1. WHEN the Message_Handler receives a message from an unknown phone number, THE Message_Handler SHALL respond using TEMPLATES["unknown_member"] from the Personality_Module.
2. WHEN the Message_Handler receives a message from an inactive member, THE Message_Handler SHALL respond using TEMPLATES["inactive_member"] from the Personality_Module.
3. THE Message_Handler SHALL contain zero hardcoded Hebrew response strings outside of Personality_Module references.

### Requirement 6: Personality Test Suite

**User Story:** As a developer, I want comprehensive tests for the personality module and its integrations, so that I can verify correctness and prevent regressions.

#### Acceptance Criteria

1. THE test suite SHALL verify that `get_greeting(name, hour)` returns a greeting containing the provided Member_Name for hours 0, 6, 12, 18.
2. THE test suite SHALL verify that `get_greeting(name, hour)` returns a different greeting string for morning (hour=8) versus evening (hour=20).
3. THE test suite SHALL verify that `format_task_created(title, due_date)` includes the task title in the returned string.
4. WHEN `format_task_created` receives a non-null due_date, THE test suite SHALL verify the due_date appears in the returned string.
5. WHEN `format_task_created` receives a null due_date, THE test suite SHALL verify the returned string does not contain a date placeholder.
6. THE test suite SHALL verify that `format_task_list([])` returns TEMPLATES["task_list_empty"].
7. THE test suite SHALL verify that `format_task_list` with multiple tasks returns a string containing each task title.
8. THE test suite SHALL verify that `format_task_list` includes priority emojis (🔴, 🟡, 🟢) matching task priorities.
9. THE test suite SHALL verify that TEMPLATES contains all ten required Template_Key entries.
10. THE test suite SHALL verify that existing tests (175 tests) continue to pass after personality integration.
11. FOR ALL valid Member_Name strings and valid hour integers (0–23), calling `get_greeting` then verifying the result contains the Member_Name SHALL hold true (round-trip property: name in → name in output).

### Requirement 7: README Roadmap Update

**User Story:** As a developer, I want the README roadmap to reflect the STABLE-2 milestone, so that the project history is accurate.

#### Acceptance Criteria

1. WHEN the personality feature is complete, THE README SHALL contain a new row in the roadmap table for "STABLE-2 — Agent Personality" with status "✅ Complete" and an updated test count.
