# Implementation Plan: Core Skills Migration (Sprint R2)

## Overview

Migrate all existing Fortress functionality into 7 self-contained Skills that plug into the Skills Engine from Sprint R1. Each skill wraps existing service-layer functions, uses personality templates for responses, and enforces RBAC via a shared `_check_perm` helper. Implementation follows the user-specified order: personality templates → TaskSkill → RecurringSkill → DocumentSkill → BugSkill → ChatSkill → MemorySkill → MorningSkill → registration → message handler update → tests.

## Tasks

- [x] 1. Add personality templates and permission helper
  - [x] 1.1 Add new personality templates to `fortress/src/prompts/personality.py`
    - Add the following keys to the `TEMPLATES` dict: `"morning_briefing"`, `"briefing_tasks"`, `"briefing_recurring"`, `"briefing_docs"`, `"briefing_bugs"`, `"no_report_yet"`, `"memory_excluded"`, `"memory_list_empty"`, `"memory_list_header"`
    - Verify `"need_list_first"`, `"verification_failed"`, `"task_similar_exists"`, `"confirm_delete"` already exist
    - _Requirements: 24.1_

  - [x] 1.2 Create shared `_check_perm` helper module
    - Create a module-level function (e.g. in a new file or at the top of each skill) that calls `check_permission(db, member.phone, resource, action)` and returns `Result(success=False, message=TEMPLATES["permission_denied"])` if denied, else `None`
    - This helper is imported by all skills that enforce RBAC
    - _Requirements: 25.1, 25.2, 25.3, 25.4_

- [x] 2. Implement TaskSkill — `fortress/src/skills/task_skill.py`
  - [x] 2.1 Create TaskSkill class with BaseSkill interface
    - Implement `name`, `description`, `commands` properties with all 6 regex patterns (create, list, delete, delete_all, complete, update)
    - Implement `execute` dispatcher that routes to `_create`, `_list`, `_delete`, `_delete_all`, `_complete`, `_update`
    - Implement `get_help` returning Hebrew help text
    - _Requirements: 1.1, 2.1, 3.1, 4.1, 5.1, 6.1_

  - [x] 2.2 Implement TaskSkill._create with duplicate detection
    - Check permission (tasks/write) via `_check_perm`
    - Query for duplicate tasks (same title, same member, last 5 minutes)
    - If duplicate found: return `task_similar_exists` template and set `pending_confirmation`
    - If no duplicate: call `tasks.create_task`, return Result with entity_type="task", action="created"
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.7, 1.8, 31.1, 31.2, 31.3_

  - [x] 2.3 Implement TaskSkill._list with task_list_order state storage
    - Check permission (tasks/read) via `_check_perm`
    - Call `tasks.list_tasks(status="open")`, store task IDs as `task_list_order` in conversation state context
    - Format with `format_task_list`, return empty template if no tasks
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 27.2_

  - [x] 2.4 Implement TaskSkill._delete with index resolution and confirmation
    - Check permission (tasks/write), resolve index from `task_list_order` in state
    - Return `need_list_first` if no task_list_order, `task_not_found` if out of range
    - Set `pending_confirmation` with task details, return `confirm_delete` template
    - On confirmed re-dispatch: call `tasks.archive_task`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 29.1, 30.1, 30.2, 30.3_

  - [x] 2.5 Implement TaskSkill._delete_all with bulk confirmation
    - Check permission (tasks/write), query open task count
    - Set `pending_confirmation` with count and task list, return `bulk_delete_confirm` template
    - On confirmed re-dispatch: archive all open tasks, return `bulk_deleted` template
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 29.2_

  - [x] 2.6 Implement TaskSkill._complete with index and last_entity_id fallback
    - Check permission (tasks/write), resolve task by index or `last_entity_id` from state
    - Call `tasks.complete_task`, return Result with entity_type="task", action="completed"
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8_

  - [x] 2.7 Implement TaskSkill._update with change parsing
    - Check permission (tasks/write), resolve task by index or `last_entity_id`
    - Parse changes from text (due_date, title, priority, assigned_to)
    - Apply updates via service layer, return `task_updated` template
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8_

  - [x] 2.8 Implement TaskSkill.verify method
    - Check DB state per action: created→status "open", deleted→status "archived", completed→status "done", updated→task exists
    - _Requirements: 1.6, 3.5, 5.6, 6.7, 26.1, 26.2, 26.3, 26.4_

- [x] 3. Implement RecurringSkill — `fortress/src/skills/recurring_skill.py`
  - [x] 3.1 Create RecurringSkill class with BaseSkill interface
    - Implement `name`, `description`, `commands` with 3 regex patterns (create, list, delete)
    - Implement Hebrew frequency parsing: יומי→daily, שבועי→weekly, חודשי→monthly, שנתי→yearly
    - Implement `execute` dispatcher, `get_help`
    - _Requirements: 7.1, 8.1, 9.1_

  - [x] 3.2 Implement RecurringSkill._create with frequency parsing
    - Parse title + frequency from message text
    - Calculate `next_due_date` based on frequency and current date
    - Call `recurring.create_pattern`, return Result with entity_type="recurring_pattern", action="created"
    - _Requirements: 7.1, 7.2, 7.3, 7.5_

  - [x] 3.3 Implement RecurringSkill._list and _delete with confirmation
    - `_list`: call `recurring.list_patterns(is_active=True)`, format with `format_recurring_list`
    - `_delete`: resolve pattern, set `pending_confirmation`, on confirm call `recurring.deactivate_pattern`
    - _Requirements: 8.1, 8.2, 8.3, 9.1, 9.2, 9.3, 9.4, 9.5, 29.3_

  - [x] 3.4 Implement RecurringSkill.verify method
    - created→is_active=True, deleted→is_active=False
    - _Requirements: 7.4, 26.5, 26.6_

- [x] 4. Implement DocumentSkill — `fortress/src/skills/document_skill.py`
  - [x] 4.1 Create DocumentSkill class with BaseSkill interface
    - Implement `name="document"`, `description`, `commands` with list pattern only (save has no regex — triggered by media detection)
    - Implement `execute` dispatcher, `get_help`
    - _Requirements: 10.1, 11.1_

  - [x] 4.2 Implement DocumentSkill._save and _list
    - `_save`: call `documents.process_document(file_path, member.id, "whatsapp")`, return Result with entity_type="document", action="saved"
    - `_list`: query last 20 documents, format with `format_document_list`
    - _Requirements: 10.2, 10.3, 10.5, 11.1, 11.2, 11.3_

  - [x] 4.3 Implement DocumentSkill.verify method
    - saved→document exists in DB
    - _Requirements: 10.4, 26.7_

- [x] 5. Implement BugSkill — `fortress/src/skills/bug_skill.py`
  - [x] 5.1 Create BugSkill class with BaseSkill interface
    - Implement `name="bug"`, `description`, `commands` with 2 regex patterns (report, list)
    - Implement `execute` dispatcher, `get_help`
    - _Requirements: 13.1, 14.1_

  - [x] 5.2 Implement BugSkill._report and _list with permission checks
    - `_report`: check perm (tasks/write), create BugReport record, return Result with entity_type="bug_report", action="reported"
    - `_list`: check perm (tasks/read), query open BugReports, format with `format_bug_list`
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.6, 14.1, 14.2, 14.3, 14.4, 14.5_

  - [x] 5.3 Implement BugSkill.verify method
    - reported→bug exists with status "open"
    - _Requirements: 13.5, 26.8_

- [x] 6. Checkpoint — Verify core CRUD skills
  - Ensure all existing Sprint R1 tests pass (`test_base_skill.py`, `test_registry.py`, `test_command_parser.py`, `test_executor.py`, `test_system_skill.py`). Ask the user if questions arise.

- [x] 7. Implement ChatSkill — `fortress/src/skills/chat_skill.py`
  - [x] 7.1 Create ChatSkill class with BaseSkill interface
    - Implement `name="chat"`, `description`, `commands` with greeting regex pattern
    - Implement `execute` for greet action using `get_greeting(member.name, current_hour)`
    - Implement `verify` (always True), `get_help`
    - _Requirements: 15.1, 15.2, 15.3, 24.3_

  - [x] 7.2 Implement ChatSkill.respond async method
    - Load memories via MemorySkill recall
    - Construct prompt with personality + time context + memories + conversation state
    - Call LLM (Bedrock primary, OpenRouter fallback)
    - Return response string; return `error_fallback` template if both LLM calls fail
    - _Requirements: 16.1, 16.2, 16.3, 16.4_

- [x] 8. Implement MemorySkill — `fortress/src/skills/memory_skill.py`
  - [x] 8.1 Create MemorySkill class with BaseSkill interface
    - Implement `name="memory"`, `description`, `commands` with list pattern only (store/recall are programmatic)
    - Implement `execute` dispatcher, `get_help`
    - _Requirements: 17.1_

  - [x] 8.2 Implement MemorySkill._store, _recall, and _list
    - `_store(db, member, content, category, memory_type)`: check exclusion → validate category → call `save_memory` → return Result with entity_type="memory", action="stored"; return `memory_excluded` if excluded
    - `_recall(db, member)`: call `load_memories` → return memory list in Result.data
    - `_list`: call `load_memories`, format as numbered list with category + content, use `memory_list_header` and `memory_list_empty` templates
    - _Requirements: 17.1, 17.2, 17.3, 17.4, 18.1, 18.2, 18.3, 18.4, 19.1, 19.2, 19.3_

  - [x] 8.3 Implement MemorySkill.verify method
    - stored→memory exists in DB; recall/list→always True
    - _Requirements: 18.4_

- [x] 9. Implement MorningSkill — `fortress/src/skills/morning_skill.py`
  - [x] 9.1 Create MorningSkill class with BaseSkill interface
    - Implement `name="morning"`, `description`, `commands` with 2 regex patterns (briefing, summary)
    - Implement `execute` dispatcher, `get_help`
    - _Requirements: 20.1, 21.1_

  - [x] 9.2 Implement MorningSkill._briefing and _summary
    - `_briefing`: query counts (open tasks, active recurring, recent docs, open bugs), format with `morning_briefing` + section templates, hide bugs for non-parent roles
    - `_summary`: check perm (finance/read), generate summary report using personality templates, return `no_report_yet` if no data
    - _Requirements: 20.1, 20.2, 20.3, 20.4, 21.1, 21.2, 21.3, 21.4_

  - [x] 9.3 Implement MorningSkill.verify method
    - Always True (read-only operations)
    - _Requirements: 28.5_

- [x] 10. Register all skills in `fortress/src/skills/__init__.py`
  - Register TaskSkill, RecurringSkill, DocumentSkill (dual: "document" + "media"), BugSkill, ChatSkill, MemorySkill, MorningSkill
  - Ensure DocumentSkill instance is registered under both `"document"` and `"media"` keys
  - Verify SystemSkill registration is preserved
  - _Requirements: 22.1, 22.2, 22.3, 12.1, 12.2, 12.3_

- [x] 11. Update message handler LLM fallback — `fortress/src/services/message_handler.py`
  - Replace `workflow_engine.run_workflow` call with `ChatSkill.respond(db, member, message_text)` via `registry.get("chat")`
  - Change intent from `"llm_fallback"` to `"chat.respond"`
  - _Requirements: 23.1, 23.2, 23.3_

- [x] 12. Checkpoint — Verify integration
  - Ensure all existing Sprint R1 tests still pass after registration and message handler changes. Ask the user if questions arise.

- [x] 13. Write unit tests for all skills
  - [x] 13.1 Create `fortress/tests/test_task_skill.py`
    - Test create (happy path, permission denied, duplicate detection with confirmation)
    - Test list (happy path, permission denied, empty list, task_list_order stored in state)
    - Test delete (by index, missing task_list_order → need_list_first, out-of-range → task_not_found, confirmation flow)
    - Test delete_all (confirmation with count, permission denied)
    - Test complete (by index, by last_entity_id fallback, permission denied)
    - Test update (by index, change parsing, permission denied)
    - Test verify for each action type
    - _Requirements: 32.1_

  - [x] 13.2 Create `fortress/tests/test_recurring_skill.py`
    - Test create (Hebrew frequency parsing, next_due_date calculation)
    - Test list (active patterns, empty list)
    - Test delete (confirmation flow, deactivation)
    - Test verify for create and delete
    - _Requirements: 32.2_

  - [x] 13.3 Create `fortress/tests/test_document_skill.py`
    - Test save (process_document called, Result metadata)
    - Test list (formatted output, empty list)
    - Test verify for save
    - Test dual registration (registry.get("media") is registry.get("document"))
    - _Requirements: 32.3_

  - [x] 13.4 Create `fortress/tests/test_bug_skill.py`
    - Test report (happy path, permission denied, Result metadata)
    - Test list (open bugs, permission denied, empty list)
    - Test verify for report
    - _Requirements: 32.4_

  - [x] 13.5 Create `fortress/tests/test_chat_skill.py`
    - Test greet at different hours (morning, afternoon, evening, night)
    - Test greet includes member name
    - Test respond calls LLM with correct context (mock Bedrock/OpenRouter)
    - Test respond fallback when LLM fails
    - _Requirements: 32.5_

  - [x] 13.6 Create `fortress/tests/test_memory_skill.py`
    - Test store (valid content saved, excluded content rejected, invalid category mapped)
    - Test recall (returns memories in Result.data)
    - Test list (formatted output, empty list)
    - Test verify for store
    - _Requirements: 32.6_

  - [x] 13.7 Create `fortress/tests/test_morning_skill.py`
    - Test briefing (correct counts, section formatting, bugs hidden for non-parent)
    - Test summary (permission check, formatted report)
    - Test verify always True
    - _Requirements: 32.7_

- [x] 14. Final checkpoint — Run full test suite
  - Run all tests including Sprint R1 tests to ensure nothing is broken. Ensure all tests pass, ask the user if questions arise.
  - _Requirements: 32.8_

## Notes

- All code is Python, matching the existing codebase
- Tests are unit tests only (no property-based tests per sprint decision)
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- All Sprint R1 tests must continue to pass throughout implementation
- Work should be done on branch: `rebuild/skills-engine`
