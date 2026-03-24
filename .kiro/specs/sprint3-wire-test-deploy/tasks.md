# Implementation Plan: Sprint R3 — Wire + Test + Deploy

## Overview

Create 7 end-to-end test files validating the full Skills Engine pipeline through `handle_incoming_message`, clean up unused imports, run all tests, merge `rebuild/skills-engine` to `main`, and update documentation. All tests use pytest with mocked DB/services — no real database or LLM needed. Branch: `rebuild/skills-engine`.

## Tasks

- [x] 1. Create test_e2e_skills.py — End-to-end skill integration tests
  - [x] 1.1 Add E2E helper fixtures to conftest.py
    - Add `_make_member(role, name, phone)` role-aware factory (parent/child/grandparent)
    - Add `mock_task(**overrides)`, `mock_recurring(**overrides)`, `mock_bug(**overrides)`, `mock_document(**overrides)` factories
    - Add `_mock_permission_check(role)` returning a function implementing the permission matrix
    - _Requirements: 1.1–1.13, 2.1–2.12_

  - [x] 1.2 Implement test_e2e_skills.py — 13 tests covering every skill through handle_incoming_message
    - `test_task_create_e2e` — "משימה חדשה: לקנות חלב" → routes to TaskSkill.create, returns "יצרתי משימה"
    - `test_task_list_e2e` — "משימות" → returns formatted task list, stores task_list_order in state
    - `test_task_delete_confirm_e2e` — "מחק משימה 1" then "כן" → archives task, returns "נמחקה"
    - `test_task_delete_deny_e2e` — "מחק משימה 1" then "לא" → task unarchived, state cleared
    - `test_document_save_e2e` — media message → routes to DocumentSkill.save, returns "שמרתי"
    - `test_greeting_e2e` — "שלום" → returns greeting with member name, no LLM call
    - `test_bug_report_e2e` — "באג: תמונה לא עובדת" → persists BugReport, matches bug_reported template
    - `test_recurring_create_e2e` — "תזכורת חדשה: ארנונה, חודשי" → persists RecurringPattern, matches recurring_created template
    - `test_help_e2e` — "עזרה" → returns skill list in Hebrew
    - `test_morning_briefing_e2e` — "בוקר" → returns morning briefing with task/bug counts
    - `test_llm_fallback_e2e` — unrecognized message → delegates to ChatSkill.respond, saves with intent "chat.respond"
    - `test_unknown_phone_e2e` — unknown phone → returns unknown_member template, saves Conversation with None member_id
    - `test_inactive_member_e2e` — inactive member → returns inactive_member template
    - _Requirements: 1.1–1.13_

- [x] 2. Create test_e2e_permissions.py — Permission enforcement tests
  - [x] 2.1 Implement test_e2e_permissions.py — 12 tests covering role-based access control
    - `test_parent_task_create_allowed` — parent creates task → success response
    - `test_child_task_create_denied` — child creates task → permission_denied with 🔒
    - `test_parent_task_list_allowed` — parent lists tasks → task list returned
    - `test_child_task_list_allowed` — child lists tasks → task list returned (read access)
    - `test_parent_task_delete_allowed` — parent deletes task → confirmation flow proceeds
    - `test_child_task_delete_denied` — child deletes task → permission_denied with 🔒
    - `test_parent_bug_report_allowed` — parent reports bug → BugReport persisted, success
    - `test_child_bug_report_denied` — child reports bug → permission_denied with 🔒
    - `test_parent_summary_allowed` — parent requests summary → summary returned
    - `test_child_summary_denied` — child requests summary → permission_denied with 🔒
    - `test_grandparent_task_list_allowed` — grandparent lists tasks → task list returned (read access)
    - `test_grandparent_task_create_denied` — grandparent creates task → permission_denied with 🔒
    - _Requirements: 2.1–2.12_

- [x] 3. Create test_e2e_confirmations.py — Confirmation flow tests
  - [x] 3.1 Implement test_e2e_confirmations.py — 8 tests covering confirm/deny/ignore paths
    - `test_task_delete_confirm` — delete initiated + "כן" → task archived, deletion confirmation
    - `test_task_delete_deny` — delete initiated + "לא" → task unarchived, state cleared
    - `test_task_delete_ignore` — delete initiated + unrelated message → state cleared, new message processed
    - `test_delete_all_confirm` — delete-all initiated + "כן" → all open tasks archived
    - `test_delete_all_deny` — delete-all initiated + "לא" → all tasks unarchived
    - `test_recurring_delete_confirm` — recurring delete initiated + "כן" → pattern deactivated
    - `test_duplicate_task_confirm` — duplicate detected + "כן" → task created regardless
    - `test_duplicate_task_deny` — duplicate detected + "לא" → duplicate uncreated
    - _Requirements: 3.1–3.8_

- [x] 4. Create test_e2e_state.py — ConversationState consistency tests
  - [x] 4.1 Implement test_e2e_state.py — 7 tests covering state tracking across operations
    - `test_state_after_task_create` — task created → state has entity_type "task", correct entity_id, action "created"
    - `test_state_after_task_list` — tasks listed → state context has task_list_order with correct IDs
    - `test_delete_resolves_index_2` — "מחק 2" after listing → resolves correct task from task_list_order[1]
    - `test_complete_resolves_index_1` — "סיים 1" after listing → resolves correct task from task_list_order[0]
    - `test_cancel_clears_state` — "עזוב" → all state fields reset to defaults
    - `test_confirm_no_pending` — "כן" with no pending confirmation → returns "אין פעולה ממתינה"
    - `test_sequential_create_list_delete_list` — create → list → delete 1 → list → correct indices after deletion
    - _Requirements: 4.1–4.7_

- [x] 5. Checkpoint — Ensure all new E2E tests pass alongside R1 + R2 tests
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Create test_e2e_conversations.py — Conversation persistence tests
  - [x] 6.1 Implement test_e2e_conversations.py — 6 tests covering conversation record saving
    - `test_skill_action_saves_conversation` — any skill action → Conversation record saved to DB
    - `test_conversation_intent_format` — intent field matches "{skill_name}.{action_name}" format
    - `test_conversation_message_in` — message_in contains original message text
    - `test_conversation_message_out` — message_out contains response text
    - `test_unknown_phone_conversation` — unknown phone → Conversation saved with None family_member_id
    - `test_llm_fallback_conversation_intent` — LLM fallback → Conversation saved with intent "chat.respond"
    - _Requirements: 5.1–5.6_

- [x] 7. Create test_e2e_regression.py — Regression safety tests
  - [x] 7.1 Implement test_e2e_regression.py — 9 tests covering edge cases and Hebrew keyword boundaries
    - `test_cancel_keywords` — each of (לא, עזוב, תעזוב, בטל, תבטל, ביטול) → CommandParser returns cancel Command
    - `test_confirm_keywords` — each of (כן, אישור, אשר, בטח, אוקיי, אוקי) → CommandParser returns confirm Command
    - `test_singular_mishima_routes_to_list` — "משימה" → routes to task list, not delete
    - `test_media_with_text_prioritizes_media` — media message with text → media handling takes priority
    - `test_empty_message_llm_fallback` — empty message → delegates to ChatSkill LLM fallback
    - `test_long_response_truncated` — response >3500 chars → truncated with "... (הודעה קוצרה)"
    - `test_mixed_hebrew_english` — mixed Hebrew/English text → pattern matching attempted normally
    - `test_emoji_only_llm_fallback` — emoji-only message → delegates to ChatSkill LLM fallback
    - `test_numbers_only_llm_fallback` — numbers-only message → delegates to ChatSkill LLM fallback
    - _Requirements: 6.1–6.9_

- [x] 8. Create test_e2e_personality.py — Personality template consistency tests
  - [x] 8.1 Implement test_e2e_personality.py — 7 tests covering Hebrew response consistency
    - `test_error_responses_use_templates` — all skill error responses use TEMPLATES values, not hardcoded strings
    - `test_permission_denied_has_lock_emoji` — permission denied → response contains 🔒
    - `test_verification_failed_uses_template` — verification failure → matches verification_failed template
    - `test_greeting_includes_name` — greeting → response includes member name
    - `test_greeting_time_of_day` — greetings at different hours → correct time-of-day template (morning/afternoon/evening/night)
    - `test_task_list_priority_emojis` — task list → uses 🔴 urgent, 🟡 high, 🟢 normal, ⚪ low
    - `test_no_english_error_messages` — all template values contain Hebrew text, no English error messages
    - _Requirements: 7.1–7.7_

- [x] 9. Clean up unused imports from old pipeline
  - Scan `message_handler.py`, `src/skills/`, and `src/engine/` for imports of: workflow_engine, unified_handler, model_router, model_dispatch, intent_detector, routing_policy
  - Remove any found (current code is expected to be clean — verify and fix if needed)
  - Add a regression test in `test_e2e_regression.py` that reads source files and asserts no old pipeline imports exist
  - Verify old pipeline source files remain on disk (no deletion)
  - _Requirements: 8.1–8.8_

- [x] 10. Checkpoint — Run ALL tests (R1 + R2 + R3), everything must pass
  - Run `cd fortress && python -m pytest tests/ -v --tb=short`
  - All existing R1 + R2 tests plus ~62 new R3 tests must pass
  - Ensure all tests pass, ask the user if questions arise.

- [-] 11. Merge rebuild/skills-engine to main and push
  - `git checkout main`
  - `git merge rebuild/skills-engine` (standard merge, not squash)
  - If conflicts: keep rebuild/skills-engine version
  - Run full test suite on main: `cd fortress && python -m pytest tests/ -v --tb=short`
  - `git push origin main`
  - _Requirements: 9.1–9.3_

- [ ] 12. Update README.md roadmap
  - Add row for "R2 — Core Skills Migration" with "✅ Complete"
  - Add row for "R3 — Wire + Test + Deploy" with "✅ Complete"
  - Update "Current Version" line to "Phase R3 — Skills Engine"
  - Update test count in status section to reflect final count
  - _Requirements: 10.1–10.4_

- [ ] 13. Update docs/setup.md with Skills Engine documentation
  - Add "Skills Engine Architecture" section describing CommandParser → Executor → Skill pipeline
  - Add "Available Skills" table listing all 8 skills (system, task, recurring, document, bug, chat, memory, morning) with one-line Hebrew descriptions
  - Add "How to Add a New Skill" section with step-by-step instructions
  - _Requirements: 11.1–11.3_

- [ ] 14. Final checkpoint — Ensure all tests pass on main
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- All tests use pytest with `@pytest.mark.asyncio` for async `handle_incoming_message`
- Mock strategy: patch DB session, auth, services — no real PostgreSQL or LLM needed
- No property-based tests — unit tests only per project decision
- Each test file follows the E2E pattern from the design document
- Checkpoints ensure incremental validation before merge
- Old pipeline files remain on disk for Sprint R4 removal
