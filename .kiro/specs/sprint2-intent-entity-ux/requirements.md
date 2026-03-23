# Requirements Document

## Introduction

Sprint 2 builds on the Sprint 1 foundation (conversation state, time injection, action verification) to fix the remaining ~30% of production bugs in Fortress. The focus areas are: strict intent classification with priority-based keyword matching, multi-intent message handling, clarification instead of guessing, bulk operations, assignee notifications, task index consistency, smarter duplicate detection, and data/info storage. All user-facing text uses personality templates. All existing tests (365) must continue to pass.

## Glossary

- **Intent_Detector**: The synchronous keyword-matching module (`src/services/intent_detector.py`) that classifies incoming messages into intent categories before any LLM call.
- **Workflow_Engine**: The LangGraph-based state machine (`src/services/workflow_engine.py`) that orchestrates nodes for confirmation, intent detection, permission, action execution, verification, and state updates.
- **Unified_Handler**: The single-LLM-call module (`src/services/unified_handler.py`) that classifies intent and generates a response when keyword matching yields `needs_llm`.
- **Conversation_State**: The per-member database record (`conversation_state` table) tracking last intent, entity references, pending confirmations, and context (including `task_list_order`).
- **Routing_Policy**: The module (`src/services/routing_policy.py`) mapping intents to sensitivity levels and LLM provider chains.
- **Personality_Templates**: The centralized Hebrew response template dictionary (`src/prompts/personality.py` `TEMPLATES`) used for all user-facing text.
- **Confirmation_Flow**: The existing pending-confirmation mechanism where the bot sets `pending_confirmation=True` with action details, then waits for user yes/no before executing.
- **Family_Member**: A record in the `family_members` table representing a household user, identified by phone number.
- **WhatsApp_Client**: The WAHA-based message sending module (`src/services/whatsapp_client.py`) used for outbound notifications.
- **Memory_Service**: The module (`src/services/memory_service.py`) that saves, loads, and manages conversational memories per family member.

## Requirements

### Requirement 1: Strict Priority-Based Intent Classification

**User Story:** As a family member, I want my messages to be classified correctly so that "משימה" does not accidentally trigger delete instead of list, and exact phrases always take precedence over loose keyword matches.

#### Acceptance Criteria

1. WHEN a message is received, THE Intent_Detector SHALL evaluate keyword matches in strict priority order: Priority 1 (exact phrases) before Priority 2 (action + context verbs) before Priority 3 (standalone keywords) before Priority 4 (no match → `needs_llm`).
2. WHEN the message matches an exact phrase from Priority 1 (e.g., "משימה חדשה:", "תזכורת חדשה:", "מחק משימה", "מחק תזכורת", "סיום משימה", "באג:"), THE Intent_Detector SHALL return the corresponding intent and skip all lower-priority checks.
3. WHEN the message contains a Priority 2 action verb ("תשנה"/"תעדכן"/"עדכן" → `update_task`, "תמחק"/"תמחוק"/"מחק" → `delete_task`, "תיצור"/"תוסיף"/"הוסף" → `create_task`, "תסיים"/"סיים"/"בוצע" → `complete_task`) and no Priority 1 match exists, THE Intent_Detector SHALL return the corresponding intent.
4. WHEN the message matches a Priority 3 standalone keyword ("משימות" → `list_tasks`, "מסמכים" → `list_documents`, "תזכורות" → `list_recurring`, "באגים" → `list_bugs`, "שלום"/"היי" → `greeting`) and no Priority 1 or 2 match exists, THE Intent_Detector SHALL return the corresponding intent.
5. WHEN the message is "משימה" (singular, without any action prefix), THE Intent_Detector SHALL return `needs_llm`.
6. WHEN the message starts with "אל" or "לא", THE Intent_Detector SHALL return `cancel_action` regardless of any other keywords present in the message.
7. WHEN no keyword match is found at any priority level, THE Intent_Detector SHALL return `needs_llm`.

### Requirement 2: Multi-Intent Detection

**User Story:** As a family member, I want to send a single message with multiple requests (e.g., "תיצור משימה לקנות חלב וגם תזכיר לי לשלם ארנונה") so that the bot handles all of them in one response.

#### Acceptance Criteria

1. THE Unified_Handler prompt (UNIFIED_CLASSIFY_AND_RESPOND) SHALL include instructions to detect multi-intent messages and return a JSON response with `"intent": "multi_intent"` and a `"sub_intents"` array containing individual intent objects.
2. THE Intent_Detector INTENTS dict and VALID_INTENTS set SHALL include `"multi_intent"`.
3. THE Routing_Policy SENSITIVITY_MAP SHALL map `multi_intent` to `"medium"`.
4. WHEN the Workflow_Engine receives a `multi_intent` classification, THE Workflow_Engine SHALL iterate over each sub-intent, execute the corresponding handler for each, and combine all individual responses into a single combined response.
5. THE Personality_Templates SHALL include a `"multi_intent_summary"` template for wrapping combined multi-intent responses.

### Requirement 3: Clarification Strategy

**User Story:** As a family member, I want the bot to ask me what I meant when it is unsure, instead of guessing and performing the wrong action.

#### Acceptance Criteria

1. THE Intent_Detector INTENTS dict and VALID_INTENTS set SHALL include `"ambiguous"`.
2. WHEN the Unified_Handler LLM returns low confidence or an `"ambiguous"` intent, THE Workflow_Engine SHALL present the user with a numbered list of possible intents to choose from.
3. WHEN the Workflow_Engine presents clarification options, THE Conversation_State SHALL store the options array in `pending_action` with `type="clarification"`.
4. WHEN the user replies with a number corresponding to a clarification option, THE Workflow_Engine SHALL execute the intent associated with that option number.
5. THE Personality_Templates SHALL include `"clarify"` (asking the user to choose) and `"clarify_option"` (formatting each option) templates.
6. THE Workflow_Engine confirmation_check_node SHALL handle `pending_action` of `type="clarification"` by looking up the selected option number and routing to the corresponding intent.

### Requirement 4: Bulk Operations

**User Story:** As a family member, I want to delete all tasks or a range of tasks at once (e.g., "מחק הכל" or "מחק 1-5") so that I can clean up quickly.

#### Acceptance Criteria

1. WHEN the message contains "מחק הכל", "נקה הכל", or "delete all", THE Intent_Detector SHALL return `bulk_delete_tasks`.
2. WHEN the message matches a range pattern like "מחק 1 עד 5", "מחק 1-5", or "delete 1-5", THE Intent_Detector SHALL return `bulk_delete_range`.
3. THE Intent_Detector INTENTS dict and VALID_INTENTS set SHALL include `"bulk_delete_tasks"` and `"bulk_delete_range"`.
4. THE Routing_Policy SENSITIVITY_MAP SHALL map both `bulk_delete_tasks` and `bulk_delete_range` to `"medium"`.
5. WHEN `bulk_delete_tasks` is executed, THE Workflow_Engine SHALL list all open tasks for the member, present them for confirmation using the Confirmation_Flow, and archive all open tasks upon confirmation.
6. WHEN `bulk_delete_range` is executed, THE Workflow_Engine SHALL parse the numeric range from the message, list the tasks in that range, present them for confirmation using the Confirmation_Flow, and archive only those tasks upon confirmation.
7. THE Personality_Templates SHALL include `"bulk_delete_confirm"` (asking confirmation for delete-all), `"bulk_deleted"` (confirming bulk deletion with count), and `"bulk_range_confirm"` (asking confirmation for range deletion) templates.

### Requirement 5: Assignee Notifications

**User Story:** As a family member, I want the person I assign a task to to receive a WhatsApp notification so that they know about the new task.

#### Acceptance Criteria

1. WHEN a task is created with `assigned_to` pointing to a different Family_Member than the sender, THE Workflow_Engine SHALL send a WhatsApp notification to the assignee using the WhatsApp_Client.
2. WHEN a task is created with `assigned_to` equal to the sender, THE Workflow_Engine SHALL send no assignee notification.
3. THE Personality_Templates SHALL include a `"task_assigned_notification"` template for the notification message sent to the assignee.
4. IF the WhatsApp notification fails to send, THEN THE Workflow_Engine SHALL log the failure and continue returning the task creation response to the sender without error.
5. THE Workflow_Engine SHALL log both successful and failed notification attempts with the assignee member ID and task title.

### Requirement 6: Task Index Consistency

**User Story:** As a family member, I want to refer to tasks by their number from the last list (e.g., "מחק 2") and have the bot correctly identify which task I mean.

#### Acceptance Criteria

1. WHEN `list_tasks` is executed, THE Workflow_Engine update_state_node SHALL save the task order as `task_list_order` (list of task ID strings) in `Conversation_State.context`.
2. WHEN the user sends a message containing a number (e.g., "מחק 2", "משימה 2", or just "2") and `task_list_order` exists in the Conversation_State context, THE Workflow_Engine SHALL look up the task ID at that index in `task_list_order`.
3. IF the user references a task by number and no `task_list_order` exists in the Conversation_State context, THEN THE Workflow_Engine SHALL respond with the `"need_list_first"` personality template.
4. THE Personality_Templates SHALL include a `"need_list_first"` template instructing the user to request a task list before referencing by number.

### Requirement 7: Smarter Duplicate Detection

**User Story:** As a family member, I want the bot to catch near-duplicate tasks (not just exact title matches) so that I don't accidentally create the same task twice with slightly different wording.

#### Acceptance Criteria

1. WHEN a new task is about to be created, THE Workflow_Engine task_create_node SHALL check for similar open tasks using three strategies: exact title match (case-insensitive), substring match (new title contained in existing or vice versa), and normalized match (stripping Hebrew prefixes "ל"/"ה" before comparing).
2. IF an exact duplicate is found (same title, case-insensitive, open status), THEN THE Workflow_Engine SHALL reject the creation and return the existing `"task_duplicate"` personality template without asking for confirmation.
3. IF a similar (but not exact) match is found via substring or normalized comparison, THEN THE Workflow_Engine SHALL ask the user for confirmation using the Confirmation_Flow before creating the task.
4. THE Personality_Templates SHALL include a `"task_similar_exists"` template showing the similar task title and asking whether to create anyway.

### Requirement 8: Data Input Recognition (store_info)

**User Story:** As a family member, I want to tell the bot factual information (e.g., "הקוד לכספת הוא 1234") and have it stored as a permanent memory, without creating a task.

#### Acceptance Criteria

1. THE Intent_Detector INTENTS dict and VALID_INTENTS set SHALL include `"store_info"` with `model_tier` set to `"local"`.
2. THE Unified_Handler prompt (UNIFIED_CLASSIFY_AND_RESPOND) SHALL include `store_info` as a valid intent with a description indicating the user wants to store factual information.
3. WHEN the Workflow_Engine receives a `store_info` intent, THE Workflow_Engine SHALL save the information as a Memory with `category="fact"` and `memory_type="permanent"` using the Memory_Service.
4. THE Personality_Templates SHALL include an `"info_stored"` template confirming the information was saved.
5. THE Routing_Policy SENSITIVITY_MAP SHALL map `store_info` to `"medium"`.

### Requirement 9: Comprehensive Test Coverage

**User Story:** As a developer, I want comprehensive tests for all new Sprint 2 functionality so that regressions are caught early.

#### Acceptance Criteria

1. THE test suite SHALL include `test_intent_priority.py` covering all Priority 1–4 keyword matching rules, the "משימה" → `needs_llm` rule, and the "אל"/"לא" → `cancel_action` rule.
2. THE test suite SHALL include `test_multi_intent.py` covering multi-intent detection, sub-intent iteration, and combined response generation.
3. THE test suite SHALL include `test_clarification.py` covering ambiguous intent detection, numbered option presentation, option selection from Conversation_State, and clarification routing.
4. THE test suite SHALL include `test_bulk_operations.py` covering `bulk_delete_tasks` keyword detection, `bulk_delete_range` range parsing, confirmation flow integration, and task archival.
5. THE test suite SHALL include `test_assignee_notification.py` covering notification sent when assignee differs from sender, no notification when assignee equals sender, and graceful handling of notification failure.
6. THE test suite SHALL include `test_duplicate_detection.py` covering exact duplicate rejection, substring similarity detection, normalized (prefix-stripped) similarity detection, and confirmation flow for similar tasks.
7. WHEN the full test suite is executed, all existing 365 tests SHALL continue to pass alongside the new tests.

### Requirement 10: README Roadmap Update

**User Story:** As a developer, I want the README roadmap table to reflect Sprint 2 completion so that the project status is accurate.

#### Acceptance Criteria

1. WHEN Sprint 2 is complete, THE README.md roadmap table SHALL include a new row for "SPRINT-2 — Intent + Entity + UX" with status, description, and test count.
