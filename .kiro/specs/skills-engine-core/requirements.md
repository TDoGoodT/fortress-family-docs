# Requirements Document

## Introduction

Sprint R1 replaces the LLM-first message processing pipeline with a Skills-first architecture. Currently, every incoming WhatsApp message is routed through an LLM for intent detection and response generation. The new architecture introduces a deterministic Skills Engine where 90% of messages are handled by regex-matched skill commands (regex → DB → personality template), 10% fall back to LLM for free chat and NLU, and 0% of CRUD operations go through LLM. The old pipeline files (workflow_engine.py, unified_handler.py, model_router.py, model_dispatch.py, intent_detector.py, routing_policy.py) are preserved but no longer imported by the new message handler.

## Glossary

- **Skills_Engine**: The deterministic message processing pipeline that matches user messages to registered Skills via regex patterns and executes them without LLM calls
- **Skill**: A self-contained module implementing the BaseSkill ABC that handles a specific domain (tasks, documents, system commands) via regex-matched commands
- **Command**: A dataclass representing a parsed user message containing the target skill name, action name, and extracted parameters
- **Result**: A dataclass representing the outcome of a skill execution containing success status, response message, entity metadata, and optional data payload
- **Skill_Registry**: A singleton that holds all registered Skill instances and provides lookup by name and command pattern matching
- **Command_Parser**: A deterministic parser (zero LLM calls) that matches incoming messages against registered skill patterns with priority ordering
- **Executor**: The engine component that receives a parsed Command, dispatches it to the appropriate Skill, verifies the result against the database, updates conversation state, writes an audit log entry, and returns a Result
- **Response_Formatter**: A component that formats Result objects into WhatsApp-safe messages with truncation at approximately 3500 characters
- **System_Skill**: A built-in Skill handling cancel, confirm, and help commands
- **Message_Handler**: The thin auth-layer entry point that authenticates the sender and delegates to the Skills Engine pipeline (parse → execute → format)
- **Conversation_State_Service**: The existing service (conversation_state.py) providing get_state, update_state, clear_state, set_pending_confirmation, and resolve_pending operations
- **Audit_Service**: The existing service (audit.py) providing log_action for append-only action logging
- **Personality_Templates**: The existing Hebrew string templates (personality.py) used for all user-facing bot responses
- **Family_Member**: A registered user in the family_members table, identified by phone number

## Requirements

### Requirement 1: Base Skill Interface

**User Story:** As a developer, I want an abstract base class defining the Skill contract, so that all domain skills follow a consistent interface with typed Command and Result dataclasses.

#### Acceptance Criteria

1. THE BaseSkill module SHALL define a `Command` dataclass with fields: skill (str), action (str), params (dict)
2. THE BaseSkill module SHALL define a `Result` dataclass with fields: success (bool), message (str), entity_type (str or None), entity_id (UUID or None), action (str or None), data (dict or None)
3. THE BaseSkill ABC SHALL define a `name` property returning a string identifier for the skill
4. THE BaseSkill ABC SHALL define a `description` property returning a human-readable description of the skill
5. THE BaseSkill ABC SHALL define a `commands` property returning a list of tuples where each tuple contains a compiled regex pattern and an action name string
6. THE BaseSkill ABC SHALL define an abstract `execute(db, member, command)` method that accepts a SQLAlchemy Session, a FamilyMember, and a Command, and returns a Result
7. THE BaseSkill ABC SHALL define an abstract `verify(db, result)` method that accepts a SQLAlchemy Session and a Result, and returns a boolean indicating whether the action persisted in the database
8. THE BaseSkill ABC SHALL define an abstract `get_help()` method returning a Hebrew help string describing available commands
9. THE BaseSkill module SHALL be located at `src/skills/base_skill.py`

### Requirement 2: Skill Registry

**User Story:** As a developer, I want a singleton registry that holds all skill instances and provides lookup by name and pattern matching, so that the Command Parser and Executor can discover skills at runtime.

#### Acceptance Criteria

1. THE Skill_Registry SHALL provide a `register(skill)` method that accepts a BaseSkill instance and stores the skill indexed by its name
2. THE Skill_Registry SHALL provide a `get(name)` method that returns the registered BaseSkill instance for the given name, or None if not found
3. THE Skill_Registry SHALL provide an `all_commands()` method that returns a flat list of tuples containing (compiled_regex_pattern, action_name, skill_instance) across all registered skills
4. THE Skill_Registry SHALL provide a `list_skills()` method that returns a list of all registered BaseSkill instances
5. THE Skill_Registry module SHALL export a module-level singleton instance named `registry`
6. THE Skill_Registry module SHALL be located at `src/skills/registry.py`

### Requirement 3: Deterministic Command Parser

**User Story:** As a developer, I want a deterministic command parser that matches messages to skill commands using regex patterns with zero LLM calls, so that 90% of messages are handled without AI overhead.

#### Acceptance Criteria

1. THE Command_Parser SHALL match incoming messages against registered skill patterns and return a Command dataclass on match, or None for LLM fallback
2. THE Command_Parser SHALL enforce the following priority order: media messages first, then cancel patterns, then confirmation patterns, then skill command patterns, then LLM fallback
3. WHEN a message matches a cancel pattern (לא, עזוב, תעזוב, בטל, תבטל, ביטול, cancel), THE Command_Parser SHALL return a Command with skill="system" and action="cancel"
4. WHEN a message matches a confirmation pattern (כן, yes, אישור, בטח, אוקיי, ok, אוקי), THE Command_Parser SHALL return a Command with skill="system" and action="confirm"
5. WHEN a message contains media (has_media=True), THE Command_Parser SHALL return a Command with skill="media" and action="save"
6. WHEN no pattern matches, THE Command_Parser SHALL return None to signal LLM fallback
7. THE Command_Parser SHALL make zero LLM calls under all code paths
8. THE Command_Parser SHALL extract named groups from regex matches and include them in the Command params dict
9. THE Command_Parser module SHALL be located at `src/engine/command_parser.py`

### Requirement 4: Executor

**User Story:** As a developer, I want an executor that dispatches parsed commands to skills, verifies results, updates state, and logs actions, so that every skill execution follows a consistent and auditable pipeline.

#### Acceptance Criteria

1. WHEN the Executor receives a Command, THE Executor SHALL look up the target skill from the Skill_Registry by the Command's skill name
2. WHEN the Executor finds the target skill, THE Executor SHALL call the skill's execute method with the database session, family member, and command
3. WHEN the skill execution returns a successful Result with an entity_id, THE Executor SHALL call the skill's verify method to confirm the action persisted in the database
4. IF the verify method returns False, THEN THE Executor SHALL replace the Result message with the personality template "verification_failed" and set success to False
5. WHEN the skill execution returns a successful Result, THE Executor SHALL call update_state on the Conversation_State_Service with the Result's entity_type, entity_id, and action
6. WHEN the skill execution returns a Result with action="cancel", THE Executor SHALL call clear_state on the Conversation_State_Service
7. WHEN the skill execution returns a successful Result with an entity_id, THE Executor SHALL call log_action on the Audit_Service with the member's id, the action, the entity_type, and the entity_id
8. IF any exception occurs during skill execution, THEN THE Executor SHALL call db.rollback(), log the error, and return a Result with success=False and the "error_fallback" personality template message
9. THE Executor module SHALL be located at `src/engine/executor.py`

### Requirement 5: State Manager Integration

**User Story:** As a developer, I want the Executor to correctly integrate with the existing conversation_state service, so that confirmation flows, cancellations, and state tracking work seamlessly with the Skills Engine.

#### Acceptance Criteria

1. WHEN a skill action completes successfully, THE Executor SHALL call `update_state` with intent set to the Command's skill name, entity_type from the Result, entity_id from the Result, and action from the Result
2. WHEN a cancel action is processed, THE Executor SHALL call `clear_state` to reset all mutable conversation state fields
3. WHEN a confirmation action is processed and a pending action exists, THE Executor SHALL call `resolve_pending` to retrieve the pending action data and then execute the pending action through the appropriate skill
4. WHEN a confirmation action is processed and no pending action exists, THE Executor SHALL return a Result indicating there is nothing to confirm
5. THE Executor SHALL use the existing `set_pending_confirmation` function when a skill requests confirmation before executing a destructive action

### Requirement 6: Response Formatter

**User Story:** As a developer, I want a response formatter that truncates long messages for WhatsApp and passes through short messages unchanged, so that all bot responses are safe for the WhatsApp message size limit.

#### Acceptance Criteria

1. WHEN a Result message exceeds approximately 3500 characters, THE Response_Formatter SHALL truncate the message and append a truncation indicator
2. WHEN a Result message is within the character limit, THE Response_Formatter SHALL return the message unchanged
3. THE Response_Formatter SHALL provide a `format_response(result)` function that accepts a Result and returns a string
4. THE Response_Formatter module SHALL be located at `src/engine/response_formatter.py`

### Requirement 7: Updated Message Handler

**User Story:** As a developer, I want the message handler to use the Skills Engine pipeline (parse → execute → format) instead of the workflow engine, so that the new architecture is the active code path.

#### Acceptance Criteria

1. THE Message_Handler SHALL authenticate the sender using the existing `get_family_member_by_phone` function and return the appropriate personality template for unknown or inactive members
2. WHEN the sender is authenticated, THE Message_Handler SHALL call the Command_Parser to parse the message
3. WHEN the Command_Parser returns a Command, THE Message_Handler SHALL pass the Command to the Executor
4. WHEN the Command_Parser returns None (LLM fallback), THE Message_Handler SHALL delegate to the existing LLM pipeline for free-chat handling
5. WHEN the Executor returns a Result, THE Message_Handler SHALL pass the Result to the Response_Formatter and return the formatted string
6. THE Message_Handler SHALL save every message exchange to the conversations table with the parsed intent
7. THE Message_Handler SHALL be located at `src/services/message_handler.py`, replacing the current processing logic
8. THE Message_Handler SHALL accept has_media and media_file_path parameters and pass them to the Command_Parser

### Requirement 8: System Skill

**User Story:** As a family member, I want built-in cancel, confirm, and help commands, so that I can cancel pending actions, confirm destructive operations, and see a list of available commands in Hebrew.

#### Acceptance Criteria

1. WHEN the action is "cancel" and a pending confirmation exists, THE System_Skill SHALL clear the pending state and return a Result with the "cancelled" personality template message
2. WHEN the action is "cancel" and no pending confirmation exists, THE System_Skill SHALL clear the conversation state and return a Result with the "cancelled" personality template message
3. WHEN the action is "confirm" and a pending confirmation exists, THE System_Skill SHALL return a Result with action="confirm" and the pending action data in the Result's data field, so the Executor can re-dispatch the pending action
4. WHEN the action is "confirm" and no pending confirmation exists, THE System_Skill SHALL return a Result indicating there is nothing to confirm
5. WHEN the action is "help", THE System_Skill SHALL query the Skill_Registry for all registered skills and return a Result containing a Hebrew-formatted list of all available commands
6. THE System_Skill SHALL implement the verify method to always return True since system commands do not create database entities
7. THE System_Skill module SHALL be located at `src/skills/system_skill.py`

### Requirement 9: Skill Registration and Module Init

**User Story:** As a developer, I want the skills and engine packages to be properly initialized with the System Skill registered at import time, so that the Skills Engine is ready to handle messages on application startup.

#### Acceptance Criteria

1. THE `src/skills/__init__.py` module SHALL import and register the System_Skill instance into the global Skill_Registry
2. THE `src/engine/__init__.py` module SHALL exist as an empty module to make the engine directory a Python package
3. WHEN the skills package is imported, THE Skill_Registry SHALL contain the System_Skill registered under the name "system"

### Requirement 10: Test Coverage

**User Story:** As a developer, I want comprehensive tests for all new Skills Engine components, so that regressions are caught early and all existing tests continue to pass.

#### Acceptance Criteria

1. THE test_command_parser.py file SHALL test: cancel pattern matching for all Hebrew cancel keywords, confirmation pattern matching for all Hebrew confirmation keywords, media message detection, skill command pattern matching with parameter extraction, and LLM fallback when no pattern matches
2. THE test_executor.py file SHALL test: successful skill execution with state update and audit log, verification failure replacing the result message, exception handling with session rollback, cancel action clearing state, and confirmation action resolving pending actions
3. THE test_base_skill.py file SHALL test: Command dataclass construction and field access, Result dataclass construction with default None fields, and that BaseSkill cannot be instantiated directly
4. THE test_system_skill.py file SHALL test: cancel with pending confirmation, cancel without pending confirmation, confirm with pending action, confirm without pending action, and help listing all registered skills in Hebrew
5. THE test_registry.py file SHALL test: registering a skill, retrieving a skill by name, retrieving None for an unregistered name, all_commands returning patterns from all registered skills, and list_skills returning all registered skill instances
6. FOR ALL existing tests in the fortress/tests directory, THE test suite SHALL continue to pass without modification

### Requirement 11: Preserve Old Code

**User Story:** As a developer, I want the old pipeline files preserved in the codebase, so that they remain available for reference and potential rollback without being imported by the new message handler.

#### Acceptance Criteria

1. THE following files SHALL remain in the codebase without modification: workflow_engine.py, unified_handler.py, model_router.py, model_dispatch.py, intent_detector.py, routing_policy.py
2. THE updated Message_Handler SHALL import from the skills and engine packages only, with no imports from the old pipeline files listed above

### Requirement 12: README Roadmap Update

**User Story:** As a developer, I want the README roadmap to reflect the R1 Skills Engine Core work, so that the project status is accurate.

#### Acceptance Criteria

1. THE README.md roadmap table SHALL include a new row for "R1 — Skills Engine Core" with status, description summarizing the skills-first architecture, and the test count after all new tests pass
