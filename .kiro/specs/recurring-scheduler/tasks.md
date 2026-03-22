# Implementation Plan: Recurring Scheduler

## Overview

Add an automated daily scheduler to Fortress that generates tasks from due recurring patterns, sends WhatsApp notifications, and provides WhatsApp-based management commands (create, list, delete) for recurring patterns. The scheduler runs daily at 07:00 via APScheduler embedded in the FastAPI process. All changes are in Python, building on the existing `recurring.py` service and LangGraph workflow engine.

## Tasks

- [x] 1. Add personality templates and `format_recurring_list` function
  - [x] 1.1 Add 8 recurring templates to `TEMPLATES` dict in `src/prompts/personality.py`
    - Add keys: `reminder_new_task`, `scheduler_summary`, `recurring_list_header`, `recurring_list_empty`, `recurring_list_item`, `recurring_created`, `recurring_deleted`, `recurring_not_found`
    - Use exact Hebrew strings from the design document
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8_
  - [x] 1.2 Add `format_recurring_list(patterns: list) -> str` function to `src/prompts/personality.py`
    - Follow the same pattern as `format_task_list()` and `format_document_list()`
    - Use `recurring_list_header`, `recurring_list_empty`, and `recurring_list_item` templates
    - Output must contain each pattern's title, frequency, and next_due_date
    - _Requirements: 4.9_
  - [x] 1.3 Update `REQUIRED_TEMPLATE_KEYS` set in `tests/test_personality.py` to include the 8 new keys
    - Ensures the existing `test_templates_has_all_required_keys` test passes with the new templates
    - _Requirements: 10.3_
  - [ ]* 1.4 Add unit tests for recurring templates and `format_recurring_list` in `tests/test_personality.py`
    - `test_recurring_templates_exist` — all 8 recurring template keys present and non-empty
    - `test_format_recurring_list_with_patterns` — output contains pattern title, frequency, next_due_date
    - `test_format_recurring_list_empty` — returns `recurring_list_empty` template
    - _Requirements: 10.3_

- [x] 2. Add `SCHEDULER_HOUR` config and `apscheduler` dependency
  - [x] 2.1 Add `SCHEDULER_HOUR` to `src/config.py`
    - `SCHEDULER_HOUR: int = int(os.getenv("SCHEDULER_HOUR", "7"))`
    - _Requirements: 8.1_
  - [x] 2.2 Add `apscheduler==3.10.4` to `requirements.txt`
    - _Requirements: 8.4_

- [x] 3. Implement scheduler service (`src/services/scheduler.py`)
  - [x] 3.1 Create `src/services/scheduler.py` with `SchedulerResult` dataclass and module-level state
    - `SchedulerResult` with `tasks_created`, `notifications_sent`, `task_details` fields
    - Module-level `_last_run` and `_last_run_tasks` state variables
    - `get_status()` function returning dict with `last_run` and `tasks_created_last_run`
    - _Requirements: 2.2, 2.3_
  - [x] 3.2 Implement `run_daily_schedule(db: Session) -> SchedulerResult`
    - Call `get_due_patterns(db)` then `generate_tasks_from_due_patterns(db)`
    - For each created task, resolve assigned member's phone via DB query on `FamilyMember`
    - Send per-task WhatsApp notification using `reminder_new_task` template via `send_text_message`
    - Send admin summary using `scheduler_summary` template to `ADMIN_PHONE`
    - Catch per-notification errors without crashing; log every step
    - Update `_last_run` and `_last_run_tasks` after completion
    - Return `SchedulerResult` with accurate counts
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 3.1, 3.2, 3.3, 3.4, 3.5_
  - [ ]* 3.3 Create `tests/test_scheduler.py` with unit tests
    - `test_run_no_due_patterns_returns_empty` — empty result when no patterns due
    - `test_run_with_due_patterns_creates_tasks` — tasks created and result populated
    - `test_notifications_sent_for_created_tasks` — `send_text_message` called per task
    - `test_notification_failure_does_not_crash` — scheduler continues on send failure
    - `test_admin_summary_sent_after_run` — summary sent to `ADMIN_PHONE`
    - `test_status_updated_after_run` — `get_status()` reflects last run
    - `test_status_before_first_run` — `get_status()` returns null/0 initially
    - `test_single_pattern_error_continues_others` — resilience when one pattern fails
    - All tests use `MagicMock`/`AsyncMock` for DB, `whatsapp_client`, and `recurring` module
    - _Requirements: 10.1_

- [x] 4. Checkpoint — Verify scheduler service tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement scheduler router and APScheduler integration
  - [x] 5.1 Create `src/routers/scheduler.py` with POST `/scheduler/run` and GET `/scheduler/status`
    - POST `/run` invokes `run_daily_schedule(db)` and returns `tasks_created` + `notifications_sent`
    - GET `/status` returns `get_status()` dict
    - No authentication required
    - _Requirements: 2.1, 2.2, 2.3_
  - [x] 5.2 Modify `src/main.py` to integrate APScheduler and register scheduler router
    - Import and initialize `AsyncIOScheduler` with `CronTrigger(hour=SCHEDULER_HOUR, minute=0)`
    - Add `_scheduled_run` helper that creates a DB session and calls `run_daily_schedule`
    - Start scheduler in lifespan startup, shut down in lifespan cleanup
    - Register `scheduler.router` via `app.include_router()`
    - _Requirements: 2.4, 8.1, 8.2, 8.3_

- [x] 6. Add recurring intents to intent detector and routing policy
  - [x] 6.1 Add `list_recurring`, `create_recurring`, `delete_recurring` to `INTENTS` dict in `src/services/intent_detector.py`
    - All three with `model_tier: "local"`
    - _Requirements: 5.4_
  - [x] 6.2 Add keyword matching for recurring intents in `_match_keywords()` in `src/services/intent_detector.py`
    - `"תזכורות"`, `"חוזרות"`, `"recurring"` → `list_recurring`
    - `"תזכורת חדשה:"`, `"recurring:"` → `create_recurring` (prefix match)
    - `"מחק תזכורת"`, `"בטל תזכורת"` → `delete_recurring`
    - Place recurring keyword checks BEFORE existing delete_task checks to avoid conflicts
    - _Requirements: 5.1, 5.2, 5.3_
  - [x] 6.3 Add 3 recurring intents to `SENSITIVITY_MAP` in `src/services/routing_policy.py` mapped to `"medium"`
    - _Requirements: 5.5_
  - [ ]* 6.4 Add unit tests for recurring intent detection in `tests/test_recurring_management.py`
    - `test_list_recurring_intent_hebrew_tizkorot` — `"תזכורות"` → `list_recurring`
    - `test_list_recurring_intent_hebrew_chozrot` — `"חוזרות"` → `list_recurring`
    - `test_list_recurring_intent_english` — `"recurring"` → `list_recurring`
    - `test_create_recurring_intent_hebrew` — `"תזכורת חדשה: ..."` → `create_recurring`
    - `test_create_recurring_intent_english` — `"recurring: ..."` → `create_recurring`
    - `test_delete_recurring_intent_machak` — `"מחק תזכורת"` → `delete_recurring`
    - `test_delete_recurring_intent_batel` — `"בטל תזכורת"` → `delete_recurring`
    - _Requirements: 10.2_
  - [ ]* 6.5 Extend `tests/test_routing_policy.py` with `test_recurring_intents_medium_sensitivity`
    - Verify all 3 recurring intents map to `"medium"` sensitivity
    - _Requirements: 5.5_
  - [ ]* 6.6 Extend `tests/test_intent_detector.py` with `test_intents_contains_recurring`
    - Verify INTENTS dict includes the 3 new intents
    - _Requirements: 5.4_

- [x] 7. Add workflow engine handlers for recurring management
  - [x] 7.1 Add `list_recurring`, `create_recurring`, `delete_recurring` to `_PERMISSION_MAP` in `src/services/workflow_engine.py`
    - `"list_recurring": ("tasks", "read")`
    - `"create_recurring": ("tasks", "write")`
    - `"delete_recurring": ("tasks", "write")`
    - _Requirements: 6.5_
  - [x] 7.2 Implement `_handle_list_recurring` handler in `src/services/workflow_engine.py`
    - Query active patterns for the current member using `recurring.list_patterns()` filtered by `assigned_to`
    - Format with `format_recurring_list()`
    - _Requirements: 6.1_
  - [x] 7.3 Implement `_handle_create_recurring` handler in `src/services/workflow_engine.py`
    - Parse title from message text after prefix (`"תזכורת חדשה:"` / `"recurring:"`)
    - Parse frequency from Hebrew keywords: `"יומי"` → `"daily"`, `"שבועי"` → `"weekly"`, `"חודשי"` / `"כל חודש"` → `"monthly"`, `"שנתי"` → `"yearly"`, default `"monthly"`
    - Calculate `next_due_date` as today + one frequency period
    - Call `recurring.create_pattern()` with parsed fields and `assigned_to=member.id`
    - Return `recurring_created` template
    - _Requirements: 6.2_
  - [x] 7.4 Implement `_handle_delete_recurring` handler in `src/services/workflow_engine.py`
    - Identify pattern by number (from list) or title match
    - Call `recurring.deactivate_pattern()` on match
    - Return `recurring_deleted` or `recurring_not_found` template
    - _Requirements: 6.3, 6.4_
  - [x] 7.5 Register 3 handlers in `_ACTION_HANDLERS` dict in `src/services/workflow_engine.py`
    - _Requirements: 6.6_
  - [ ]* 7.6 Add workflow handler tests in `tests/test_recurring_management.py`
    - `test_list_handler_returns_formatted_patterns` — handler returns formatted list
    - `test_list_handler_empty_patterns` — handler returns empty template
    - `test_create_handler_creates_pattern` — handler calls `create_pattern` with parsed fields
    - `test_delete_handler_deactivates_pattern` — handler calls `deactivate_pattern`
    - `test_delete_handler_not_found` — handler returns `recurring_not_found`
    - _Requirements: 10.2_

- [x] 8. Update unified handler and system prompt for recurring intents
  - [x] 8.1 Update `UNIFIED_CLASSIFY_AND_RESPOND` in `src/prompts/system_prompts.py`
    - Add `list_recurring`, `create_recurring`, `delete_recurring` to the intent list
    - Add `recurring_data` JSON format description for `create_recurring` intent
    - _Requirements: 7.3_
  - [x] 8.2 Update `handle_with_llm` in `src/services/unified_handler.py` to extract `recurring_data` for `create_recurring` intent
    - When intent is `create_recurring`, extract `recurring_data` from JSON response
    - _Requirements: 7.1, 7.2_

- [x] 9. Checkpoint — Verify all recurring management tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Create shell script and update README
  - [x] 10.1 Create `scripts/run_scheduler.sh`
    - curl POST to `http://localhost:8000/scheduler/run`
    - Print JSON response
    - Make executable
    - _Requirements: 9.1, 9.2, 9.3_
  - [x] 10.2 Update `README.md` roadmap
    - Add `STABLE-5 — Recurring Scheduler` row with `✅ Complete` status and updated test count
    - Update "Current Version" text to `Phase STABLE-5`
    - _Requirements: 11.1, 11.2_

- [x] 11. Final checkpoint — Run full test suite and verify 254+ tests pass
  - Run `pytest` from the `fortress/` directory and confirm all 254 existing tests plus new tests pass
  - Ensure no regressions in any existing test file
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- All tests use `MagicMock`/`AsyncMock` — no real DB, HTTP, or WhatsApp calls
- The implementation language is Python (FastAPI + SQLAlchemy), matching the existing codebase
