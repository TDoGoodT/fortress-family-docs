# Requirements Document

## Introduction

STABLE-6 for the Fortress family assistant system. This release covers two areas: (A) critical bugfixes for the memory pipeline and session handling, plus diagnostic logging for photo uploads, and (B) a new parents-only bug tracker feature allowing family members to report and list bugs via WhatsApp in Hebrew.

## Glossary

- **Fortress**: The family assistant WhatsApp bot system (FastAPI + LangGraph + PostgreSQL)
- **Memory_Service**: The module (`memory_service.py`) responsible for saving, loading, and expiring conversational memories
- **Workflow_Engine**: The LangGraph StateGraph orchestrator (`workflow_engine.py`) that routes messages through intent detection, permissions, action handlers, memory save, and conversation save nodes
- **Intent_Detector**: The keyword-matching module (`intent_detector.py`) that classifies incoming messages into intent categories
- **Unified_Handler**: The LLM-based classifier+responder (`unified_handler.py`) used when keyword matching fails
- **Personality_Module**: The module (`personality.py`) containing Hebrew response templates and formatting functions
- **Routing_Policy**: The module (`routing_policy.py`) mapping intents to sensitivity levels and LLM provider routes
- **Bug_Tracker**: The new subsystem for reporting and listing bugs via WhatsApp
- **BugReport**: The ORM model representing a bug report record in the database
- **Valid_Categories**: The set of memory categories allowed by the database CHECK constraint: `preference`, `goal`, `fact`, `habit`, `context`
- **MEMORY_EXTRACTOR**: The LLM system prompt used to extract facts from conversations
- **Pipeline**: The sequence of LangGraph nodes from intent detection through conversation save
- **Session**: The SQLAlchemy database session used within a single request

## Requirements

### Requirement 1: Memory Category Validation

**User Story:** As a system operator, I want invalid memory categories returned by the LLM to be caught before database insertion, so that IntegrityError crashes are prevented.

#### Acceptance Criteria

1. WHEN the Memory_Service `save_memory()` function receives a category value, THE Memory_Service SHALL validate that the category is one of the Valid_Categories (`preference`, `goal`, `fact`, `habit`, `context`) before inserting into the database
2. WHEN the Memory_Service `save_memory()` function receives the category value `task`, THE Memory_Service SHALL map it to `context` and proceed with the save
3. WHEN the Memory_Service `save_memory()` function receives a category value not in Valid_Categories and not mappable, THE Memory_Service SHALL default the category to `context` and log a warning with the original invalid category value
4. THE Memory_Service SHALL define a `VALID_CATEGORIES` constant set containing `preference`, `goal`, `fact`, `habit`, `context`
5. THE Memory_Service SHALL define a `CATEGORY_MAP` dictionary mapping known invalid categories to valid ones (at minimum: `task` → `context`)

### Requirement 2: MEMORY_EXTRACTOR Prompt Category Enforcement

**User Story:** As a system operator, I want the MEMORY_EXTRACTOR prompt to explicitly list valid categories in Hebrew, so that the LLM is less likely to return invalid categories.

#### Acceptance Criteria

1. THE MEMORY_EXTRACTOR prompt in `system_prompts.py` SHALL list the valid categories explicitly as: `preference`, `goal`, `fact`, `habit`, `context`
2. THE MEMORY_EXTRACTOR prompt SHALL instruct the LLM in Hebrew that only these five categories are permitted
3. THE MEMORY_EXTRACTOR prompt SHALL instruct the LLM to use `context` as the default category when uncertain

### Requirement 3: Session Rollback Resilience in Memory Save Node

**User Story:** As a system operator, I want the memory save node to handle database failures gracefully, so that a failed memory save does not put the session into an unusable rollback state.

#### Acceptance Criteria

1. WHEN the `memory_save_node` in the Workflow_Engine encounters a database exception, THE Workflow_Engine SHALL execute `session.rollback()` on the database session before returning
2. WHEN the `memory_save_node` fails, THE Workflow_Engine SHALL log the exception at error level
3. WHEN the `memory_save_node` fails, THE Workflow_Engine SHALL return an empty dict without a `response` key, preserving the existing response in state

### Requirement 4: Session Rollback Resilience in Conversation Save Node

**User Story:** As a system operator, I want the conversation save node to handle database failures gracefully, so that a PendingRollbackError from a prior node failure does not crash the pipeline.

#### Acceptance Criteria

1. WHEN the `conversation_save_node` in the Workflow_Engine encounters a database exception, THE Workflow_Engine SHALL execute `session.rollback()` on the database session before returning
2. WHEN the `conversation_save_node` fails, THE Workflow_Engine SHALL log the exception at error level
3. WHEN the `conversation_save_node` fails, THE Workflow_Engine SHALL return an empty dict without a `response` key, preserving the existing response in state
4. WHEN the `conversation_save_node` encounters a `PendingRollbackError`, THE Workflow_Engine SHALL recover the session via rollback and log the root cause

### Requirement 5: Photo Upload Diagnostic Logging

**User Story:** As a system operator, I want detailed logging for photo uploads, so that I can diagnose why photo uploads are not working.

#### Acceptance Criteria

1. WHEN the Workflow_Engine `_handle_upload_document` handler is invoked, THE Workflow_Engine SHALL log the values of `has_media`, `media_file_path`, and `member.name` at info level before processing
2. WHEN the WhatsApp webhook receives a message with media, THE WhatsApp router SHALL log the media type, MIME type, and filename from the payload at info level

### Requirement 6: Bug Reports Database Table

**User Story:** As a developer, I want a `bug_reports` table in the database, so that bug reports can be persisted.

#### Acceptance Criteria

1. THE database migration `006_bug_reports.sql` SHALL create a `bug_reports` table with the following columns: `id` (UUID primary key, default `gen_random_uuid()`), `reported_by` (UUID foreign key to `family_members.id`), `description` (TEXT, NOT NULL), `status` (TEXT, NOT NULL, default `open`), `priority` (TEXT, default `normal`), `metadata` (JSONB, default `{}`), `created_at` (TIMESTAMPTZ, default `now()`), `resolved_at` (TIMESTAMPTZ, nullable)
2. THE `status` column SHALL have a CHECK constraint allowing only: `open`, `fixed`, `wont_fix`, `duplicate`
3. THE `priority` column SHALL have a CHECK constraint allowing only: `low`, `normal`, `high`, `critical`
4. THE migration SHALL create indexes on `reported_by`, `status`, and `created_at`

### Requirement 7: BugReport ORM Model

**User Story:** As a developer, I want a SQLAlchemy ORM model for bug reports, so that the application can interact with the `bug_reports` table.

#### Acceptance Criteria

1. THE BugReport model in `schema.py` SHALL use SQLAlchemy 2.0 `mapped_column` style, consistent with existing models
2. THE BugReport model SHALL define all columns matching the `bug_reports` table schema from Requirement 6
3. THE BugReport model SHALL define a `relationship` to `FamilyMember` via the `reported_by` foreign key
4. THE FamilyMember model SHALL define a reverse `relationship` named `bug_reports` to the BugReport model

### Requirement 8: Bug Tracker Intent Detection

**User Story:** As a parent, I want to report a bug by typing "באג:" or "bug:" and list bugs by typing "באגים" or "bugs", so that I can interact with the bug tracker via WhatsApp keywords.

#### Acceptance Criteria

1. WHEN a message starts with "באג:" or "bug:", THE Intent_Detector SHALL return the intent `report_bug`
2. WHEN a message equals "באג" or "bug", THE Intent_Detector SHALL return the intent `report_bug`
3. WHEN a message equals "באגים" or "bugs" or "רשימת באגים", THE Intent_Detector SHALL return the intent `list_bugs`
4. THE Intent_Detector INTENTS dictionary SHALL include `report_bug` with `model_tier: "local"` and `list_bugs` with `model_tier: "local"`
5. THE VALID_INTENTS set SHALL include `report_bug` and `list_bugs`

### Requirement 9: Bug Tracker Routing and Permissions

**User Story:** As a system designer, I want bug tracker intents routed at medium sensitivity and restricted to parents only, so that the feature follows existing security patterns.

#### Acceptance Criteria

1. THE Routing_Policy SENSITIVITY_MAP SHALL map `report_bug` to `medium` and `list_bugs` to `medium`
2. THE Workflow_Engine _PERMISSION_MAP SHALL map `report_bug` to `("tasks", "write")` and `list_bugs` to `("tasks", "read")`
3. WHEN a non-parent family member sends a `report_bug` or `list_bugs` message, THE Workflow_Engine SHALL return the `permission_denied` personality template

### Requirement 10: Bug Tracker Personality Templates

**User Story:** As a parent, I want bug tracker responses in Hebrew using the Fortress personality, so that the experience is consistent with other features.

#### Acceptance Criteria

1. THE Personality_Module TEMPLATES dictionary SHALL include the key `bug_reported` with a Hebrew confirmation template containing a `{description}` placeholder
2. THE Personality_Module TEMPLATES dictionary SHALL include the key `bug_list_header` with a Hebrew header for the bug list
3. THE Personality_Module TEMPLATES dictionary SHALL include the key `bug_list_empty` with a Hebrew message indicating no open bugs
4. THE Personality_Module TEMPLATES dictionary SHALL include the key `bug_list_item` with a Hebrew template containing `{index}`, `{description}`, `{priority}`, and `{created_at}` placeholders
5. THE Personality_Module SHALL define a `format_bug_list()` function that accepts a list of BugReport objects and returns a formatted Hebrew string, following the same pattern as `format_task_list()`

### Requirement 11: Bug Tracker Workflow Handlers

**User Story:** As a parent, I want to report a bug and see a list of open bugs via WhatsApp, so that I can track issues with the system.

#### Acceptance Criteria

1. WHEN the intent is `report_bug`, THE Workflow_Engine SHALL extract the bug description from the message by stripping the "באג:"/"bug:" prefix
2. WHEN the intent is `report_bug`, THE Workflow_Engine SHALL create a BugReport record with the extracted description, `reported_by` set to the current member's ID, status `open`, and priority `normal`
3. WHEN the intent is `report_bug`, THE Workflow_Engine SHALL return the `bug_reported` personality template with the description
4. WHEN the intent is `list_bugs`, THE Workflow_Engine SHALL query all BugReport records with status `open`, ordered by `created_at` descending
5. WHEN the intent is `list_bugs`, THE Workflow_Engine SHALL format the results using `format_bug_list()` and return the formatted string
6. THE Workflow_Engine _ACTION_HANDLERS dictionary SHALL include entries for `report_bug` and `list_bugs`

### Requirement 12: Unified Handler Bug Tracker Integration

**User Story:** As a system designer, I want the unified LLM handler to recognize bug tracker intents, so that messages not caught by keyword matching can still be routed to the bug tracker.

#### Acceptance Criteria

1. THE UNIFIED_CLASSIFY_AND_RESPOND prompt SHALL include `report_bug` and `list_bugs` in the list of valid intents
2. THE UNIFIED_CLASSIFY_AND_RESPOND prompt SHALL include Hebrew descriptions for `report_bug` (user wants to report a bug) and `list_bugs` (user wants to see bug list)
3. THE VALID_INTENTS set in `intent_detector.py` SHALL include `report_bug` and `list_bugs` (same as Requirement 8.5)

### Requirement 13: Existing Test Suite Compatibility

**User Story:** As a developer, I want all 262 existing tests to continue passing after these changes, so that no regressions are introduced.

#### Acceptance Criteria

1. WHEN the full test suite is executed, THE system SHALL pass all 262 previously existing tests without modification to those tests
2. THE new code SHALL follow existing patterns for imports, naming conventions, and module structure
