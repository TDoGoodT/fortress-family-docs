# Implementation Plan: Sprint 1 — State, Time & Verification

## Overview

Adds conversation state tracking, deterministic Israel-timezone time injection, action verification, confirmation flows, cancel/update intents, and reference resolution to the Fortress workflow engine. All changes are within the existing `fortress/src/` tree using Python.

## Tasks

- [x] 1. Create migration 007 — conversation_state table
  - Create `fortress/migrations/007_conversation_state.sql`
  - Table: conversation_state with columns: id (UUID PK), family_member_id (UUID NOT NULL UNIQUE FK→family_members), last_intent (TEXT), last_entity_type (TEXT), last_entity_id (UUID), last_action (TEXT), pending_confirmation (BOOLEAN DEFAULT false), pending_action (JSONB), context (JSONB DEFAULT '{}'), updated_at (TIMESTAMPTZ DEFAULT now()), created_at (TIMESTAMPTZ DEFAULT now())
  - Add index on family_member_id
  - Wrap in BEGIN/COMMIT
  - _Requirements: 1.1, 1.2, 1.3_

- [x] 2. Add ConversationState ORM model
  - [x] 2.1 Add ConversationState class to `fortress/src/models/schema.py`
    - All mapped columns matching migration 007
    - One-to-one relationship to FamilyMember with `uselist=False`
    - _Requirements: 2.1, 2.2_
  - [x] 2.2 Add back-reference on FamilyMember
    - Add `conversation_state` relationship on FamilyMember with `uselist=False`
    - _Requirements: 2.3_

- [x] 3. Create conversation_state.py service
  - Create `fortress/src/services/conversation_state.py`
  - Implement `get_state(db, member_id)` — get-or-create pattern
  - Implement `update_state(db, member_id, **kwargs)` — partial update, bump updated_at
  - Implement `clear_state(db, member_id)` — reset all mutable fields
  - Implement `set_pending_confirmation(db, member_id, action_type, action_data)` — set pending_confirmation=True, store action in pending_action
  - Implement `resolve_pending(db, member_id)` — return pending_action and clear, or None
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_

- [x] 4. Create time_context.py and add pytz dependency
  - [x] 4.1 Add `pytz==2024.1` to `fortress/requirements.txt`
    - _Requirements: 4.5_
  - [x] 4.2 Create `fortress/src/utils/time_context.py`
    - Implement `get_time_context()` returning dict with keys: now, today_date, today_day_he, today_display, tomorrow_date, tomorrow_display, current_time, hour — all in Asia/Jerusalem
    - Implement `_day_name_he(weekday)` — Hebrew day names (0=Monday → "יום שני")
    - Implement `_month_name_he(month)` — Hebrew month names (1 → "ינואר")
    - Implement `format_time_for_prompt()` — Hebrew formatted string for LLM prompt injection
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [x] 5. Update personality.py — new templates
  - Add to TEMPLATES dict: `confirm_delete`, `action_cancelled`, `cancelled`, `task_updated`, `task_update_which`, `verification_failed`
  - _Requirements: 6.6, 7.6, 11.6_

- [x] 6. Update intent_detector.py — cancel and update intents
  - [x] 6.1 Add cancel_action keywords to `_match_keywords`
    - Keywords: "עזוב", "תעזוב", "בטל", "תבטל", "לא", "cancel"
    - Prefix match: "אל תעשה", "אל "
    - Add `cancel_action` to INTENTS dict
    - _Requirements: 7.1, 7.2, 7.3_
  - [x] 6.2 Add update_task keywords to `_match_keywords`
    - Keywords: "תשנה", "תעדכן", "עדכן", "שנה", "update"
    - Add `update_task` to INTENTS dict
    - _Requirements: 11.1, 11.2_

- [x] 7. Update routing_policy.py
  - Add `cancel_action: "low"` to SENSITIVITY_MAP
  - Add `update_task: "medium"` to SENSITIVITY_MAP
  - _Requirements: 7.4, 11.3_

- [x] 8. Update workflow_engine.py — confirmation, state management, verification, reference resolution
  - [x] 8.1 Extend WorkflowState TypedDict
    - Add keys: conv_state, time_context, state_context, created_task_id, deleted_task_id, listed_tasks, created_recurring_id
    - _Requirements: 5.1, 5.2_
  - [x] 8.2 Add confirmation_check_node
    - Load conversation state, check pending_confirmation
    - "כן" → resolve_pending + execute action
    - "לא" / cancel → resolve_pending + cancelled template
    - Other → clear pending, fall through to intent_node
    - Set as new graph entry point (before intent_node)
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_
  - [x] 8.3 Add cancel_action_node
    - Clear conversation state, return cancelled template
    - _Requirements: 7.5_
  - [x] 8.4 Add resolve_reference helper
    - Pronoun check: "אותה", "אותו", "את זה" → last_entity_id from conv_state
    - Index check: "משימה N" → task_ids from conv_state.context
    - Name check: query family_members by name
    - _Requirements: 8.1, 8.2, 8.3, 8.4_
  - [x] 8.5 Add verification_node
    - After action nodes, query DB to confirm create/delete/update persisted
    - Return verification_failed template if record not found
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_
  - [x] 8.6 Add update_state_node
    - After conversation_save_node, before END
    - Update conversation state based on intent (create_task, delete_task, list_tasks, cancel_action, etc.)
    - _Requirements: 10.1, 10.2, 10.3, 10.4_
  - [x] 8.7 Add update_task_node
    - Resolve target task from state or message
    - Apply field updates (title, due_date, assigned_to, priority, status)
    - Return task_updated template
    - _Requirements: 11.4, 11.5_
  - [x] 8.8 Modify delete_task flow for confirmation
    - Instead of immediate delete, set pending confirmation and return confirm_delete template
    - _Requirements: 6.1_
  - [x] 8.9 Update _PERMISSION_MAP and _ACTION_HANDLERS
    - Add `update_task: ("tasks", "write")` and `cancel_action: None`
    - Wire new nodes into graph edges and conditional routing
    - _Requirements: 11.4_
  - [x] 8.10 Rebuild LangGraph StateGraph
    - Add all new nodes: confirmation_check_node, cancel_action_node, update_task_node, verification_node, update_state_node
    - Set confirmation_check_node as entry point
    - Wire conditional edges for confirmation flow, cancel, update_task, verification
    - _Requirements: 6.5, 9.1_

- [x] 9. Update unified_handler.py — inject time and state into prompts
  - Add `time_context` and `state_context` parameters to `handle_with_llm`
  - Inject `format_time_for_prompt()` output and state context into the prompt
  - Follow prompt order: {PERSONALITY} {TIME_CONTEXT} {STATE_CONTEXT} {SPECIFIC_PROMPT} הודעת המשתמש: {message}
  - _Requirements: 5.3, 5.4, 5.5_

- [x] 10. Update system_prompts.py — add update_task to unified prompt
  - Add `update_task` to the intent list in UNIFIED_CLASSIFY_AND_RESPOND
  - Add extraction instructions for update_task intent
  - _Requirements: 11.7_

- [x] 11. Checkpoint — Ensure all source code compiles and imports work
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Create all unit tests
  - [x] 12.1 Create `fortress/tests/test_conversation_state.py`
    - Test get_state create + retrieve
    - Test update_state partial update
    - Test clear_state resets fields
    - Test set_pending_confirmation
    - Test resolve_pending with and without pending
    - _Requirements: 12.1_
  - [x] 12.2 Create `fortress/tests/test_time_context.py`
    - Test get_time_context returns all required keys
    - Test format_time_for_prompt returns non-empty string
    - Test _day_name_he returns correct Hebrew day names
    - Test _month_name_he returns correct Hebrew month names
    - _Requirements: 12.2_
  - [x] 12.3 Create `fortress/tests/test_confirmation_flow.py`
    - Test confirm-yes executes pending action
    - Test confirm-no cancels pending action
    - Test confirm-other clears pending and continues
    - Test delete_task sets pending confirmation
    - _Requirements: 12.3_
  - [x] 12.4 Create `fortress/tests/test_action_verification.py`
    - Test create_task verification succeeds when task exists
    - Test delete_task verification succeeds when task is archived
    - Test verification failure returns error template
    - _Requirements: 12.4_
  - [x] 12.5 Create `fortress/tests/test_reference_resolution.py`
    - Test "אותה" resolution from last_entity_id
    - Test "משימה 3" resolution by index from context task_ids
    - Test person name resolution from family_members
    - Test ambiguous name returns clarification
    - _Requirements: 12.5_
  - [x] 12.6 Update `fortress/tests/test_intent_detector.py`
    - Add tests for cancel_action keywords ("עזוב", "תעזוב", "בטל", "תבטל", "לא", "cancel")
    - Add tests for cancel_action prefix ("אל תעשה", "אל ")
    - Add tests for update_task keywords ("תשנה", "תעדכן", "עדכן", "שנה", "update")
    - _Requirements: 12.6_

- [x] 13. Update README.md roadmap
  - Add Sprint 1 row to the roadmap table with status, description, and test count
  - _Requirements: 13.1_

- [x] 14. Final checkpoint — Run all tests and push
  - Ensure all tests pass (existing 318 + new tests), ask the user if questions arise.
  - Push to origin main when all tests pass.

## Notes

- Unit tests only — no property-based tests
- All 318 existing tests must continue to pass unchanged
- Python is the implementation language (matching existing codebase)
- Checkpoints ensure incremental validation
- Each task references specific requirement acceptance criteria for traceability
