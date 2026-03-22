# Requirements Document

## Introduction

STABLE Step 3 — Core Flows Hardening for the Fortress family WhatsApp bot. Production testing revealed six gaps: no delete_task capability (Hebrew "מחק משימה" creates a new task instead of deleting), no duplicate task prevention, LLM hallucinating actions it cannot perform (e.g. claiming "deleted" without actually deleting), corrupt data from the old Ollama era in the database, task owner/creator not extracted from messages, and prompts containing unnecessary English duplication alongside Hebrew. This spec addresses all six gaps plus the required tests and README update.

## Glossary

- **Intent_Detector**: The synchronous keyword-matching module at `fortress/src/services/intent_detector.py` that classifies incoming messages into intents.
- **Routing_Policy**: The sensitivity-based routing module at `fortress/src/services/routing_policy.py` that maps intents to LLM provider chains.
- **Workflow_Engine**: The LangGraph-based workflow engine at `fortress/src/services/workflow_engine.py` that orchestrates intent detection, permission checks, action dispatch, and response generation.
- **Unified_Handler**: The single-LLM-call classify-and-respond handler at `fortress/src/services/unified_handler.py`.
- **System_Prompts**: The LLM prompt templates module at `fortress/src/prompts/system_prompts.py`.
- **Personality_Module**: The Hebrew personality templates module at `fortress/src/prompts/personality.py`.
- **Task_Service**: The task CRUD module at `fortress/src/services/tasks.py` containing `create_task`, `list_tasks`, `complete_task`, `archive_task`.
- **Family_Member**: A record in the `family_members` table representing a household member, with `id`, `name`, `phone`, and `role` fields.
- **Task**: A record in the `tasks` table with `id`, `title`, `status`, `assigned_to`, `created_by`, `created_at`, and other fields. Status values include `open`, `done`, and `archived`.
- **Soft_Delete**: Setting a task's status to `archived` instead of removing the row from the database.
- **Duplicate_Task**: A task with the same title (case-insensitive), same `assigned_to`, status `open`, and `created_at` within the last 5 minutes of the current time.
- **Corrupt_Data**: Task rows created during the Ollama era that have empty titles, null `created_by`, or garbled non-Hebrew/non-ASCII content in the title field.

## Requirements

### Requirement 1: Delete Task Intent Detection

**User Story:** As a family member, I want to say "מחק משימה" in WhatsApp and have the bot recognize it as a delete request, so that I can remove tasks I no longer need.

#### Acceptance Criteria

1. WHEN a message contains "מחק משימה", THE Intent_Detector SHALL return `delete_task`.
2. WHEN a message contains "מחק" as a standalone keyword, THE Intent_Detector SHALL return `delete_task`.
3. WHEN a message contains "הסר משימה", THE Intent_Detector SHALL return `delete_task`.
4. WHEN a message contains "delete task" (case-insensitive), THE Intent_Detector SHALL return `delete_task`.
5. WHEN a message contains "בטל משימה", THE Intent_Detector SHALL return `delete_task`.
6. THE Intent_Detector INTENTS dictionary SHALL include a `delete_task` entry with `model_tier` set to `local`.

### Requirement 2: Delete Task Routing

**User Story:** As a developer, I want the delete_task intent to have a defined sensitivity level, so that the routing policy can select the correct LLM provider chain.

#### Acceptance Criteria

1. THE Routing_Policy SENSITIVITY_MAP SHALL include `delete_task` with sensitivity level `medium`.

### Requirement 3: Delete Task Workflow Handler

**User Story:** As a family member, I want the bot to identify which task to delete and soft-delete it, so that I get confirmation of the deletion without losing data permanently.

#### Acceptance Criteria

1. WHEN the intent is `delete_task` and the message contains a task number (e.g. "מחק משימה 3"), THE Workflow_Engine SHALL identify the task at that position in the member's open task list and archive it using Soft_Delete.
2. WHEN the intent is `delete_task` and the message contains a task title (e.g. "מחק לקנות חלב"), THE Workflow_Engine SHALL find the matching open task by case-insensitive title comparison and archive it using Soft_Delete.
3. WHEN the intent is `delete_task` and the specific task is successfully identified and archived, THE Workflow_Engine SHALL respond using the Personality_Module `task_deleted` template with the task title.
4. WHEN the intent is `delete_task` and the specific task cannot be identified from the message, THE Workflow_Engine SHALL respond using the Personality_Module `task_delete_which` template with a numbered list of the member's open tasks.
5. WHEN the intent is `delete_task` and the referenced task does not exist in the member's open tasks, THE Workflow_Engine SHALL respond using the Personality_Module `task_not_found` template.
6. THE Workflow_Engine SHALL use `archive_task()` from the Task_Service for deletion, setting status to `archived` (Soft_Delete).

### Requirement 4: Delete Task in Unified LLM Handler

**User Story:** As a developer, I want the unified LLM prompt to recognize delete_task intent and extract the delete target, so that the LLM path also supports task deletion.

#### Acceptance Criteria

1. THE System_Prompts UNIFIED_CLASSIFY_AND_RESPOND SHALL list `delete_task` in the intent classification options with the Hebrew description "המשתמש רוצה למחוק או לבטל משימה".
2. THE System_Prompts UNIFIED_CLASSIFY_AND_RESPOND JSON response format SHALL include a `delete_target` field (task number, title string, or null).

### Requirement 5: Delete Task Personality Templates

**User Story:** As a family member, I want deletion responses to match the bot's warm Hebrew personality, so that the experience feels consistent.

#### Acceptance Criteria

1. THE Personality_Module TEMPLATES SHALL include a `task_deleted` entry with value "משימה נמחקה: {title} ✅".
2. THE Personality_Module TEMPLATES SHALL include a `task_delete_which` entry with value "איזו משימה למחוק? 🤔\n{task_list}".
3. THE Personality_Module TEMPLATES SHALL include a `task_not_found` entry with value "לא מצאתי את המשימה הזו 🤷".

### Requirement 6: Task Owner Assignment from Messages

**User Story:** As a family member, I want the bot to understand who a task is assigned to when I say something like "תזכיר לשגב לקנות חלב", so that tasks are assigned to the correct person.

#### Acceptance Criteria

1. THE System_Prompts TASK_EXTRACTOR_BEDROCK SHALL include an `assigned_to` field in the JSON extraction schema, with Hebrew instructions for extracting the assignee name from the message.
2. THE System_Prompts UNIFIED_CLASSIFY_AND_RESPOND SHALL include an `assigned_to` field in the `task_data` section of the JSON response format.
3. WHEN creating a task with an `assigned_to` name string, THE Workflow_Engine SHALL search the `family_members` table by name using case-insensitive partial matching.
4. WHEN the name matches a Family_Member, THE Workflow_Engine SHALL set the task's `assigned_to` to that Family_Member's `id`.
5. WHEN the name does not match any Family_Member, THE Workflow_Engine SHALL assign the task to the sender's `id` and log a warning.
6. THE Workflow_Engine SHALL set `created_by` to the sender's Family_Member `id` on every task creation.

### Requirement 7: Prevent Duplicate Tasks

**User Story:** As a family member, I want the bot to detect when I accidentally send the same task twice, so that I don't end up with duplicate entries.

#### Acceptance Criteria

1. WHEN creating a task, THE Workflow_Engine SHALL check for an existing Duplicate_Task (same title case-insensitive, same `assigned_to`, status `open`, created within the last 5 minutes).
2. WHEN a Duplicate_Task is found, THE Workflow_Engine SHALL skip task creation and respond using the Personality_Module `task_duplicate` template.
3. THE Personality_Module TEMPLATES SHALL include a `task_duplicate` entry with value "המשימה הזו כבר קיימת ✅".

### Requirement 8: Prevent LLM Hallucinated Actions

**User Story:** As a developer, I want the LLM to never claim it performed an action (like deleting or completing a task) that it did not actually perform, so that users are not misled.

#### Acceptance Criteria

1. THE System_Prompts UNIFIED_CLASSIFY_AND_RESPOND SHALL contain an explicit Hebrew instruction telling the LLM: "אל תמציא פעולות שלא ביצעת. אם לא מחקת/השלמת/יצרת משימה בפועל — אל תגיד שעשית את זה. תאר רק מה שאתה באמת עושה: מסווג כוונה ומייצר תשובה."
2. THE System_Prompts UNIFIED_CLASSIFY_AND_RESPOND SHALL instruct the LLM to only classify intent and generate a response, and to leave actual task operations to the system.

### Requirement 9: Hebrew-Only Prompt Cleanup

**User Story:** As a developer, I want all LLM instruction prompts to be in Hebrew only (with English JSON field names), so that prompts are concise and non-duplicative.

#### Acceptance Criteria

1. WHEN a prompt in System_Prompts contains instructions in both English and Hebrew conveying the same meaning, THE System_Prompts module SHALL retain only the Hebrew version.
2. THE System_Prompts module SHALL keep JSON field names, enum values, and code identifiers in English.
3. THE System_Prompts TASK_EXTRACTOR_BEDROCK SHALL have its LLM instructions in Hebrew only.
4. THE System_Prompts FORTRESS_BASE SHALL have its LLM instructions in Hebrew only.

### Requirement 10: Database Cleanup Migration

**User Story:** As a developer, I want a migration script that archives corrupt data from the Ollama era and deduplicates tasks, so that the database is clean for production use.

#### Acceptance Criteria

1. THE migration file `fortress/migrations/005_cleanup_corrupt_data.sql` SHALL archive tasks with empty or null titles by setting their status to `archived`.
2. THE migration file SHALL archive tasks with null `created_by` by setting their status to `archived`.
3. THE migration file SHALL deduplicate open tasks that share the same title (case-insensitive) and `assigned_to`, keeping only the most recently created one and archiving the rest.
4. THE migration file SHALL use Soft_Delete (status = `archived`) for all cleanup operations.

### Requirement 11: Test Coverage

**User Story:** As a developer, I want comprehensive tests for all new functionality, so that I can verify correctness and prevent regressions.

#### Acceptance Criteria

1. THE test suite SHALL include `tests/test_delete_task.py` covering: keyword detection for all five Hebrew/English delete keywords, delete by task number, delete by title match, ambiguous delete prompting for clarification, and task-not-found handling.
2. THE test suite SHALL update `tests/test_intent_detector.py` to include `delete_task` in the required intents set and add keyword matching tests for delete keywords.
3. THE test suite SHALL update `tests/test_personality.py` to verify the presence of `task_deleted`, `task_delete_which`, `task_not_found`, and `task_duplicate` template keys.
4. THE test suite SHALL include `tests/test_task_owner.py` covering: name-to-member resolution with exact match, partial match, case-insensitive match, no-match fallback to sender, and `created_by` always set to sender.
5. THE test suite SHALL include `tests/test_duplicate_prevention.py` covering: duplicate detected within 5 minutes, no duplicate when title differs, no duplicate when assigned_to differs, no duplicate when older than 5 minutes, and no duplicate when existing task is not open.
6. WHEN all new tests pass, THE existing 201 tests SHALL continue to pass without modification.

### Requirement 12: README Roadmap Update

**User Story:** As a developer, I want the README roadmap to reflect the STABLE-3 milestone, so that the project history is accurate.

#### Acceptance Criteria

1. WHEN the core-flows-hardening feature is complete, THE README SHALL contain a new row in the roadmap table for "STABLE-3 — Core Flows Hardening" with status "✅ Complete" and an updated test count.
