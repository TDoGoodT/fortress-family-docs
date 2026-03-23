# Implementation Plan: Sprint 2 — Intent + Entity + UX

## Overview

Incremental implementation of Sprint 2 features following the design document. Each task builds on the previous, starting with the core intent detector rewrite and ending with integration wiring, tests, and README update. All code is Python. All 365 existing tests must continue to pass.

## Tasks

- [x] 1. Rewrite intent_detector.py with priority-based matching
  - [x] 1.1 Add new intent entries and rewrite `_match_keywords` with 4-tier priority system
    - Add `multi_intent`, `ambiguous`, `bulk_delete_tasks`, `bulk_delete_range`, `store_info` to `INTENTS` dict and `VALID_INTENTS`
    - Add `import re` at the top of the file
    - Rewrite `_match_keywords` with Priority 0 (cancel override: "אל " prefix, "לא" exact), Priority 1 (exact phrases including bulk patterns), Priority 2 (action verbs as substring), Priority 3 (standalone keywords), Priority 4 (return None → `needs_llm`)
    - Ensure "משימה" singular returns `None` (falls through to `needs_llm`)
    - Preserve all existing keyword→intent mappings for backward compatibility
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 2.2, 3.1, 4.1, 4.2, 4.3, 8.1_
  - [x]* 1.2 Write unit tests for priority-based intent classification
    - Create `fortress/tests/test_intent_priority.py`
    - Test Priority 0: "אל תמחק" → `cancel_action`, "לא" → `cancel_action`
    - Test Priority 1: "משימה חדשה: X" → `create_task`, "מחק משימה" → `delete_task`, "סיום משימה" → `complete_task`, "באג:" → `report_bug`, "מחק הכל" → `bulk_delete_tasks`, "מחק 1-5" → `bulk_delete_range`, "מחק 2 עד 4" → `bulk_delete_range`
    - Test Priority 2: "תמחק" → `delete_task`, "תיצור" → `create_task`, "תעדכן" → `update_task`, "בוצע" → `complete_task`
    - Test Priority 3: "משימות" → `list_tasks`, "שלום" → `greeting`, "באגים" → `list_bugs`
    - Test "משימה" singular → `needs_llm`
    - Test priority ordering: "מחק משימה חדשה" → `delete_task` (P1 beats P2)
    - Test cancel override: "אל תיצור משימה" → `cancel_action` (P0 beats all)
    - _Requirements: 9.1_

- [x] 2. Checkpoint — Verify intent detector
  - Ensure all tests pass (existing 365 + new intent priority tests), ask the user if questions arise.

- [x] 3. Update personality templates
  - [x] 3.1 Add all new personality templates to `fortress/src/prompts/personality.py`
    - Add to `TEMPLATES` dict: `multi_intent_summary`, `clarify`, `clarify_option`, `bulk_delete_confirm`, `bulk_deleted`, `bulk_range_confirm`, `task_assigned_notification`, `need_list_first`, `task_similar_exists`, `info_stored`
    - _Requirements: 2.5, 3.5, 4.7, 5.3, 6.4, 7.4, 8.4_

- [x] 4. Update routing policy with new intents
  - [x] 4.1 Add new entries to `SENSITIVITY_MAP` in `fortress/src/services/routing_policy.py`
    - Add `multi_intent`, `ambiguous`, `bulk_delete_tasks`, `bulk_delete_range`, `store_info` all mapped to `"medium"`
    - _Requirements: 2.3, 4.4, 8.5_

- [x] 5. Update system prompts for multi-intent, ambiguous, and store_info
  - [x] 5.1 Modify `UNIFIED_CLASSIFY_AND_RESPOND` in `fortress/src/prompts/system_prompts.py`
    - Add `multi_intent`, `ambiguous`, `store_info` to the intent list with Hebrew descriptions
    - Add instructions for multi-intent JSON format with `sub_intents` array
    - Add instructions for ambiguous JSON format with `options` array
    - Add `store_info` description for factual information storage
    - _Requirements: 2.1, 3.2 (partial — LLM prompt side), 8.2_

- [x] 6. Update unified_handler.py for multi-intent and ambiguous parsing
  - [x] 6.1 Modify `handle_with_llm` in `fortress/src/services/unified_handler.py`
    - After JSON parsing, if `intent == "multi_intent"`, extract `sub_intents` from data and set `task_data = {"sub_intents": sub_intents}`
    - If `intent == "ambiguous"`, extract `options` from data and set `task_data = {"options": options}`
    - If `intent == "store_info"`, pass through normally (no special extraction needed)
    - _Requirements: 2.1, 2.4 (partial), 3.2 (partial)_

- [x] 7. Checkpoint — Verify templates, routing, prompts, and unified handler
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement workflow engine changes — new nodes and modified nodes
  - [x] 8.1 Add `_INTENT_LABELS_HE` dict and `multi_intent_node` to `fortress/src/services/workflow_engine.py`
    - Add Hebrew intent label mapping dict
    - Implement `multi_intent_node` that iterates sub-intents, calls handlers, and combines responses using `multi_intent_summary` template
    - _Requirements: 2.4, 2.5_
  - [x] 8.2 Add `clarification_node` to `fortress/src/services/workflow_engine.py`
    - Present numbered options using `clarify` and `clarify_option` templates
    - Store options in `pending_action` with `type="clarification"` via `set_pending_confirmation`
    - _Requirements: 3.2, 3.3, 3.5_
  - [x] 8.3 Modify `confirmation_check_node` to handle clarification and bulk_delete pending actions
    - Add `type="clarification"` handling: parse number from message, look up option, set `result["intent"]` to selected intent; on invalid number, re-present options
    - Add `type="bulk_delete"` handling: iterate `task_ids`, archive each, return `bulk_deleted` template with count
    - Add `type="create_task_similar"` handling: create the task on confirmation, return `task_created` template
    - _Requirements: 3.4, 3.6, 4.5, 4.6, 7.3_
  - [x] 8.4 Add `bulk_delete_node` to `fortress/src/services/workflow_engine.py`
    - Handle `bulk_delete_tasks`: list all open tasks, present for confirmation with `bulk_delete_confirm` template
    - Handle `bulk_delete_range`: parse range from message, validate bounds, present selected tasks for confirmation with `bulk_range_confirm` template
    - Use `set_pending_confirmation` with `type="bulk_delete"` and task IDs
    - _Requirements: 4.5, 4.6, 4.7_
  - [x] 8.5 Add `store_info_node` to `fortress/src/services/workflow_engine.py`
    - Save message content as Memory with `category="fact"`, `memory_type="permanent"`, `source="user_input"` using `save_memory`
    - Return `info_stored` template on success
    - _Requirements: 8.3, 8.4_
  - [x] 8.6 Add `assignee_notify_node` to `fortress/src/services/workflow_engine.py`
    - After task creation, check if `assigned_to != sender`
    - If different, send WhatsApp notification using `send_text_message` with `task_assigned_notification` template
    - Log success/failure; never raise to caller
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_
  - [x] 8.7 Modify `task_create_node` with 3-strategy duplicate detection
    - Replace current 5-minute window check with: Strategy 1 (exact title match, case-insensitive → reject), Strategy 2 (substring match → confirm via `task_similar_exists`), Strategy 3 (normalized match stripping Hebrew prefixes ל/ה → confirm)
    - Use `set_pending_confirmation` with `type="create_task_similar"` for similar matches
    - _Requirements: 7.1, 7.2, 7.3, 7.4_
  - [x] 8.8 Modify `update_state_node` to save `task_list_order`
    - Change `list_tasks` branch to save `task_list_order` (list of task ID strings) instead of `task_ids` in context
    - _Requirements: 6.1_
  - [x] 8.9 Modify `resolve_reference` to use `task_list_order` and bare numbers
    - Check `task_list_order` first, fall back to `task_ids` for backward compatibility
    - Add bare number matching (e.g., "מחק 2" or just "2") in addition to "משימה N"
    - _Requirements: 6.2_
  - [x] 8.10 Modify `delete_task_node` to use `task_list_order` from conversation state
    - Resolve task number via `task_list_order` from `conv_state.context`
    - If number given but no `task_list_order` exists, return `need_list_first` template
    - _Requirements: 6.2, 6.3, 6.4_
  - [x] 8.11 Update `_PERMISSION_MAP`, `_intent_router`, `_permission_router`, and `_build_graph`
    - Add `bulk_delete_tasks`, `bulk_delete_range`, `store_info`, `multi_intent`, `ambiguous` to `_PERMISSION_MAP`
    - Update `_intent_router` to route `bulk_delete_tasks`/`bulk_delete_range` to `permission_node`
    - Update `_permission_router` to route `multi_intent` → `multi_intent_node`, `ambiguous` → `clarification_node`, `bulk_delete_tasks`/`bulk_delete_range` → `bulk_delete_node`, `store_info` → `store_info_node`
    - Add new nodes to `_build_graph`: `multi_intent_node`, `clarification_node`, `bulk_delete_node`, `store_info_node`, `assignee_notify_node`
    - Wire edges: `task_create_node` → `assignee_notify_node` → `verification_node`; `multi_intent_node` → `response_node`; `clarification_node` → `response_node`; `bulk_delete_node` → `response_node`; `store_info_node` → `verification_node`
    - _Requirements: 2.4, 3.2, 4.4, 4.5, 5.1, 8.3_

- [x] 9. Checkpoint — Verify all workflow engine changes
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Write all Sprint 2 test files
  - [x]* 10.1 Write `fortress/tests/test_multi_intent.py`
    - Test `multi_intent` in `VALID_INTENTS`
    - Test `multi_intent_node` iterates sub-intents and combines responses
    - Test empty sub-intents returns fallback
    - Test `multi_intent_summary` template formatting
    - _Requirements: 9.2_
  - [x]* 10.2 Write `fortress/tests/test_clarification.py`
    - Test `ambiguous` in `VALID_INTENTS`
    - Test `clarification_node` presents numbered options and stores in `pending_action`
    - Test `confirmation_check_node` handles `type="clarification"` — valid number routes to correct intent
    - Test invalid number re-presents options
    - Test empty options returns `cant_understand`
    - _Requirements: 9.3_
  - [x]* 10.3 Write `fortress/tests/test_bulk_operations.py`
    - Test `bulk_delete_tasks`/`bulk_delete_range` keyword detection in intent detector
    - Test `bulk_delete_node` with `bulk_delete_tasks` intent — lists tasks, sets pending confirmation
    - Test `bulk_delete_node` with `bulk_delete_range` intent — parses range, validates bounds
    - Test `confirmation_check_node` handles `type="bulk_delete"` — archives correct tasks
    - Test empty task list returns `task_list_empty`
    - Test invalid range returns `task_not_found`
    - _Requirements: 9.4_
  - [x]* 10.4 Write `fortress/tests/test_assignee_notification.py`
    - Test notification sent when `assigned_to ≠ sender` (mock `send_text_message`)
    - Test no notification when `assigned_to == sender`
    - Test graceful handling when WhatsApp send fails
    - Test assignee not found in DB — logs warning, continues
    - _Requirements: 9.5_
  - [x]* 10.5 Write `fortress/tests/test_duplicate_detection.py`
    - Test exact duplicate (case-insensitive) → rejected with `task_duplicate` template
    - Test substring similarity → confirmation with `task_similar_exists` template
    - Test normalized (prefix-stripped ל/ה) similarity → confirmation
    - Test no match → task created successfully
    - Test `confirmation_check_node` handles `type="create_task_similar"` — creates task on "כן"
    - _Requirements: 9.6_
  - [x]* 10.6 Write store_info tests in `fortress/tests/test_workflow_engine.py` (append)
    - Test `store_info` in `VALID_INTENTS`
    - Test `store_info_node` saves memory with `category="fact"`, `memory_type="permanent"`
    - Test `info_stored` template used in response
    - _Requirements: 8.1, 8.3, 8.4_

- [x] 11. Checkpoint — Run full test suite
  - Ensure all tests pass (existing 365 + all new Sprint 2 tests), ask the user if questions arise.

- [x] 12. Update README roadmap
  - [x] 12.1 Add Sprint 2 row to the roadmap table in `README.md`
    - Add row: `| SPRINT-2 — Intent + Entity + UX | ✅ Complete | Priority intent classification, multi-intent, clarification, bulk ops, notifications | 400+ |`
    - Update test count in project structure section
    - _Requirements: 10.1_

- [x] 13. Final checkpoint — Full regression and push
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- The design uses Python throughout — no language selection needed
- All new nodes follow the existing async pattern with `WorkflowState` TypedDict
- Backward compatibility with existing `task_ids` context key is maintained via fallback in `resolve_reference`
