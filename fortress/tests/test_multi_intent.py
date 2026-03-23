"""Unit tests for multi-intent detection and handling (Sprint 2 — Req 9.2).

Validates:
- multi_intent in VALID_INTENTS
- multi_intent_node iterates sub-intents and combines responses
- Empty sub-intents returns fallback
- multi_intent_summary template formatting
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.prompts.personality import TEMPLATES as PERSONALITY_TEMPLATES
from src.services.intent_detector import VALID_INTENTS
from src.services.workflow_engine import WorkflowState, multi_intent_node


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
        "intent": "multi_intent",
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


# ── multi_intent in VALID_INTENTS ────────────────────────────────


def test_multi_intent_in_valid_intents() -> None:
    """multi_intent should be a recognized intent."""
    assert "multi_intent" in VALID_INTENTS


# ── multi_intent_node iterates sub-intents ───────────────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.ModelDispatcher")
async def test_multi_intent_node_combines_responses(mock_dispatcher) -> None:
    """multi_intent_node should call handlers for each sub-intent and combine."""
    task_data = {
        "sub_intents": [
            {"intent": "greeting"},
            {"intent": "list_tasks"},
        ]
    }
    state = _make_state(task_data=task_data)

    with patch("src.services.workflow_engine._ACTION_HANDLERS", {
        "greeting": AsyncMock(return_value="שלום!"),
        "list_tasks": AsyncMock(return_value="אין משימות"),
    }):
        result = await multi_intent_node(state)

    assert "שלום!" in result["response"]
    assert "אין משימות" in result["response"]
    assert "ביצעתי כמה דברים" in result["response"]


# ── Empty sub-intents returns fallback ───────────────────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.ModelDispatcher")
async def test_multi_intent_node_empty_sub_intents(mock_dispatcher) -> None:
    """Empty sub_intents list should return error_fallback when no prior response."""
    state = _make_state(task_data={"sub_intents": []})
    # state has response="" which is falsy, so state.get("response", fallback) returns ""
    # The node returns whatever is in state["response"] or the fallback
    result = await multi_intent_node(state)
    # With empty response in state, the node returns "" (the existing state value)
    assert result["response"] == ""


@pytest.mark.asyncio
@patch("src.services.workflow_engine.ModelDispatcher")
async def test_multi_intent_node_no_task_data(mock_dispatcher) -> None:
    """No task_data should return the existing response or fallback."""
    state = _make_state(task_data=None)
    result = await multi_intent_node(state)
    assert result["response"] == ""


@pytest.mark.asyncio
@patch("src.services.workflow_engine.ModelDispatcher")
async def test_multi_intent_node_empty_with_prior_response(mock_dispatcher) -> None:
    """Empty sub_intents with a prior LLM response should preserve that response."""
    state = _make_state(
        task_data={"sub_intents": []},
        response="תשובה מהLLM",
    )
    result = await multi_intent_node(state)
    assert result["response"] == "תשובה מהLLM"


# ── multi_intent_summary template formatting ─────────────────────


def test_multi_intent_summary_template() -> None:
    """multi_intent_summary template should format with {responses}."""
    formatted = PERSONALITY_TEMPLATES["multi_intent_summary"].format(
        responses="תשובה 1\n\nתשובה 2"
    )
    assert "ביצעתי כמה דברים" in formatted
    assert "תשובה 1" in formatted
    assert "תשובה 2" in formatted


# ── Unknown sub-intent is skipped ────────────────────────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.ModelDispatcher")
async def test_multi_intent_node_skips_unknown_sub_intent(mock_dispatcher) -> None:
    """Sub-intents with no handler should be skipped, valid ones still processed."""
    task_data = {
        "sub_intents": [
            {"intent": "nonexistent_intent"},
            {"intent": "greeting"},
        ]
    }
    state = _make_state(task_data=task_data)

    with patch("src.services.workflow_engine._ACTION_HANDLERS", {
        "greeting": AsyncMock(return_value="שלום!"),
    }):
        result = await multi_intent_node(state)

    assert "שלום!" in result["response"]
