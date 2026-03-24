# Requirements Document — Sprint R3: Wire + Test + Deploy

## Introduction

Sprint R3 is the final sprint before merging the Skills Engine rebuild to main. It validates the entire Skills Engine pipeline through end-to-end integration tests covering every skill, permission enforcement, confirmation flows, state consistency, conversation persistence, regression safety, and personality consistency. After all tests pass, unused imports from the old pipeline are cleaned up, the branch is merged to main, and documentation is updated.

## Glossary

- **Message_Handler**: The entry point (`src/services/message_handler.py`) that authenticates the sender, delegates to CommandParser, Executor, or ChatSkill, and saves conversations.
- **CommandParser**: The deterministic parser (`src/engine/command_parser.py`) that matches messages to Commands without LLM calls.
- **Executor**: The dispatch engine (`src/engine/executor.py`) that routes Commands to Skills, verifies results, updates state, and logs audits.
- **Skills_Engine**: The combined pipeline of CommandParser → Executor → ResponseFormatter.
- **Skill**: A self-contained module implementing BaseSkill that handles a domain (task, recurring, document, bug, chat, memory, morning, system).
- **ConversationState**: Per-member state tracking last intent, entity references, pending confirmations, and task_list_order context.
- **Conversation**: A database record storing message_in, message_out, intent, and member reference for every exchange.
- **Permission**: Role-based access control mapping roles (parent, child, grandparent) to read/write on resource types.
- **Personality_Templates**: Hebrew response templates in `src/prompts/personality.py` used by all skills for consistent tone.
- **Old_Pipeline**: Legacy services (workflow_engine, unified_handler, model_router, model_dispatch, intent_detector, routing_policy) that are no longer imported but remain on disk for Sprint R4 removal.

## Requirements

### Requirement 1: End-to-End Skill Integration Tests

**User Story:** As a developer, I want end-to-end tests that simulate the full WhatsApp message flow through Message_Handler, so that I can verify every skill works correctly from input to database to response.

#### Acceptance Criteria

1. WHEN a message "משימה חדשה: לקנות חלב" is received from a known parent phone, THE Message_Handler SHALL route through CommandParser to TaskSkill.create, persist a Task record in the database, and return a response containing "יצרתי משימה"
2. WHEN a message "משימות" is received from a known parent phone, THE Message_Handler SHALL return a formatted task list and store task_list_order in ConversationState context
3. WHEN a message "מחק משימה 1" is received after a task listing, followed by "כן", THE Message_Handler SHALL archive the referenced task and return a response containing "נמחקה"
4. WHEN a message "מחק משימה 1" is received after a task listing, followed by "לא", THE Message_Handler SHALL leave the task unarchived and clear ConversationState
5. WHEN a media message is received from a known parent phone, THE Message_Handler SHALL route to DocumentSkill.save, persist a Document record, and return a response containing "שמרתי"
6. WHEN a message "שלום" is received from a known parent phone, THE Message_Handler SHALL return a greeting containing the member name without invoking any LLM call
7. WHEN a message "באג: תמונה לא עובדת" is received from a known parent phone, THE Message_Handler SHALL persist a BugReport record and return a response matching the bug_reported template
8. WHEN a message "תזכורת חדשה: ארנונה, חודשי" is received from a known parent phone, THE Message_Handler SHALL persist a RecurringPattern record and return a response matching the recurring_created template
9. WHEN a message "עזרה" is received from a known member phone, THE Message_Handler SHALL return a skill list in Hebrew
10. WHEN a message "בוקר" is received from a known parent phone, THE Message_Handler SHALL return a morning briefing containing task and bug counts
11. WHEN an unrecognized message is received from a known member phone, THE Message_Handler SHALL delegate to ChatSkill.respond with a mocked LLM and save the conversation with intent "chat.respond"
12. WHEN a message is received from an unknown phone number, THE Message_Handler SHALL return the unknown_member template and save a Conversation record with None member_id
13. WHEN a message is received from an inactive member phone, THE Message_Handler SHALL return the inactive_member template

### Requirement 2: Permission Enforcement End-to-End Tests

**User Story:** As a developer, I want end-to-end tests that verify role-based access control across all skills, so that I can confirm children and grandparents cannot perform unauthorized actions.

#### Acceptance Criteria

1. WHEN a parent sends a task creation message, THE Message_Handler SHALL return a success response
2. WHEN a child sends a task creation message, THE Message_Handler SHALL return the permission_denied template containing 🔒
3. WHEN a parent sends a task list message, THE Message_Handler SHALL return the task list
4. WHEN a child sends a task list message, THE Message_Handler SHALL return the task list (read access allowed)
5. WHEN a parent sends a task deletion message, THE Message_Handler SHALL proceed with the confirmation flow
6. WHEN a child sends a task deletion message, THE Message_Handler SHALL return the permission_denied template containing 🔒
7. WHEN a parent sends a bug report message, THE Message_Handler SHALL persist the BugReport and return success
8. WHEN a child sends a bug report message, THE Message_Handler SHALL return the permission_denied template containing 🔒
9. WHEN a parent sends a summary request, THE Message_Handler SHALL return the summary
10. WHEN a child sends a summary request, THE Message_Handler SHALL return the permission_denied template containing 🔒
11. WHEN a grandparent sends a task list message, THE Message_Handler SHALL return the task list (read access allowed)
12. WHEN a grandparent sends a task creation message, THE Message_Handler SHALL return the permission_denied template containing 🔒

### Requirement 3: Confirmation Flow End-to-End Tests

**User Story:** As a developer, I want end-to-end tests for all destructive action confirmation flows, so that I can verify the confirm/deny/ignore paths work correctly for every destructive operation.

#### Acceptance Criteria

1. WHEN a task delete is initiated and the member responds "כן", THE Message_Handler SHALL archive the task and return a deletion confirmation
2. WHEN a task delete is initiated and the member responds "לא", THE Message_Handler SHALL leave the task unarchived and clear ConversationState
3. WHEN a task delete is initiated and the member sends an unrelated message, THE Message_Handler SHALL clear ConversationState and process the new message normally
4. WHEN a delete-all-tasks is initiated and the member responds "כן", THE Message_Handler SHALL archive all open tasks
5. WHEN a delete-all-tasks is initiated and the member responds "לא", THE Message_Handler SHALL leave all tasks unarchived
6. WHEN a recurring pattern delete is initiated and the member responds "כן", THE Message_Handler SHALL deactivate the recurring pattern
7. WHEN a duplicate task is detected and the member responds "כן", THE Message_Handler SHALL create the task regardless of the duplicate
8. WHEN a duplicate task is detected and the member responds "לא", THE Message_Handler SHALL leave the duplicate uncreated

### Requirement 4: State Consistency End-to-End Tests

**User Story:** As a developer, I want end-to-end tests that verify ConversationState is correctly maintained across multi-step interactions, so that I can confirm index resolution, state clearing, and sequential operations work correctly.

#### Acceptance Criteria

1. WHEN a task is created, THE ConversationState SHALL contain entity_type "task", the created task entity_id, and action "created"
2. WHEN tasks are listed, THE ConversationState SHALL contain task_list_order in context with the correct task IDs in display order
3. WHEN "מחק 2" is sent after a task listing, THE Executor SHALL resolve the correct task from task_list_order at index 2
4. WHEN "סיים 1" is sent after a task listing, THE Executor SHALL resolve the correct task from task_list_order at index 1
5. WHEN "עזוב" is sent, THE ConversationState SHALL be cleared completely (all fields reset to defaults)
6. WHEN "כן" is sent with no pending confirmation, THE Message_Handler SHALL return "אין פעולה ממתינה"
7. WHEN a task is created, then tasks are listed, then task 1 is deleted, then tasks are listed again, THE Message_Handler SHALL return correct indices reflecting the updated task set

### Requirement 5: Conversation Persistence End-to-End Tests

**User Story:** As a developer, I want end-to-end tests that verify every skill action saves a Conversation record, so that I can confirm the full message history is persisted correctly.

#### Acceptance Criteria

1. WHEN any skill action is executed through Message_Handler, THE Message_Handler SHALL save a Conversation record to the database
2. THE Conversation.intent field SHALL match the format "{skill_name}.{action_name}" for all skill-routed messages
3. THE Conversation.message_in field SHALL contain the original message text sent by the member
4. THE Conversation.message_out field SHALL contain the response text returned to the member
5. WHEN a message is received from an unknown phone, THE Message_Handler SHALL save a Conversation record with None as family_member_id
6. WHEN an unrecognized message triggers LLM fallback, THE Message_Handler SHALL save the Conversation with intent "chat.respond"

### Requirement 6: Regression Safety Tests

**User Story:** As a developer, I want regression tests covering edge cases and Hebrew keyword boundaries, so that I can prevent regressions in command parsing and message handling.

#### Acceptance Criteria

1. WHEN any of the Hebrew cancel keywords (לא, עזוב, תעזוב, בטל, תבטל, ביטול) is sent as a standalone message, THE CommandParser SHALL return a cancel Command
2. WHEN any of the Hebrew confirm keywords (כן, אישור, אשר, בטח, אוקיי, אוקי) is sent as a standalone message, THE CommandParser SHALL return a confirm Command
3. WHEN "משימה" (singular, no action verb) is sent, THE CommandParser SHALL route to task list and not trigger a delete action
4. WHEN a media message is received alongside text content, THE CommandParser SHALL prioritize media handling over text parsing
5. WHEN an empty message is received, THE Message_Handler SHALL delegate to LLM fallback via ChatSkill
6. WHEN a message exceeding 3500 characters is received, THE Response_Formatter SHALL truncate the response and append the truncation indicator
7. WHEN a message containing mixed Hebrew and English text is received, THE CommandParser SHALL attempt pattern matching normally
8. WHEN a message containing only emojis is received, THE Message_Handler SHALL delegate to LLM fallback via ChatSkill
9. WHEN a message containing only numbers is received, THE Message_Handler SHALL delegate to LLM fallback via ChatSkill

### Requirement 7: Personality Consistency Tests

**User Story:** As a developer, I want tests that verify all skill responses use personality templates consistently, so that I can confirm the bot never returns raw English error messages or inconsistent formatting.

#### Acceptance Criteria

1. WHEN any skill returns an error response, THE Skill SHALL use a Personality_Templates value (not a hardcoded string)
2. WHEN permission is denied, THE response SHALL contain the 🔒 emoji from the permission_denied template
3. WHEN verification fails, THE response SHALL match the verification_failed template
4. WHEN a greeting is returned, THE response SHALL include the member name
5. WHEN a greeting is returned at different times of day, THE response SHALL use the appropriate time-of-day template (morning, afternoon, evening, night)
6. WHEN a task list is returned, THE response SHALL use priority emojis (🔴 for urgent, 🟡 for high, 🟢 for normal, ⚪ for low)
7. THE Message_Handler SHALL return responses containing only Hebrew text and emojis, with no English error messages

### Requirement 8: Clean Up Unused Imports

**User Story:** As a developer, I want all unused imports from the old pipeline removed from active code, so that the Skills Engine is the sole message processing path with no dead references.

#### Acceptance Criteria

1. THE message_handler.py file SHALL NOT contain an import statement for workflow_engine
2. THE message_handler.py file SHALL NOT contain an import statement for unified_handler
3. THE message_handler.py file SHALL NOT contain an import statement for model_router
4. THE message_handler.py file SHALL NOT contain an import statement for model_dispatch
5. THE message_handler.py file SHALL NOT contain an import statement for intent_detector
6. THE message_handler.py file SHALL NOT contain an import statement for routing_policy
7. THE files in the skills/ and engine/ directories SHALL NOT contain import statements referencing Old_Pipeline modules (workflow_engine, unified_handler, model_router, model_dispatch, intent_detector, routing_policy)
8. THE Old_Pipeline source files SHALL remain on disk (deletion is deferred to Sprint R4)

### Requirement 9: Merge to Main

**User Story:** As a developer, I want the rebuild/skills-engine branch merged to main after all tests pass, so that the Skills Engine becomes the production codebase.

#### Acceptance Criteria

1. WHEN all tests (Sprint R1, R2, and R3) pass on the rebuild/skills-engine branch, THE Developer SHALL merge to main using a standard merge (not squash)
2. IF merge conflicts arise, THEN THE Developer SHALL resolve conflicts by keeping the rebuild/skills-engine version
3. WHEN the merge is complete, THE full test suite SHALL pass on the main branch

### Requirement 10: Update README Roadmap

**User Story:** As a developer, I want the README roadmap updated to reflect the completion of Sprints R1, R2, and R3, so that the project status is accurate.

#### Acceptance Criteria

1. THE README.md roadmap table SHALL contain a row for "R2 — Core Skills Migration" with status "✅ Complete"
2. THE README.md roadmap table SHALL contain a row for "R3 — Wire + Test + Deploy" with status "✅ Complete"
3. THE README.md "Current Version" line SHALL read "Phase R3 — Skills Engine"
4. THE README.md status section SHALL reflect the updated test count after Sprint R3

### Requirement 11: Deployment Documentation Update

**User Story:** As a developer, I want the deployment documentation updated with the Skills Engine architecture, so that future contributors understand the current system design.

#### Acceptance Criteria

1. THE docs/setup.md file SHALL contain a "Skills Engine Architecture" section describing the CommandParser → Executor → Skill pipeline
2. THE docs/setup.md file SHALL contain an "Available Skills" section listing all 8 registered skills (system, task, recurring, document, bug, chat, memory, morning) with a one-line description each
3. THE docs/setup.md file SHALL contain a "How to Add a New Skill" section with step-by-step instructions for creating and registering a new skill
