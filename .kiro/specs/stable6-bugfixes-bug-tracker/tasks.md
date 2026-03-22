# Tasks — STABLE-6 Bugfixes & Bug Tracker

## Part A: Bugfixes & Resilience

- [x] 1. Memory category validation in `save_memory()`
  - [x] 1.1 Add `VALID_CATEGORIES` set and `CATEGORY_MAP` dict to `fortress/src/services/memory_service.py`
  - [x] 1.2 Add validation logic at the top of `save_memory()` — check category against `VALID_CATEGORIES`, apply `CATEGORY_MAP`, default to `context` with warning log
  - [x] 1.3 Write unit tests in `fortress/tests/test_memory_service.py`: test `VALID_CATEGORIES` constant, `CATEGORY_MAP` constant, valid category passthrough, mapped category (`task` → `context`), invalid category defaults to `context` with warning log
- [x] 2. Update MEMORY_EXTRACTOR prompt
  - [x] 2.1 Update `MEMORY_EXTRACTOR` in `fortress/src/prompts/system_prompts.py` — add explicit Hebrew instruction listing the five valid categories and `context` as default
  - [x] 2.2 Write unit tests in `fortress/tests/test_system_prompts.py`: verify prompt contains all five category names, Hebrew instruction text, and `context` as default
- [x] 3. Session rollback in `memory_save_node` and `conversation_save_node`
  - [x] 3.1 Add `state["db"].rollback()` in the except block of `memory_save_node` in `fortress/src/services/workflow_engine.py` (with nested try/except for rollback failure)
  - [x] 3.2 Add `state["db"].rollback()` in the except block of `conversation_save_node` in `fortress/src/services/workflow_engine.py` (with nested try/except for rollback failure)
  - [x] 3.3 Write unit tests in `fortress/tests/test_workflow_engine.py`: verify `db.rollback()` is called on exception in both nodes, verify `PendingRollbackError` recovery, verify return value is empty dict without `response` key
- [x] 4. Photo upload diagnostic logging
  - [x] 4.1 Add `logger.info(...)` at the top of `_handle_upload_document` in `fortress/src/services/workflow_engine.py` logging `has_media`, `media_file_path`, and `member.name`
  - [x] 4.2 Add media type/MIME/filename logging in `fortress/src/routers/whatsapp.py` after `has_media` check

## Part B: Bug Tracker Feature

- [x] 5. Database migration for `bug_reports` table
  - [x] 5.1 Create `fortress/migrations/006_bug_reports.sql` with CREATE TABLE, CHECK constraints, and indexes
- [x] 6. BugReport ORM model
  - [x] 6.1 Add `BugReport` class to `fortress/src/models/schema.py` using `mapped_column` style
  - [x] 6.2 Add `bug_reports` relationship to `FamilyMember` model in `fortress/src/models/schema.py`
- [x] 7. Intent detection for bug tracker
  - [x] 7.1 Add `report_bug` and `list_bugs` to `INTENTS` dict in `fortress/src/services/intent_detector.py`
  - [x] 7.2 Add keyword matching for `report_bug` (באג:, bug:, באג, bug) and `list_bugs` (באגים, bugs, רשימת באגים) in `_match_keywords()` in `fortress/src/services/intent_detector.py`
  - [x] 7.3 Write unit tests in `fortress/tests/test_intent_detector.py`: test all keyword variants, INTENTS dict includes new intents, VALID_INTENTS includes new intents
- [x] 8. Routing policy for bug tracker
  - [x] 8.1 Add `report_bug: "medium"` and `list_bugs: "medium"` to `SENSITIVITY_MAP` in `fortress/src/services/routing_policy.py`
  - [x] 8.2 Write unit tests in `fortress/tests/test_routing_policy.py`: verify sensitivity mapping for both intents
- [x] 9. Bug tracker personality templates
  - [x] 9.1 Add `bug_reported`, `bug_list_header`, `bug_list_empty`, `bug_list_item` templates to `TEMPLATES` dict in `fortress/src/prompts/personality.py`
  - [x] 9.2 Add `format_bug_list()` function to `fortress/src/prompts/personality.py` following the `format_task_list()` pattern
  - [x] 9.3 Write unit tests in `fortress/tests/test_personality.py`: verify new template keys exist, `format_bug_list()` with empty list, `format_bug_list()` with mock BugReport objects, template placeholders
- [x] 10. Workflow handlers for `report_bug` and `list_bugs`
  - [x] 10.1 Add `_handle_report_bug` and `_handle_list_bugs` async handler functions to `fortress/src/services/workflow_engine.py`
  - [x] 10.2 Add `report_bug` and `list_bugs` entries to `_PERMISSION_MAP` and `_ACTION_HANDLERS` in `fortress/src/services/workflow_engine.py`
  - [x] 10.3 Add `BugReport` import and `format_bug_list` import to `fortress/src/services/workflow_engine.py`
  - [x] 10.4 Write unit tests in `fortress/tests/test_workflow_engine.py`: test `_handle_report_bug` creates BugReport and returns template, test `_handle_list_bugs` queries and formats, test `_PERMISSION_MAP` and `_ACTION_HANDLERS` entries
- [x] 11. Unified handler integration
  - [x] 11.1 Update `UNIFIED_CLASSIFY_AND_RESPOND` prompt in `fortress/src/prompts/system_prompts.py` to include `report_bug` and `list_bugs` with Hebrew descriptions
  - [x] 11.2 Write unit tests in `fortress/tests/test_unified_handler.py`: verify `report_bug` and `list_bugs` are valid intents handled by unified handler
- [ ] 12. Update existing test assertions for new template keys
  - [x] 12.1 Update `REQUIRED_TEMPLATE_KEYS` set in `fortress/tests/test_personality.py` to include `bug_reported`, `bug_list_header`, `bug_list_empty`, `bug_list_item`
  - [x] 12.2 Update `test_intents_contains_all_required` in `fortress/tests/test_intent_detector.py` to include `report_bug` and `list_bugs`
  - [x] 12.3 Run full test suite to verify all 262+ tests pass
