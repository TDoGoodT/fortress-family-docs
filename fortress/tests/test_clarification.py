"""Unit tests for clarification flow (Sprint 2 — Req 9.3).

Validates:
- ambiguous in VALID_INTENTS
- clarification_node presents numbered options and stores in pending_action
- confirmation_check_node handles type="clarification" — valid number routes
- Invalid number re-presents options
- Empty options returns cant_understand
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.prompts.personality import TEMPLATES as PERSONALITY_TEMPLATES
from src.services.intent_detector import VALID_INTENTS
from src.services.workflow_engine import (
    WorkflowState,
    clarification_node,
    confirmation_check_node,
)


def _make_state(**overrides) -> WorkflowState:
    member = MagicMock()
    member.id = uuid4()
    member.name = "TestUser"
    state: WorkflowState = {
        "db": MagicMock(),
        "member": member,
        "phone": "0501234567",
        "message_text": "test message",
        "has_media": False,
        "media_file_path": None,
        "intent": "ambiguous",
        "permission_granted": True,
        "memories": [],
        "response": "",
        "error": None,
        "task_data": None,
        "from_unified": True,
        "delete_target": None,
        "conv_state": None,
        "time_context": "",
        "state_context": "",
        "created_task_id": None,
        "deleted_task_id": None,
        "listed_tasks": [],
        "created_recurring_id": None,
    }
    state.update(overrides)
    return state


def _make_conv_state(pending=False, pending_action=None, last_intent=None):
    cs = MagicMock()
    cs.pending_confirmation = pending
    cs.pending_action = pending_action
    cs.last_intent = last_intent
    cs.last_entity_type = None
    cs.last_action = None
    cs.context = {}
    return cs


# ── ambiguous in VALID_INTENTS ───────────────────────────────────


def test_ambiguous_in_valid_intents() -> None:
    """ambiguous should be a recognized intent."""
    assert "ambiguous" in VALID_INTENTS


# ── clarification_node presents numbered options ─────────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.set_pending_confirmation")
async def test_clarification_node_presents_options(mock_set_pending) -> None:
    """clarification_node should present numbered options and store them."""
    options = ["create_task", "list_tasks", "store_info"]
    state = _make_state(task_data={"options": options})

    result = await clarification_node(state)

    assert "1." in result["response"]
    assert "2." in result["response"]
    assert "3." in result["response"]
    mock_set_pending.assert_called_once_with(
        state["db"], state["member"].id, "clarification", {"options": options}
    )


# ── confirmation_check_node: valid number routes to correct intent


@pytest.mark.asyncio
@patch("src.services.workflow_engine.resolve_pending")
@patch("src.services.workflow_engine.get_state")
async def test_clarification_valid_number_routes(mock_get_state, mock_resolve) -> None:
    """Replying '2' to clarification should route to the second option."""
    options = ["create_task", "list_tasks", "store_info"]
    conv_state = _make_conv_state(
        pending=True,
        pending_action={"type": "clarification", "data": {"options": options}},
    )
    mock_get_state.return_value = conv_state
    mock_resolve.return_value = {"type": "clarification", "data": {"options": options}}

    state = _make_state(message_text="2")
    result = await confirmation_check_node(state)

    assert result["intent"] == "list_tasks"


# ── Invalid number re-presents options ───────────────────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.set_pending_confirmation")
@patch("src.services.workflow_engine.resolve_pending")
@patch("src.services.workflow_engine.get_state")
async def test_clarification_invalid_number_re_presents(
    mock_get_state, mock_resolve, mock_set_pending
) -> None:
    """Invalid number (e.g., 9 for 3 options) should re-present the options."""
    options = ["create_task", "list_tasks"]
    conv_state = _make_conv_state(
        pending=True,
        pending_action={"type": "clarification", "data": {"options": options}},
    )
    mock_get_state.return_value = conv_state
    mock_resolve.return_value = {"type": "clarification", "data": {"options": options}}

    state = _make_state(message_text="9")
    result = await confirmation_check_node(state)

    assert "1." in result["response"]
    assert "2." in result["response"]


# ── Empty options returns cant_understand ─────────────────────────


@pytest.mark.asyncio
async def test_clarification_node_empty_options() -> None:
    """Empty options list should return cant_understand template."""
    state = _make_state(task_data={"options": []})
    result = await clarification_node(state)
    assert "TestUser" in result["response"]
    assert "לא הבנתי" in result["response"]
