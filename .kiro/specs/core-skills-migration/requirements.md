# Requirements Document

## Introduction

Sprint R2 of the Fortress Skills Engine rebuild. Sprint R1 delivered the core engine infrastructure (BaseSkill, SkillRegistry, CommandParser, Executor, StateManager, SystemSkill). Sprint R2 migrates all existing Fortress functionality into self-contained Skills: TaskSkill, RecurringSkill, DocumentSkill, BugSkill, ChatSkill, MemorySkill, and MorningSkill. After R2, the message_handler LLM fallback path is only hit for truly free-form conversation — all structured operations route through the Skills Engine with zero LLM calls.

## Glossary

- **Skills_Engine**: The Fortress command processing pipeline: CommandParser → Executor → ResponseFormatter
- **BaseSkill**: Abstract base class defining the skill interface (name, description, commands, execute, verify, get_help)
- **SkillRegistry**: Singleton that holds all registered skill instances and exposes their command patterns to the CommandParser
- **CommandParser**: Deterministic regex-based parser that matches user messages to Command objects (zero LLM)
- **Executor**: Dispatches Command objects to the appropriate skill, runs verification, updates state, and logs audit
- **StateManager**: ConversationState service that tracks last_intent, last_entity_id, pending_confirmation, and context per member
- **Command**: Dataclass with skill name, action name, and params dict — output of CommandParser
- **Result**: Dataclass with success flag, message, entity_type, entity_id, action, and data dict — output of skill execute
- **FamilyMember**: ORM model representing a household member with phone, role, and is_active fields
- **Permission**: ORM model mapping role → resource_type → can_read/can_write
- **Personality_Templates**: Dictionary of Hebrew response templates in personality.py (TEMPLATES dict)
- **Confirmation_Flow**: Pattern where destructive actions set pending_confirmation in state and require a "כן" confirmation before executing
- **Task_List_Order**: A list of task IDs stored in conversation state context after a list command, enabling index-based resolution
- **LLM_Fallback**: The code path in message_handler that delegates to an LLM (Bedrock/OpenRouter) when no skill pattern matches
- **TaskSkill**: Skill handling task CRUD operations (create, list, delete, delete_all, complete, update)
- **RecurringSkill**: Skill handling recurring pattern management (create, list, delete)
- **DocumentSkill**: Skill handling document save and list operations, registered under both "document" and "media" names
- **BugSkill**: Skill handling bug report and list operations
- **ChatSkill**: Skill handling greetings (no LLM) and free-form conversation responses (LLM)
- **MemorySkill**: Skill handling memory store, recall, and list operations
- **MorningSkill**: Skill handling morning briefing and summary report generation

## Requirements

### Requirement 1: TaskSkill — Task Creation

**User Story:** As a family member, I want to create tasks via WhatsApp messages, so that I can track household to-dos without leaving the chat.

#### Acceptance Criteria

1. WHEN a message matches the pattern "משימה חדשה" or "new task" followed by a title, THE TaskSkill SHALL parse the title from the message and create a Task record via the tasks service
2. WHEN a task creation is requested, THE TaskSkill SHALL check the member's permission for resource "tasks" with action "write" before creating the task
3. IF the member lacks tasks/write permission, THEN THE TaskSkill SHALL return a Result with success=False using the "permission_denied" personality template
4. WHEN a task creation is requested, THE TaskSkill SHALL check for duplicate tasks with the same title created by the same member within a 5-minute window
5. IF a duplicate task is detected, THEN THE TaskSkill SHALL return a confirmation prompt using the "task_similar_exists" personality template and set pending_confirmation in state
6. WHEN a task is created successfully, THE TaskSkill SHALL verify the task exists in the database with status "open" before returning success
7. WHEN a task is created successfully, THE TaskSkill SHALL return a Result with entity_type="task", entity_id set to the new task's UUID, and action="created"
8. THE TaskSkill SHALL format the creation response using the "task_created" personality template

### Requirement 2: TaskSkill — Task Listing

**User Story:** As a family member, I want to list my open tasks, so that I can see what needs to be done.

#### Acceptance Criteria

1. WHEN a message matches the pattern "משימות" or "tasks", THE TaskSkill SHALL query open tasks via the tasks service
2. WHEN a task list is requested, THE TaskSkill SHALL check the member's permission for resource "tasks" with action "read" before querying
3. IF the member lacks tasks/read permission, THEN THE TaskSkill SHALL return a Result with success=False using the "permission_denied" personality template
4. WHEN tasks are listed successfully, THE TaskSkill SHALL store the ordered list of task IDs as "task_list_order" in the conversation state context
5. WHEN tasks are listed successfully, THE TaskSkill SHALL format the response using the format_task_list personality helper
6. WHEN no open tasks exist, THE TaskSkill SHALL return the "task_list_empty" personality template

### Requirement 3: TaskSkill — Task Deletion

**User Story:** As a family member, I want to delete a task by index number, so that I can remove tasks quickly from the list I just saw.

#### Acceptance Criteria

1. WHEN a message matches the pattern "מחק משימה" or "מחק" followed by an index number, THE TaskSkill SHALL resolve the task ID from the task_list_order stored in conversation state
2. IF task_list_order does not exist in conversation state, THEN THE TaskSkill SHALL return the "need_list_first" personality template
3. IF the index is out of range of task_list_order, THEN THE TaskSkill SHALL return the "task_not_found" personality template
4. WHEN a valid task is resolved for deletion, THE TaskSkill SHALL set pending_confirmation with the task details and return the "confirm_delete" personality template
5. WHEN deletion is confirmed, THE TaskSkill SHALL archive the task via the tasks service and verify the task status is "archived" in the database
6. WHEN a task is deleted successfully, THE TaskSkill SHALL return a Result with entity_type="task", entity_id set to the archived task's UUID, and action="deleted"
7. WHEN a task deletion is requested, THE TaskSkill SHALL check the member's permission for resource "tasks" with action "write" before proceeding

### Requirement 4: TaskSkill — Bulk Delete All

**User Story:** As a family member, I want to delete all open tasks at once, so that I can clear my task list quickly.

#### Acceptance Criteria

1. WHEN a message matches the pattern "מחק הכל" or "נקה הכל" or "delete all", THE TaskSkill SHALL query the count of open tasks
2. WHEN a bulk delete is requested, THE TaskSkill SHALL check the member's permission for resource "tasks" with action "write" before proceeding
3. IF the member lacks tasks/write permission, THEN THE TaskSkill SHALL return a Result with success=False using the "permission_denied" personality template
4. WHEN open tasks exist, THE TaskSkill SHALL set pending_confirmation with the task count and return the "bulk_delete_confirm" personality template showing the count and task list
5. WHEN bulk deletion is confirmed, THE TaskSkill SHALL archive all open tasks and return the "bulk_deleted" personality template with the count

### Requirement 5: TaskSkill — Task Completion

**User Story:** As a family member, I want to mark a task as done by index or by referencing the last task, so that I can track progress.

#### Acceptance Criteria

1. WHEN a message matches the pattern "סיים" or "סיום" or "בוצע" or "done" with an optional index number, THE TaskSkill SHALL resolve the target task
2. WHEN an index is provided, THE TaskSkill SHALL resolve the task ID from task_list_order in conversation state
3. WHEN no index is provided, THE TaskSkill SHALL use the last_entity_id from conversation state if last_entity_type is "task"
4. IF task_list_order does not exist in state and an index is provided, THEN THE TaskSkill SHALL return the "need_list_first" personality template
5. WHEN a task completion is requested, THE TaskSkill SHALL check the member's permission for resource "tasks" with action "write" before proceeding
6. WHEN a task is completed successfully, THE TaskSkill SHALL verify the task status is "done" in the database
7. WHEN a task is completed successfully, THE TaskSkill SHALL return a Result with entity_type="task", entity_id set to the completed task's UUID, and action="completed"
8. THE TaskSkill SHALL format the completion response using the "task_completed" personality template

### Requirement 6: TaskSkill — Task Update

**User Story:** As a family member, I want to update task properties like due date, title, priority, or assignee, so that I can adjust tasks as needs change.

#### Acceptance Criteria

1. WHEN a message matches the pattern "עדכן" or "שנה" with an optional index and change descriptions, THE TaskSkill SHALL resolve the target task and parse the requested changes
2. THE TaskSkill SHALL support updating the following fields: due_date, title, priority, assigned_to
3. WHEN an index is provided, THE TaskSkill SHALL resolve the task ID from task_list_order in conversation state
4. WHEN no index is provided, THE TaskSkill SHALL use the last_entity_id from conversation state if last_entity_type is "task"
5. IF task_list_order does not exist in state and an index is provided, THEN THE TaskSkill SHALL return the "need_list_first" personality template
6. WHEN a task update is requested, THE TaskSkill SHALL check the member's permission for resource "tasks" with action "write" before proceeding
7. WHEN a task is updated successfully, THE TaskSkill SHALL verify the task exists in the database with the updated values
8. THE TaskSkill SHALL format the update response using the "task_updated" personality template including a summary of changes


### Requirement 7: RecurringSkill — Create Recurring Pattern

**User Story:** As a family member, I want to create recurring reminders via chat, so that repeating tasks are generated automatically.

#### Acceptance Criteria

1. WHEN a message matches the pattern "תזכורת חדשה" or "recurring" followed by details, THE RecurringSkill SHALL parse the title and frequency from the message text
2. WHEN a recurring pattern creation is requested, THE RecurringSkill SHALL calculate the next_due_date based on the parsed frequency and current date
3. WHEN a recurring pattern is created successfully, THE RecurringSkill SHALL return a Result with entity_type="recurring_pattern", entity_id set to the new pattern's UUID, and action="created"
4. WHEN a recurring pattern is created successfully, THE RecurringSkill SHALL verify the pattern exists in the database with is_active=True
5. THE RecurringSkill SHALL format the creation response using the "recurring_created" personality template

### Requirement 8: RecurringSkill — List Recurring Patterns

**User Story:** As a family member, I want to see all active recurring reminders, so that I know what repeating tasks are set up.

#### Acceptance Criteria

1. WHEN a message matches the pattern "תזכורות" or "חוזרות" or "recurring", THE RecurringSkill SHALL query active recurring patterns via the recurring service
2. WHEN patterns are listed successfully, THE RecurringSkill SHALL format the response using the format_recurring_list personality helper
3. WHEN no active patterns exist, THE RecurringSkill SHALL return the "recurring_list_empty" personality template

### Requirement 9: RecurringSkill — Delete Recurring Pattern

**User Story:** As a family member, I want to cancel a recurring reminder, so that it stops generating tasks.

#### Acceptance Criteria

1. WHEN a message matches the pattern "מחק תזכורת" or "בטל תזכורת" followed by an identifier, THE RecurringSkill SHALL resolve the target pattern
2. WHEN a valid pattern is resolved for deletion, THE RecurringSkill SHALL set pending_confirmation with the pattern details and return the "confirm_delete" personality template
3. WHEN deletion is confirmed, THE RecurringSkill SHALL deactivate the pattern via deactivate_pattern and verify is_active=False in the database
4. WHEN a pattern is deleted successfully, THE RecurringSkill SHALL return a Result with entity_type="recurring_pattern", entity_id set to the deactivated pattern's UUID, and action="deleted"
5. THE RecurringSkill SHALL format the deletion response using the "recurring_deleted" personality template

### Requirement 10: DocumentSkill — Save Document

**User Story:** As a family member, I want to save documents and images sent via WhatsApp, so that household paperwork is organized and accessible.

#### Acceptance Criteria

1. WHEN a message has has_media=True, THE CommandParser SHALL produce a Command with skill="media" and action="save"
2. WHEN the DocumentSkill receives a save command, THE DocumentSkill SHALL process the document via the documents service using the media_file_path from command params
3. WHEN a document is saved successfully, THE DocumentSkill SHALL return a Result with entity_type="document", entity_id set to the new document's UUID, and action="saved"
4. WHEN a document is saved successfully, THE DocumentSkill SHALL verify the document exists in the database
5. THE DocumentSkill SHALL format the save response using the "document_saved" personality template

### Requirement 11: DocumentSkill — List Documents

**User Story:** As a family member, I want to list recent documents, so that I can find saved files.

#### Acceptance Criteria

1. WHEN a message matches the pattern "מסמכים" or "documents", THE DocumentSkill SHALL query the last 20 documents from the database
2. WHEN documents are listed successfully, THE DocumentSkill SHALL format the response using the format_document_list personality helper
3. WHEN no documents exist, THE DocumentSkill SHALL return the "document_list_empty" personality template

### Requirement 12: DocumentSkill — Dual Registration

**User Story:** As a developer, I want the DocumentSkill registered under both "document" and "media" names, so that media save commands from CommandParser route correctly.

#### Acceptance Criteria

1. THE Skills_Engine SHALL register the DocumentSkill instance under the name "document" in the SkillRegistry
2. THE Skills_Engine SHALL register the same DocumentSkill instance under the name "media" in the SkillRegistry
3. WHEN the CommandParser produces a Command with skill="media", THE Executor SHALL resolve the DocumentSkill from the registry

### Requirement 13: BugSkill — Report Bug

**User Story:** As a parent, I want to report bugs via chat, so that issues are tracked without leaving WhatsApp.

#### Acceptance Criteria

1. WHEN a message matches the pattern "באג" or "bug" followed by a description, THE BugSkill SHALL create a BugReport record in the database
2. WHEN a bug report is requested, THE BugSkill SHALL check the member's permission for resource "tasks" with action "write" before creating the report
3. IF the member lacks tasks/write permission, THEN THE BugSkill SHALL return a Result with success=False using the "permission_denied" personality template
4. WHEN a bug is reported successfully, THE BugSkill SHALL return a Result with entity_type="bug_report", entity_id set to the new report's UUID, and action="reported"
5. WHEN a bug is reported successfully, THE BugSkill SHALL verify the bug report exists in the database with status "open"
6. THE BugSkill SHALL format the report response using the "bug_reported" personality template

### Requirement 14: BugSkill — List Bugs

**User Story:** As a family member, I want to see open bugs, so that I know what issues are being tracked.

#### Acceptance Criteria

1. WHEN a message matches the pattern "באגים" or "bugs" or "רשימת באגים", THE BugSkill SHALL query open bug reports from the database
2. WHEN a bug list is requested, THE BugSkill SHALL check the member's permission for resource "tasks" with action "read" before querying
3. IF the member lacks tasks/read permission, THEN THE BugSkill SHALL return a Result with success=False using the "permission_denied" personality template
4. WHEN bugs are listed successfully, THE BugSkill SHALL format the response using the format_bug_list personality helper
5. WHEN no open bugs exist, THE BugSkill SHALL return the "bug_list_empty" personality template


### Requirement 15: ChatSkill — Greeting

**User Story:** As a family member, I want to greet the bot and get a friendly response, so that the interaction feels natural and personal.

#### Acceptance Criteria

1. WHEN a message matches the pattern "שלום" or "היי" or "hello" or "בוקר טוב" or "ערב טוב" or "לילה טוב", THE ChatSkill SHALL return a time-appropriate greeting using the get_greeting personality helper
2. THE ChatSkill SHALL produce the greeting response without making any LLM calls
3. WHEN a greeting is returned, THE ChatSkill SHALL include the member's name in the response

### Requirement 16: ChatSkill — LLM Conversation Response

**User Story:** As a family member, I want free-form conversation to be handled intelligently, so that the bot can respond to messages that don't match any command pattern.

#### Acceptance Criteria

1. WHEN the message_handler LLM fallback path is reached, THE message_handler SHALL delegate to ChatSkill.respond instead of workflow_engine.run_workflow
2. WHEN ChatSkill.respond is called, THE ChatSkill SHALL construct a prompt including the Fortress personality, current time context, conversation state, and relevant memories
3. WHEN ChatSkill.respond is called, THE ChatSkill SHALL call the LLM (Bedrock or OpenRouter) to generate a response
4. THE ChatSkill SHALL be the only skill in the system that makes LLM calls

### Requirement 17: MemorySkill — List Memories

**User Story:** As a family member, I want to see what the bot remembers about me, so that I can review stored information.

#### Acceptance Criteria

1. WHEN a message matches the pattern "זכרונות" or "memories", THE MemorySkill SHALL load memories for the member via load_memories from the memory service
2. WHEN memories are loaded successfully, THE MemorySkill SHALL format the response as a numbered list with category and content
3. WHEN no memories exist for the member, THE MemorySkill SHALL return the "memory_list_empty" personality template
4. THE MemorySkill SHALL format the list using the "memory_list_header" personality template

### Requirement 18: MemorySkill — Store Memory

**User Story:** As a developer, I want the MemorySkill to store memories programmatically, so that other skills and the ChatSkill can persist important information.

#### Acceptance Criteria

1. WHEN the MemorySkill store action is called programmatically, THE MemorySkill SHALL check the content against memory exclusion patterns via check_exclusion
2. IF the content matches an exclusion pattern, THEN THE MemorySkill SHALL return a Result with success=False using the "memory_excluded" personality template
3. WHEN the content passes exclusion checks, THE MemorySkill SHALL validate the category against VALID_CATEGORIES and save via save_memory
4. WHEN a memory is stored successfully, THE MemorySkill SHALL return a Result with entity_type="memory", entity_id set to the new memory's UUID, and action="stored"

### Requirement 19: MemorySkill — Recall Memories

**User Story:** As a developer, I want the MemorySkill to provide memory recall for ChatSkill context, so that LLM responses are informed by stored knowledge.

#### Acceptance Criteria

1. WHEN the MemorySkill recall action is called by ChatSkill, THE MemorySkill SHALL load relevant memories for the member via load_memories
2. THE MemorySkill recall action SHALL be a programmatic interface only, not triggered by user-facing regex patterns
3. WHEN memories are recalled, THE MemorySkill SHALL return the memory list in the Result data field for ChatSkill consumption

### Requirement 20: MorningSkill — Morning Briefing

**User Story:** As a family member, I want to receive a morning briefing with task and reminder counts, so that I can start my day informed.

#### Acceptance Criteria

1. WHEN a message matches the pattern "בוקר" or "morning" or "סיכום בוקר", THE MorningSkill SHALL query counts of open tasks, active recurring patterns, recent documents, and open bugs
2. THE MorningSkill SHALL produce the briefing response without making any LLM calls
3. THE MorningSkill SHALL format the briefing using the "morning_briefing" personality template with section templates for tasks, recurring, documents, and bugs
4. WHEN a section has zero items, THE MorningSkill SHALL omit that section from the briefing or show a zero count

### Requirement 21: MorningSkill — Summary Report

**User Story:** As a parent, I want to request a summary report, so that I can see an overview of household activity.

#### Acceptance Criteria

1. WHEN a message matches the pattern "דוח" or "report" or "סיכום", THE MorningSkill SHALL generate a summary report
2. WHEN a summary report is requested, THE MorningSkill SHALL check the member's permission for resource "finance" with action "read" before generating
3. IF the member lacks finance/read permission, THEN THE MorningSkill SHALL return a Result with success=False using the "permission_denied" personality template
4. THE MorningSkill SHALL format the report using personality templates without making any LLM calls

### Requirement 22: Skill Registration

**User Story:** As a developer, I want all skills registered at import time in __init__.py, so that the CommandParser and Executor can discover them.

#### Acceptance Criteria

1. THE Skills_Engine SHALL register TaskSkill, RecurringSkill, DocumentSkill, BugSkill, ChatSkill, MemorySkill, and MorningSkill in src/skills/__init__.py
2. THE Skills_Engine SHALL register the DocumentSkill instance under both "document" and "media" names in the SkillRegistry
3. WHEN the skills module is imported, THE SkillRegistry SHALL contain all seven skill types plus the existing SystemSkill

### Requirement 23: Message Handler LLM Fallback Update

**User Story:** As a developer, I want the message handler to use ChatSkill.respond for the LLM fallback path, so that all conversation logic is consolidated in the skills architecture.

#### Acceptance Criteria

1. WHEN the CommandParser returns None (no pattern match), THE message_handler SHALL delegate to ChatSkill.respond instead of workflow_engine.run_workflow
2. WHEN ChatSkill.respond is called from message_handler, THE message_handler SHALL pass the database session, member, and message text
3. THE message_handler SHALL record the intent as "chat.respond" for LLM fallback conversations

### Requirement 24: Personality Templates

**User Story:** As a developer, I want all new response strings defined as personality templates, so that the bot's voice is consistent and maintainable.

#### Acceptance Criteria

1. THE Personality_Templates SHALL include templates for: "verification_failed", "morning_briefing", "briefing_tasks", "briefing_recurring", "briefing_docs", "briefing_bugs", "no_report_yet", "memory_excluded", "memory_list_empty", "memory_list_header", "need_list_first"
2. THE TaskSkill, RecurringSkill, DocumentSkill, BugSkill, and MorningSkill SHALL use only personality templates for user-facing response strings (no hardcoded Hebrew strings outside of templates)
3. THE ChatSkill greet action SHALL use the get_greeting personality helper for response generation

### Requirement 25: Permission Enforcement Invariant

**User Story:** As a developer, I want every skill action to check permissions before executing, so that the role-based access control is enforced consistently.

#### Acceptance Criteria

1. THE TaskSkill SHALL check permissions before every action (create, list, delete, delete_all, complete, update)
2. THE BugSkill SHALL check permissions before every action (report, list)
3. THE MorningSkill SHALL check permissions before the summary report action
4. WHEN a permission check fails, THE skill SHALL return a Result with success=False and the "permission_denied" template before performing any database mutations

### Requirement 26: Verification Integrity Invariant

**User Story:** As a developer, I want every action that produces an entity_id to be verified against the database, so that data integrity is guaranteed.

#### Acceptance Criteria

1. WHEN the TaskSkill creates a task, THE TaskSkill verify method SHALL confirm the task exists in the database with status "open"
2. WHEN the TaskSkill deletes a task, THE TaskSkill verify method SHALL confirm the task status is "archived" in the database
3. WHEN the TaskSkill completes a task, THE TaskSkill verify method SHALL confirm the task status is "done" in the database
4. WHEN the TaskSkill updates a task, THE TaskSkill verify method SHALL confirm the task exists in the database
5. WHEN the RecurringSkill creates a pattern, THE RecurringSkill verify method SHALL confirm the pattern exists with is_active=True
6. WHEN the RecurringSkill deletes a pattern, THE RecurringSkill verify method SHALL confirm the pattern has is_active=False
7. WHEN the DocumentSkill saves a document, THE DocumentSkill verify method SHALL confirm the document exists in the database
8. WHEN the BugSkill reports a bug, THE BugSkill verify method SHALL confirm the bug report exists with status "open"

### Requirement 27: State Consistency Invariant

**User Story:** As a developer, I want conversation state updated after every successful action, so that index resolution and context tracking work correctly.

#### Acceptance Criteria

1. WHEN any skill action succeeds, THE Executor SHALL call update_state with the intent, entity_type, entity_id, and action from the Result
2. WHEN the TaskSkill list action succeeds, THE TaskSkill SHALL store the task ID order in the conversation state context field as "task_list_order"
3. WHEN a destructive action requires confirmation, THE skill SHALL call set_pending_confirmation with the action type and data

### Requirement 28: Zero LLM for CRUD Invariant

**User Story:** As a developer, I want CRUD skills to never call the LLM, so that structured operations are fast, deterministic, and cost-free.

#### Acceptance Criteria

1. THE TaskSkill SHALL produce all responses using personality templates and format helpers without calling any LLM service
2. THE RecurringSkill SHALL produce all responses using personality templates and format helpers without calling any LLM service
3. THE DocumentSkill SHALL produce all responses using personality templates and format helpers without calling any LLM service
4. THE BugSkill SHALL produce all responses using personality templates and format helpers without calling any LLM service
5. THE MorningSkill SHALL produce all responses using personality templates and format helpers without calling any LLM service

### Requirement 29: Confirmation Flow for Destructive Actions

**User Story:** As a family member, I want destructive actions to require confirmation, so that I don't accidentally delete tasks or reminders.

#### Acceptance Criteria

1. WHEN the TaskSkill delete action resolves a valid task, THE TaskSkill SHALL set pending_confirmation before archiving
2. WHEN the TaskSkill delete_all action finds open tasks, THE TaskSkill SHALL set pending_confirmation before bulk archiving
3. WHEN the RecurringSkill delete action resolves a valid pattern, THE RecurringSkill SHALL set pending_confirmation before deactivating
4. WHEN a confirmation is received, THE Executor SHALL resolve the pending action and re-dispatch to the target skill

### Requirement 30: Index Resolution Safety

**User Story:** As a developer, I want index-based operations to validate state before resolving, so that stale or missing list state produces a clear error instead of a crash.

#### Acceptance Criteria

1. WHEN an index-based operation is requested (delete, complete, update with index), THE TaskSkill SHALL check that "task_list_order" exists in the conversation state context
2. IF "task_list_order" does not exist in state, THEN THE TaskSkill SHALL return the "need_list_first" personality template
3. IF the provided index is less than 1 or greater than the length of task_list_order, THEN THE TaskSkill SHALL return the "task_not_found" personality template

### Requirement 31: Duplicate Detection for Task Creation

**User Story:** As a family member, I want the system to warn me about duplicate tasks, so that I don't accidentally create the same task twice.

#### Acceptance Criteria

1. WHEN a task creation is requested, THE TaskSkill SHALL query existing open tasks created by the same member with an exact title match within the last 5 minutes
2. IF a duplicate is found, THEN THE TaskSkill SHALL return the "task_similar_exists" personality template with the existing task title and set pending_confirmation
3. IF the member confirms creation despite the duplicate, THEN THE TaskSkill SHALL proceed to create the task normally

### Requirement 32: Test Coverage

**User Story:** As a developer, I want full test suites for each skill, so that all skill behavior is verified independently.

#### Acceptance Criteria

1. THE test suite SHALL include test_task_skill.py covering create, list, delete, delete_all, complete, and update actions
2. THE test suite SHALL include test_recurring_skill.py covering create, list, and delete actions
3. THE test suite SHALL include test_document_skill.py covering save and list actions
4. THE test suite SHALL include test_bug_skill.py covering report and list actions
5. THE test suite SHALL include test_chat_skill.py covering greet and respond actions
6. THE test suite SHALL include test_memory_skill.py covering store, recall, and list actions
7. THE test suite SHALL include test_morning_skill.py covering briefing and summary actions
8. WHEN the full test suite is run, all existing tests from Sprint R1 SHALL continue to pass
