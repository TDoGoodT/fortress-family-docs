# Requirements Document

## Introduction

Sprint 1 addresses the three root causes behind 60% of production bugs in Fortress: stateless conversations, unreliable time handling, and unverified LLM action claims. This sprint adds per-member conversation state tracking, deterministic Israel-timezone time injection into all LLM prompts, and post-action database verification to ensure the bot never claims an action it did not perform. It also introduces confirmation flows for destructive actions, cancel/negation intent handling, reference resolution from conversation context, and an update-task intent.

## Glossary

- **Fortress**: The WhatsApp-based family task management bot (FastAPI + LangGraph)
- **Conversation_State**: A database row tracking the current conversational context for a single family member (one row per member, upsert pattern)
- **Time_Context**: A deterministic time snapshot in Israel timezone (Asia/Jerusalem) injected into every LLM prompt
- **Workflow_Engine**: The LangGraph StateGraph that orchestrates message processing through nodes (intent detection, permission, action, response)
- **Unified_Handler**: The service that performs a single LLM call to classify intent and generate a response
- **Intent_Detector**: The synchronous keyword-based classifier that maps messages to intent categories
- **Routing_Policy**: The mapping from intent to LLM provider sensitivity level
- **Personality_Templates**: Hebrew string templates used for all user-facing bot responses
- **Action_Verification**: A post-action database query confirming that a claimed create/delete/update actually persisted
- **Confirmation_Flow**: A two-step interaction requiring explicit user confirmation before executing destructive actions
- **Reference_Resolution**: The process of resolving pronouns ("אותה"), task indices ("משימה 3"), and person names to concrete entity IDs using conversation state and database lookups
- **Family_Member**: A registered user in the family_members table, identified by phone number
- **Pending_Action**: A JSONB payload stored in Conversation_State describing a destructive action awaiting user confirmation

## Requirements

### Requirement 1: Conversation State Table

**User Story:** As a developer, I want a conversation_state database table, so that each family member's conversational context persists across messages.

#### Acceptance Criteria

1. THE Migration_007 SHALL create a `conversation_state` table with columns: id (UUID PRIMARY KEY), family_member_id (UUID NOT NULL REFERENCES family_members(id) UNIQUE), last_intent (TEXT), last_entity_type (TEXT), last_entity_id (UUID), last_action (TEXT), pending_confirmation (BOOLEAN DEFAULT false), pending_action (JSONB), context (JSONB DEFAULT '{}'), updated_at (TIMESTAMPTZ DEFAULT now()), created_at (TIMESTAMPTZ DEFAULT now())
2. THE Migration_007 SHALL enforce a UNIQUE constraint on family_member_id so that each Family_Member has at most one Conversation_State row
3. THE Migration_007 SHALL be placed at `migrations/007_conversation_state.sql`

### Requirement 2: Conversation State ORM Model

**User Story:** As a developer, I want a SQLAlchemy ORM model for conversation_state, so that application code can read and write conversation state using the existing ORM patterns.

#### Acceptance Criteria

1. THE ConversationState model SHALL be defined in `src/models/schema.py` with mapped columns matching all columns from the conversation_state table
2. THE ConversationState model SHALL define a one-to-one relationship to FamilyMember using `uselist=False`
3. THE FamilyMember model SHALL define a back-reference relationship to ConversationState using `uselist=False`

### Requirement 3: Conversation State Service

**User Story:** As a developer, I want a conversation state service with get/update/clear/pending operations, so that all workflow nodes can manage conversational context through a clean API.

#### Acceptance Criteria

1. WHEN `get_state` is called with a member_id that has no existing row, THE Conversation_State_Service SHALL create a new Conversation_State row with default values and return the row
2. WHEN `get_state` is called with a member_id that has an existing row, THE Conversation_State_Service SHALL return the existing row without modification
3. WHEN `update_state` is called with keyword arguments, THE Conversation_State_Service SHALL update only the non-None fields and always set updated_at to the current timestamp
4. WHEN `clear_state` is called, THE Conversation_State_Service SHALL reset last_intent, last_entity_type, last_entity_id, and last_action to None, pending_confirmation to False, pending_action to None, and context to an empty object
5. WHEN `set_pending_confirmation` is called with action_type and action_data, THE Conversation_State_Service SHALL set pending_confirmation to True and store the action_type and action_data in pending_action as JSONB
6. WHEN `resolve_pending` is called and a pending action exists, THE Conversation_State_Service SHALL return the pending_action data and then clear pending_confirmation to False and pending_action to None
7. WHEN `resolve_pending` is called and no pending action exists, THE Conversation_State_Service SHALL return None
8. THE Conversation_State_Service SHALL be located at `src/services/conversation_state.py`

### Requirement 4: Time Context Injection

**User Story:** As a developer, I want a deterministic time context module in Israel timezone, so that LLM prompts always contain accurate date/time information instead of relying on the LLM to guess.

#### Acceptance Criteria

1. THE Time_Context module SHALL provide a `get_time_context()` function returning a dictionary with keys: now, today_date, today_day_he (Hebrew day name), today_display, tomorrow_date, tomorrow_display, current_time, hour — all computed in Asia/Jerusalem timezone
2. THE Time_Context module SHALL provide a `_month_name_he(month)` helper returning Hebrew month names for months 1–12
3. THE Time_Context module SHALL provide a `format_time_for_prompt()` function returning a formatted Hebrew string suitable for injection into LLM prompts
4. THE Time_Context module SHALL be located at `src/utils/time_context.py`
5. THE requirements.txt SHALL include `pytz==2024.1` as a dependency

### Requirement 5: Inject Time and State into All Prompts

**User Story:** As a developer, I want every LLM call to include time context and conversation state, so that the LLM always knows the current date/time and the user's conversational context.

#### Acceptance Criteria

1. WHEN the Workflow_Engine invokes any LLM call, THE Workflow_Engine SHALL include the output of `format_time_for_prompt()` in the prompt
2. WHEN the Workflow_Engine invokes any LLM call, THE Workflow_Engine SHALL include the current Conversation_State context in the prompt
3. WHEN the Unified_Handler invokes the LLM, THE Unified_Handler SHALL include the output of `format_time_for_prompt()` in the prompt
4. WHEN the Unified_Handler invokes the LLM, THE Unified_Handler SHALL include the current Conversation_State context in the prompt
5. THE prompt structure for all LLM calls SHALL follow the order: {PERSONALITY} {TIME_CONTEXT} {STATE_CONTEXT} {SPECIFIC_PROMPT} הודעת המשתמש: {message}

### Requirement 6: Confirmation Flow for Destructive Actions

**User Story:** As a family member, I want the bot to ask for confirmation before deleting tasks, so that accidental deletions are prevented.

#### Acceptance Criteria

1. WHEN a delete_task intent is detected, THE Workflow_Engine SHALL store the delete action as a Pending_Action via `set_pending_confirmation` and ask the user to confirm
2. WHEN a pending confirmation exists and the user replies "כן" (yes), THE Workflow_Engine SHALL execute the pending action and clear the pending state
3. WHEN a pending confirmation exists and the user replies "לא" (no), THE Workflow_Engine SHALL cancel the pending action, clear the pending state, and inform the user
4. WHEN a pending confirmation exists and the user replies with an unrelated message, THE Workflow_Engine SHALL clear the pending state and process the new message normally
5. THE Workflow_Engine SHALL add a confirmation_check_node at the start of the workflow graph, before intent detection
6. THE Personality_Templates SHALL include templates for `confirm_delete` and `action_cancelled`

### Requirement 7: Cancel and Negation Intent

**User Story:** As a family member, I want to say "עזוב" or "בטל" to cancel any pending action, so that I can easily back out of any operation.

#### Acceptance Criteria

1. WHEN the user sends "עזוב", "תעזוב", "בטל", "תבטל", "לא", or "cancel", THE Intent_Detector SHALL classify the message as `cancel_action`
2. WHEN the user sends a message starting with "אל תעשה" or "אל", THE Intent_Detector SHALL classify the message as `cancel_action`
3. THE INTENTS dictionary SHALL include `cancel_action` with model_tier `local`
4. THE Routing_Policy SENSITIVITY_MAP SHALL map `cancel_action` to `low`
5. WHEN a cancel_action intent is detected, THE Workflow_Engine SHALL clear the Conversation_State and return "בסדר, עזבתי 😊"
6. THE Personality_Templates SHALL include a `cancelled` template

### Requirement 8: Reference Resolution

**User Story:** As a family member, I want to say "אותה" (that one) or "משימה 3" (task 3) to refer to previously mentioned entities, so that I can have natural multi-turn conversations.

#### Acceptance Criteria

1. WHEN the user message contains "אותה", "אותו", "את זה", or "the same", THE Workflow_Engine SHALL resolve the reference to the last_entity_id stored in Conversation_State
2. WHEN the user message contains "משימה" followed by a number, THE Workflow_Engine SHALL resolve the reference by index in the most recently shown open task list (order matching what was displayed)
3. WHEN the user message contains a person name, THE Workflow_Engine SHALL resolve the name from the family_members table
4. IF a person name matches multiple Family_Members, THEN THE Workflow_Engine SHALL ask the user to clarify which person they mean

### Requirement 9: Action Verification

**User Story:** As a developer, I want every action to be verified against the database after execution, so that the bot never claims it performed an action that did not actually persist.

#### Acceptance Criteria

1. WHEN a task is created, THE Workflow_Engine SHALL query the database to confirm the task exists before returning a success response
2. WHEN a task is deleted (archived), THE Workflow_Engine SHALL query the database to confirm the task status is "archived" before returning a success response
3. WHEN a recurring pattern is created, THE Workflow_Engine SHALL query the database to confirm the pattern exists before returning a success response
4. IF a verification query fails to find the expected record, THEN THE Workflow_Engine SHALL return an error message instead of a success message
5. THE Workflow_Engine SHALL use LLM responses only for Hebrew text generation; action success or failure status SHALL be determined by database verification

### Requirement 10: Update State After Every Action

**User Story:** As a developer, I want the conversation state to be updated after every action, so that subsequent messages can reference the context of the previous interaction.

#### Acceptance Criteria

1. WHEN a task is created, THE Workflow_Engine SHALL call `update_state` with last_intent="create_task", last_entity_type="task", last_entity_id set to the new task ID, and last_action="created"
2. WHEN a task is deleted, THE Workflow_Engine SHALL call `update_state` with last_intent="delete_task", last_entity_type="task", last_entity_id set to the deleted task ID, and last_action="deleted"
3. WHEN tasks are listed, THE Workflow_Engine SHALL save the task IDs in the Conversation_State context field for subsequent index-based resolution
4. WHEN a cancel_action is processed, THE Workflow_Engine SHALL call `clear_state`

### Requirement 11: Update Task Intent

**User Story:** As a family member, I want to update task details by saying "תשנה" or "עדכן", so that I can modify tasks without deleting and recreating them.

#### Acceptance Criteria

1. WHEN the user sends "תשנה", "תעדכן", "עדכן", "שנה", or "update", THE Intent_Detector SHALL classify the message as `update_task`
2. THE INTENTS dictionary SHALL include `update_task` with model_tier `local`
3. THE Routing_Policy SENSITIVITY_MAP SHALL map `update_task` to `medium`
4. WHEN an update_task intent is detected, THE Workflow_Engine SHALL resolve the target task from Conversation_State or by number/name from the message
5. THE Workflow_Engine SHALL support updating task fields: title, due_date, assigned_to, priority, and status
6. THE Personality_Templates SHALL include templates for `task_updated` and `task_update_which`
7. THE UNIFIED_CLASSIFY_AND_RESPOND prompt SHALL include `update_task` as a valid intent category

### Requirement 12: Test Coverage

**User Story:** As a developer, I want comprehensive tests for all new functionality, so that regressions are caught early and all existing tests continue to pass.

#### Acceptance Criteria

1. THE test_conversation_state.py file SHALL test get_state (create and retrieve), update_state (partial update), clear_state, set_pending_confirmation, and resolve_pending
2. THE test_time_context.py file SHALL test that get_time_context returns all required keys, that format_time_for_prompt returns a non-empty string, and that Hebrew day and month name helpers return correct values
3. THE test_confirmation_flow.py file SHALL test confirm-yes executes the action, confirm-no cancels, confirm-other clears and continues, and that delete_task sets a pending confirmation
4. THE test_action_verification.py file SHALL test that create_task verifies the task exists in the database and that delete_task verifies the task is archived
5. THE test_reference_resolution.py file SHALL test "אותה" resolution from last_entity_id, "משימה 3" resolution by index, and person name resolution from family_members
6. THE test_intent_detector.py file SHALL be updated to test cancel_action keywords and update_task keywords
7. FOR ALL existing tests, THE test suite SHALL continue to pass without modification

### Requirement 13: README Roadmap Update

**User Story:** As a developer, I want the README roadmap to reflect the sprint 1 work, so that the project status is accurate.

#### Acceptance Criteria

1. THE README.md roadmap table SHALL include a new row for Sprint 1 with status, description, and test count
