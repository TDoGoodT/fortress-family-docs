# Implementation Plan: Core Flows Hardening

## Overview

Incremental implementation of six production gaps: delete_task flow, duplicate prevention, anti-hallucination prompts, corrupt data cleanup, task owner assignment, and Hebrew-only prompt cleanup. All deletions use soft-delete (archive). All 201 existing tests must continue to pass.

## Tasks

- [x] 1. Update intent_detector.py — add delete_task keywords
  - [x] 1.1 Add `delete_task` to INTENTS dict and VALID_INTENTS
    - Add `"delete_task": {"model_tier": "local"}` to `INTENTS` dict in `fortress/src/services/intent_detector.py`
    - `VALID_INTENTS` is derived from `INTENTS.keys()` so it updates automatically
    - _Requirements: 1.6_
  - [x] 1.2 Add delete keyword matching in `_match_keywords()`
    - Add a new block before the `return None` in `_match_keywords()`:
      - `"מחק משימה"` — substring match (`in stripped`)
      - `"מחק"` — standalone match (`stripped == "מחק"`)
      - `"הסר משימה"` — substring match
      - `"בטל משימה"` — substring match
      - `"delete task"` — case-insensitive substring match (`in lower`)
    - All return `"delete_task"`
    - Important: check `"מחק משימה"` before standalone `"מחק"` to avoid false positives
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x] 2. Update routing_policy.py — add delete_task sensitivity
  - Add `"delete_task": "medium"` to `SENSITIVITY_MAP` in `fortress/src/services/routing_policy.py`
  - _Requirements: 2.1_

- [x] 3. Update personality.py — add delete and duplicate templates
  - Add four new entries to the `TEMPLATES` dict in `fortress/src/prompts/personality.py`:
    - `"task_deleted": "משימה נמחקה: {title} ✅"`
    - `"task_delete_which": "איזו משימה למחוק? 🤔\n{task_list}"`
    - `"task_not_found": "לא מצאתי את המשימה הזו 🤷"`
    - `"task_duplicate": "המשימה הזו כבר קיימת ✅"`
  - _Requirements: 5.1, 5.2, 5.3, 7.3_

- [x] 4. Update system_prompts.py — delete intent, task owner, anti-hallucination, Hebrew cleanup
  - [x] 4.1 Update UNIFIED_CLASSIFY_AND_RESPOND
    - Add `delete_task` to the intent list with Hebrew description: "המשתמש רוצה למחוק או לבטל משימה"
    - Add `delete_target` field to JSON response format (task number, title string, or null)
    - Add `assigned_to` field to `task_data` section
    - Add anti-hallucination instruction in Hebrew: "אל תמציא פעולות שלא ביצעת. אם לא מחקת/השלמת/יצרת משימה בפועל — אל תגיד שעשית את זה. תאר רק מה שאתה באמת עושה: מסווג כוונה ומייצר תשובה."
    - _Requirements: 4.1, 4.2, 6.2, 8.1, 8.2_
  - [x] 4.2 Update TASK_EXTRACTOR_BEDROCK — add assigned_to, convert to Hebrew
    - Add `assigned_to` field to JSON extraction schema with Hebrew instructions for extracting the assignee name
    - Convert English instructions to Hebrew only (keep JSON field names in English)
    - _Requirements: 6.1, 9.3_
  - [x] 4.3 Update FORTRESS_BASE — Hebrew only
    - Replace the English instruction string with Hebrew equivalent, keeping the same meaning
    - _Requirements: 9.1, 9.4_
  - [x] 4.4 Update INTENT_CLASSIFIER — add delete_task
    - Add `delete_task` to the intent list in the INTENT_CLASSIFIER prompt
    - _Requirements: 4.1_

- [x] 5. Update workflow_engine.py — delete handler, owner resolution, dedup
  - [x] 5.1 Add `delete_target` to WorkflowState TypedDict
    - Add `delete_target: str | None` field to the `WorkflowState` TypedDict
    - Add `"delete_target": None` to the initial state in `run_workflow()`
    - _Requirements: 3.1, 3.2_
  - [x] 5.2 Add `_resolve_member_by_name()` helper function
    - New function: `def _resolve_member_by_name(db: Session, name: str) -> UUID | None`
    - Query `FamilyMember` where `func.lower(FamilyMember.name).contains(name.lower())`
    - Return first match's ID, or None if no match
    - _Requirements: 6.3, 6.4, 6.5_
  - [x] 5.3 Add `delete_task` to `_PERMISSION_MAP`
    - Add `"delete_task": ("tasks", "write")` to the `_PERMISSION_MAP` dict
    - _Requirements: 3.6_
  - [x] 5.4 Implement `delete_task_node` async function
    - Parse message to find task number (regex `\d+` at end) or title (strip delete keywords, use remainder)
    - Number detection: index into member's open task list via `list_tasks(db, status="open", assigned_to=member.id)`
    - Title detection: case-insensitive match against open tasks
    - If match found → `archive_task(db, task.id)` → respond with `PERSONALITY_TEMPLATES["task_deleted"].format(title=task.title)`
    - If ambiguous (no number/title extractable) → respond with `task_delete_which` template + numbered task list
    - If not found / out of range → respond with `task_not_found` template
    - Import `archive_task` from `src.services.tasks`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_
  - [x] 5.5 Update `task_create_node` — duplicate check, owner resolution, created_by
    - Before creating, query for duplicate: same `lower(title)`, same `assigned_to`, status `open`, `created_at` within last 5 minutes
    - If duplicate found → return `{"response": PERSONALITY_TEMPLATES["task_duplicate"]}`, skip creation
    - Resolve `assigned_to` name from `task_data.get("assigned_to")` using `_resolve_member_by_name()`; fall back to sender ID if no match
    - Always set `created_by` to `state["member"].id`
    - _Requirements: 6.3, 6.4, 6.5, 6.6, 7.1, 7.2_
  - [x] 5.6 Update `_intent_router` and `_permission_router`
    - `_intent_router`: `delete_task` routes to `"permission_node"` (already handled by the else branch, but verify)
    - `_permission_router`: add branch for `granted + intent == "delete_task"` → `"delete_task_node"`
    - _Requirements: 3.1_
  - [x] 5.7 Update `_build_graph` — add delete_task_node to graph
    - Add `graph.add_node("delete_task_node", delete_task_node)`
    - Update conditional edges from `permission_node` to include `"delete_task_node": "delete_task_node"`
    - Add `graph.add_edge("delete_task_node", "response_node")`
    - _Requirements: 3.1, 3.3_

- [x] 6. Update unified_handler.py — extract delete_target
  - Extract `delete_target` from parsed JSON when intent is `delete_task`
  - Return it embedded in `task_data` dict (e.g. `{"delete_target": value}`) or as a separate field
  - Update the return tuple handling so `delete_target` is available in workflow state
  - _Requirements: 4.1, 4.2_

- [x] 7. Create migration 005_cleanup_corrupt_data.sql
  - Create `fortress/migrations/005_cleanup_corrupt_data.sql` with three idempotent operations:
    - Archive tasks with empty or null titles: `UPDATE tasks SET status = 'archived' WHERE title IS NULL OR trim(title) = '';`
    - Archive open tasks with null created_by: `UPDATE tasks SET status = 'archived' WHERE created_by IS NULL AND status = 'open';`
    - Deduplicate open tasks: keep newest per `(lower(title), assigned_to)` group, archive the rest using a CTE with `ROW_NUMBER()`
  - All operations use soft-delete only (`SET status = 'archived'`), never SQL DELETE
  - _Requirements: 10.1, 10.2, 10.3, 10.4_

- [x] 8. Checkpoint — verify existing tests still pass
  - Ensure all 201 existing tests pass with `pytest fortress/tests/ -x -q`
  - Ask the user if questions arise.

- [x] 9. Create and update all tests
  - [x] 9.1 Update `tests/test_intent_detector.py`
    - Add `"delete_task"` to the `required` set in `test_intents_contains_all_required`
    - Add keyword matching tests for each of the 5 delete keywords: "מחק משימה", "מחק", "הסר משימה", "בטל משימה", "delete task"
    - Add test that "מחק משימה 3" also returns `delete_task` (substring match)
    - _Requirements: 11.2_
  - [x] 9.2 Update `tests/test_personality.py`
    - Add `task_deleted`, `task_delete_which`, `task_not_found`, `task_duplicate` to `REQUIRED_TEMPLATE_KEYS` set
    - Update the test name `test_templates_has_all_ten_keys` → adjust count or rename to `test_templates_has_all_required_keys`
    - _Requirements: 11.3_
  - [x] 9.3 Update `tests/test_routing_policy.py`
    - Add `"delete_task"` to the `test_medium_sensitivity_intents` parametrize list
    - _Requirements: 11.3_
  - [x] 9.4 Create `tests/test_delete_task.py`
    - Test delete by task number: mock `list_tasks` returning 3 tasks, send "מחק משימה 2", verify `archive_task` called with correct task ID
    - Test delete by title match: mock task list, send "מחק לקנות חלב", verify case-insensitive match and archive
    - Test ambiguous delete (no number/title): verify response contains `task_delete_which` template with numbered list
    - Test task not found: verify response contains `task_not_found` template
    - Test task number out of range: verify `task_not_found` response
    - Test that `archive_task` is used (not `complete_task` or raw DELETE)
    - Test `_permission_router` routes `delete_task` to `delete_task_node` when granted
    - All tests use `unittest.mock.MagicMock` and `AsyncMock`, `@pytest.mark.asyncio`
    - _Requirements: 11.1_
  - [x] 9.5 Create `tests/test_task_owner.py`
    - Test `_resolve_member_by_name` exact match
    - Test `_resolve_member_by_name` partial match (e.g., "שגב" matches "שגב כהן")
    - Test `_resolve_member_by_name` case-insensitive match
    - Test no-match fallback to sender ID
    - Test `created_by` always set to sender's member ID
    - Test `assigned_to` from `task_data` resolved to member UUID
    - Test warning logged when name doesn't match
    - All tests use mocked DB session
    - _Requirements: 11.4_
  - [x] 9.6 Create `tests/test_duplicate_prevention.py`
    - Test duplicate detected within 5 minutes: verify `create_task` not called, response is `task_duplicate`
    - Test no duplicate when title differs
    - Test no duplicate when `assigned_to` differs
    - Test no duplicate when existing task is older than 5 minutes
    - Test no duplicate when existing task status is not `open` (e.g., `done` or `archived`)
    - All tests use mocked DB session
    - _Requirements: 11.5_
  - [x] 9.7 Update `tests/test_unified_handler.py`
    - Add test for `delete_task` intent with `delete_target` field in JSON response
    - Verify `delete_target` is extracted and returned correctly
    - _Requirements: 11.1_

- [x] 10. Update README.md — add STABLE-3 milestone
  - Add a new row in the roadmap table for "STABLE-3 — Core Flows Hardening" with status "✅ Complete"
  - Update the test count to reflect the new total
  - _Requirements: 12.1_

- [-] 11. Final checkpoint — run all tests
  - Run `pytest fortress/tests/ -x -q` and ensure all tests pass (existing 201 + ~30 new)
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- All deletions use soft-delete (`status = 'archived'`), never SQL DELETE
- All 201 existing tests must continue to pass without modification
- No property-based testing — unit tests only with pytest + mocks
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
