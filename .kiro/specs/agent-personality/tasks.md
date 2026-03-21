# Implementation Plan: Agent Personality

## Overview

Centralise all user-facing Hebrew text into `fortress/src/prompts/personality.py`, wire it into system prompts and all services, update existing tests for compatibility, add a dedicated test file, and update the README roadmap.

## Tasks

- [x] 1. Create personality module
  - [x] 1.1 Create `fortress/src/prompts/personality.py` with PERSONALITY, GREETINGS, TEMPLATES constants and `get_greeting`, `format_task_created`, `format_task_list` functions
    - PERSONALITY: Hebrew string defining agent character (warm, family-oriented, WhatsApp-concise, emoji-light)
    - GREETINGS: dict with keys `morning` (5–11), `afternoon` (12–16), `evening` (17–20), `night` (21–4), each a Hebrew greeting with `{name}` placeholder
    - TEMPLATES: dict with 10 keys — `task_created`, `task_completed`, `task_list_empty`, `task_list_header`, `document_saved`, `permission_denied`, `unknown_member`, `inactive_member`, `error_fallback`, `cant_understand`
    - `get_greeting(name, hour)`: maps hour (0–23) to correct GREETINGS key, formats with name, returns greeting string
    - `format_task_created(title, due_date)`: returns Hebrew confirmation; includes due_date when not None, omits date section when None
    - `format_task_list(tasks)`: returns TEMPLATES["task_list_empty"] for empty list; otherwise numbered list with priority emojis (🔴 urgent, 🟡 high, 🟢 normal, ⚪ low), title, optional due date
    - Use `hour % 24` for out-of-range hours; default missing priority to "normal"
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

  - [x] 1.2 Update `fortress/src/prompts/__init__.py` to re-export personality module public API
    - Re-export: `PERSONALITY`, `GREETINGS`, `TEMPLATES`, `get_greeting`, `format_task_created`, `format_task_list`
    - _Requirements: 1.1, 1.2, 1.3_

- [x] 2. Update system prompts with personality prefix
  - [x] 2.1 Modify `fortress/src/prompts/system_prompts.py` to import PERSONALITY and prepend it to FORTRESS_BASE, UNIFIED_CLASSIFY_AND_RESPOND, and TASK_RESPONDER
    - Import `PERSONALITY` from `personality` module
    - Prepend `PERSONALITY + "\n\n"` to `FORTRESS_BASE`, `UNIFIED_CLASSIFY_AND_RESPOND`, `TASK_RESPONDER`
    - Leave `INTENT_CLASSIFIER`, `TASK_EXTRACTOR`, `TASK_EXTRACTOR_BEDROCK`, `MEMORY_EXTRACTOR` unchanged (machine-facing)
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [x] 3. Checkpoint — Verify existing tests still pass
  - Ensure all 175 existing tests pass after system_prompts changes, ask the user if questions arise.

- [x] 4. Update workflow engine to use personality module
  - [x] 4.1 Modify `fortress/src/services/workflow_engine.py` to import and use personality functions/templates
    - Import `get_greeting`, `format_task_created`, `format_task_list`, `TEMPLATES as PERSONALITY_TEMPLATES` from personality module
    - Replace `_handle_greeting` hardcoded `f"שלום, {member.name}! 👋"` with `get_greeting(member.name, current_hour)` using `datetime.now().hour`
    - Replace `_handle_create_task` confirmation with `format_task_created(title, due_date)` — still use dispatcher for task extraction
    - Replace `_handle_list_tasks` formatting with `format_task_list(tasks)` — no dispatcher call needed for formatting
    - Replace `_handle_unknown` hardcoded Hebrew help text with `PERSONALITY_TEMPLATES["cant_understand"]`
    - Replace `permission_node` denial string with `PERSONALITY_TEMPLATES["permission_denied"]`
    - Replace `run_workflow` except block `HEBREW_FALLBACK` with `PERSONALITY_TEMPLATES["error_fallback"]`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

- [x] 5. Update unified handler to use personality fallback
  - [x] 5.1 Modify `fortress/src/services/unified_handler.py` to import TEMPLATES and alias error_fallback
    - Import `TEMPLATES` from personality module
    - Replace hardcoded `HEBREW_FALLBACK_MSG` value with `TEMPLATES["error_fallback"]`
    - Keep `HEBREW_FALLBACK_MSG` as module-level alias for backward compatibility (existing tests reference it)
    - _Requirements: 4.1, 4.2_

- [x] 6. Update message handler to use personality templates
  - [x] 6.1 Modify `fortress/src/services/message_handler.py` to import TEMPLATES and replace hardcoded Hebrew strings
    - Import `TEMPLATES` from personality module
    - Replace `"מספר לא מזוהה. פנה למנהל המשפחה."` with `TEMPLATES["unknown_member"]`
    - Replace `"החשבון שלך לא פעיל."` with `TEMPLATES["inactive_member"]`
    - _Requirements: 5.1, 5.2, 5.3_

- [x] 7. Checkpoint — Verify existing tests still pass
  - Ensure all 175 existing tests pass after service changes, ask the user if questions arise.

- [x] 8. Create personality test suite and update existing tests
  - [x] 8.1 Update `fortress/tests/test_message_handler.py` assertions to use personality TEMPLATES
    - Replace `"מספר לא מזוהה"` substring check with assertion against `TEMPLATES["unknown_member"]`
    - Replace `"לא פעיל"` substring check with assertion against `TEMPLATES["inactive_member"]`
    - _Requirements: 5.1, 5.2, 6.10_

  - [x] 8.2 Update `fortress/tests/test_workflow_engine.py` if any assertions reference hardcoded Hebrew strings
    - Check and update any assertions that match on old hardcoded Hebrew responses
    - _Requirements: 3.7, 6.10_

  - [x] 8.3 Update `fortress/tests/test_unified_handler.py` to verify HEBREW_FALLBACK_MSG alias still works
    - Ensure existing import of `HEBREW_FALLBACK_MSG` still resolves correctly
    - _Requirements: 4.2, 6.10_

  - [x]* 8.4 Create `fortress/tests/test_personality.py` with unit tests for personality module
    - Test PERSONALITY is a non-empty string
    - Test GREETINGS has keys: morning, afternoon, evening, night
    - Test TEMPLATES has all 10 required keys and all values are non-empty strings
    - Test `get_greeting` returns string containing name for hours 0, 6, 12, 18
    - Test `get_greeting` returns different strings for morning (hour=8) vs evening (hour=20)
    - Test boundary hours (5, 11, 12, 16, 17, 20, 21, 4) map to correct time-of-day
    - Test `format_task_created` includes title in output
    - Test `format_task_created` with non-null due_date includes date in output
    - Test `format_task_created` with null due_date omits date placeholder
    - Test `format_task_list([])` returns TEMPLATES["task_list_empty"]
    - Test `format_task_list` with multiple tasks includes each title
    - Test `format_task_list` priority emojis: urgent→🔴, high→🟡, normal→🟢, low→⚪
    - Test FORTRESS_BASE starts with PERSONALITY
    - Test UNIFIED_CLASSIFY_AND_RESPOND starts with PERSONALITY
    - Test TASK_RESPONDER starts with PERSONALITY
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.11_

- [x] 9. Update README roadmap
  - [x] 9.1 Update `README.md` with STABLE-2 — Agent Personality row in roadmap table
    - Add row: `| STABLE-2 — Agent Personality | ✅ Complete | Centralised Hebrew personality, templates, greeting system | 190+ |`
    - Update status line and test count references
    - _Requirements: 7.1_

- [x] 10. Final checkpoint — Run full test suite
  - Ensure all tests pass (175 existing + new personality tests), ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- No property-based tests — unit tests only per user request
- All 175 existing tests must continue to pass throughout implementation
- The personality module is pure functions and constants — no I/O, no async, no database
- `HEBREW_FALLBACK_MSG` kept as alias in unified_handler.py for backward compatibility
- Each task references specific requirements for traceability
- Checkpoints at tasks 3, 7, and 10 ensure incremental validation
