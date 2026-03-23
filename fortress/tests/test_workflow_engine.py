"""Unit tests for the workflow engine — routing, nodes, and Ollama removal."""

import inspect
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.services import workflow_engine
from src.services.workflow_engine import (
    WorkflowState,
    _intent_router,
    _permission_router,
    intent_node,
    task_create_node,
    unified_llm_node,
)


def _make_state(**overrides) -> WorkflowState:
    """Build a minimal WorkflowState dict with sensible defaults."""
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
        "intent": "",
        "permission_granted": False,
        "memories": [],
        "response": "",
        "error": None,
        "task_data": None,
        "from_unified": False,
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


# ── Intent routing (Property 6) ─────────────────────────────────


def test_keyword_routes_to_permission_node() -> None:
    """Keyword intent should route to permission_node, not unified_llm_node."""
    state = _make_state(intent="greeting")
    assert _intent_router(state) == "permission_node"


def test_needs_llm_routes_to_unified_node() -> None:
    """'needs_llm' intent should route to unified_llm_node."""
    state = _make_state(intent="needs_llm")
    assert _intent_router(state) == "unified_llm_node"


# ── Unified node sets state (Property 7) ────────────────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.ModelDispatcher")
@patch("src.services.workflow_engine.load_memories", return_value=[])
@patch("src.services.workflow_engine.handle_with_llm", new_callable=AsyncMock)
async def test_unified_node_sets_state(mock_handle, mock_mem, mock_disp) -> None:
    mock_handle.return_value = ("greeting", "שלום!", None)
    state = _make_state(intent="needs_llm")
    result = await unified_llm_node(state)
    assert result["intent"] == "greeting"
    assert result["response"] == "שלום!"
    assert result["from_unified"] is True
    assert result["task_data"] is None


@pytest.mark.asyncio
@patch("src.services.workflow_engine.ModelDispatcher")
@patch("src.services.workflow_engine.load_memories", return_value=[])
@patch("src.services.workflow_engine.handle_with_llm", new_callable=AsyncMock)
async def test_unified_node_stores_task_data_no_create(mock_handle, mock_mem, mock_disp) -> None:
    """unified_llm_node stores task_data but does NOT call create_task."""
    task_data = {"title": "לקנות חלב", "due_date": None, "category": "groceries", "priority": "normal"}
    mock_handle.return_value = ("create_task", "נוצרה משימה", task_data)
    state = _make_state(intent="needs_llm")
    with patch("src.services.workflow_engine.create_task") as mock_create:
        result = await unified_llm_node(state)
        mock_create.assert_not_called()
    assert result["task_data"] == task_data
    assert result["intent"] == "create_task"


# ── Task creation after permission (Property 8) ─────────────────


@pytest.mark.asyncio
async def test_task_created_after_permission_granted() -> None:
    """task_create_node should call create_task when task_data is present."""
    task_data = {"title": "לקנות חלב", "due_date": None, "category": "groceries", "priority": "normal"}
    state = _make_state(
        permission_granted=True,
        from_unified=True,
        task_data=task_data,
        intent="create_task",
    )
    # Configure mock DB so duplicate check and name resolution return None
    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.first.return_value = None
    state["db"].query.return_value = mock_query
    with patch("src.services.workflow_engine.create_task") as mock_create:
        await task_create_node(state)
        mock_create.assert_called_once()
        call_args = mock_create.call_args
        assert call_args[0][1] == "לקנות חלב"


def test_task_not_created_when_denied() -> None:
    """Permission denied + from_unified should route to response_node (no task creation)."""
    state = _make_state(
        permission_granted=False,
        from_unified=True,
        task_data={"title": "test"},
    )
    assert _permission_router(state) == "response_node"


# ── Unified path skips action_node (Property 9) ─────────────────


def test_unified_path_skips_action_node() -> None:
    """from_unified + granted should route to response_node, skipping action_node."""
    state = _make_state(permission_granted=True, from_unified=True)
    assert _permission_router(state) == "response_node"


def test_unified_path_with_task_data_routes_to_task_create() -> None:
    """from_unified + granted + task_data should route to task_create_node."""
    state = _make_state(
        permission_granted=True,
        from_unified=True,
        task_data={"title": "test"},
    )
    assert _permission_router(state) == "task_create_node"


# ── Permission denial replaces response (Property 10) ───────────


def test_denial_replaces_unified_response() -> None:
    """Denied permission should route to response_node regardless of from_unified."""
    state = _make_state(
        permission_granted=False,
        from_unified=True,
        response="LLM generated response",
    )
    assert _permission_router(state) == "response_node"


# ── OllamaClient not in workflow_engine (Property 11) ───────────


def test_no_ollama_in_workflow_engine() -> None:
    """OllamaClient should not be imported in workflow_engine module."""
    source = inspect.getsource(workflow_engine)
    assert "OllamaClient" not in source


# ── Ollama in fallback chain (Property 12) ───────────────────────


def test_ollama_in_fallback_chain() -> None:
    """Routing policy should still include 'ollama' in all route lists."""
    from src.services.routing_policy import ROUTE_MAP
    for level, providers in ROUTE_MAP.items():
        assert "ollama" in providers, f"'ollama' missing from {level} route"


# ── Response protection (Properties 4, 6) ────────────────────────

from src.services.workflow_engine import memory_save_node, conversation_save_node


@pytest.mark.asyncio
@patch("src.services.workflow_engine.BedrockClient")
@patch("src.services.workflow_engine.extract_memories_from_message", new_callable=AsyncMock)
async def test_memory_save_node_never_returns_response_key(mock_extract, mock_bedrock) -> None:
    """memory_save_node must never return a 'response' key."""
    state = _make_state(intent="ask_question", response="LLM answer")
    result = await memory_save_node(state)
    assert "response" not in result


@pytest.mark.asyncio
async def test_conversation_save_node_never_returns_response_key() -> None:
    """conversation_save_node must never return a 'response' key."""
    db = MagicMock()
    state = _make_state(intent="greeting", response="שלום!")
    state["db"] = db
    result = await conversation_save_node(state)
    assert "response" not in result


@pytest.mark.asyncio
@patch("src.services.workflow_engine.BedrockClient")
@patch("src.services.workflow_engine.extract_memories_from_message", new_callable=AsyncMock)
async def test_memory_save_failure_does_not_affect_response(mock_extract, mock_bedrock) -> None:
    """Exception in memory save preserves LLM response."""
    mock_extract.side_effect = Exception("memory extraction failed")
    state = _make_state(intent="ask_question", response="LLM answer")
    result = await memory_save_node(state)
    assert "response" not in result


@pytest.mark.asyncio
async def test_conversation_save_failure_does_not_affect_response() -> None:
    """Exception in conversation save preserves LLM response."""
    db = MagicMock()
    db.add.side_effect = Exception("db error")
    state = _make_state(intent="greeting", response="שלום!")
    state["db"] = db
    result = await conversation_save_node(state)
    assert "response" not in result


# ── Session rollback resilience (STABLE-6) ───────────────────────


@pytest.mark.asyncio
@patch("src.services.workflow_engine.BedrockClient")
@patch("src.services.workflow_engine.extract_memories_from_message", new_callable=AsyncMock)
async def test_memory_save_node_calls_rollback_on_failure(mock_extract, mock_bedrock) -> None:
    """memory_save_node calls db.rollback() when extraction fails."""
    mock_extract.side_effect = Exception("db integrity error")
    db = MagicMock()
    state = _make_state(intent="ask_question", response="LLM answer")
    state["db"] = db
    result = await memory_save_node(state)
    db.rollback.assert_called_once()
    assert result == {}


@pytest.mark.asyncio
async def test_conversation_save_node_calls_rollback_on_failure() -> None:
    """conversation_save_node calls db.rollback() when commit fails."""
    db = MagicMock()
    db.commit.side_effect = Exception("PendingRollbackError")
    state = _make_state(intent="greeting", response="שלום!")
    state["db"] = db
    result = await conversation_save_node(state)
    db.rollback.assert_called_once()
    assert result == {}


@pytest.mark.asyncio
@patch("src.services.workflow_engine.BedrockClient")
@patch("src.services.workflow_engine.extract_memories_from_message", new_callable=AsyncMock)
async def test_memory_save_node_survives_rollback_failure(mock_extract, mock_bedrock) -> None:
    """memory_save_node survives even if rollback itself fails."""
    mock_extract.side_effect = Exception("db error")
    db = MagicMock()
    db.rollback.side_effect = Exception("rollback failed too")
    state = _make_state(intent="ask_question", response="LLM answer")
    state["db"] = db
    result = await memory_save_node(state)
    assert result == {}
    assert "response" not in result


@pytest.mark.asyncio
async def test_conversation_save_node_survives_rollback_failure() -> None:
    """conversation_save_node survives even if rollback itself fails."""
    db = MagicMock()
    db.commit.side_effect = Exception("PendingRollbackError")
    db.rollback.side_effect = Exception("rollback failed too")
    state = _make_state(intent="greeting", response="שלום!")
    state["db"] = db
    result = await conversation_save_node(state)
    assert result == {}
    assert "response" not in result


# ── Bug tracker handlers (STABLE-6) ──────────────────────────────

from src.services.workflow_engine import (
    _ACTION_HANDLERS,
    _PERMISSION_MAP,
)


def test_permission_map_includes_bug_tracker() -> None:
    """_PERMISSION_MAP should include report_bug and list_bugs."""
    assert "report_bug" in _PERMISSION_MAP
    assert _PERMISSION_MAP["report_bug"] == ("tasks", "write")
    assert "list_bugs" in _PERMISSION_MAP
    assert _PERMISSION_MAP["list_bugs"] == ("tasks", "read")


def test_action_handlers_includes_bug_tracker() -> None:
    """_ACTION_HANDLERS should include report_bug and list_bugs."""
    assert "report_bug" in _ACTION_HANDLERS
    assert "list_bugs" in _ACTION_HANDLERS


@pytest.mark.asyncio
async def test_handle_report_bug_creates_record() -> None:
    """_handle_report_bug should add a BugReport to the DB and return confirmation."""
    from src.services.workflow_engine import _handle_report_bug

    db = MagicMock()
    member = MagicMock()
    member.id = uuid4()
    member.name = "TestUser"

    result = await _handle_report_bug(
        db, member, "באג: תמונה לא נשמרת", MagicMock(), None, "report_bug",
    )
    db.add.assert_called_once()
    db.flush.assert_called_once()
    assert "תמונה לא נשמרת" in result


@pytest.mark.asyncio
async def test_handle_report_bug_strips_english_prefix() -> None:
    """_handle_report_bug should strip 'bug:' prefix."""
    from src.services.workflow_engine import _handle_report_bug

    db = MagicMock()
    member = MagicMock()
    member.id = uuid4()

    result = await _handle_report_bug(
        db, member, "bug: photos not saving", MagicMock(), None, "report_bug",
    )
    assert "photos not saving" in result


@pytest.mark.asyncio
async def test_handle_list_bugs_empty() -> None:
    """_handle_list_bugs should return empty template when no bugs."""
    from src.services.workflow_engine import _handle_list_bugs
    from src.prompts.personality import TEMPLATES

    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
    member = MagicMock()
    member.id = uuid4()

    result = await _handle_list_bugs(
        db, member, "באגים", MagicMock(), None, "list_bugs",
    )
    assert result == TEMPLATES["bug_list_empty"]


@pytest.mark.asyncio
async def test_handle_list_bugs_with_bugs() -> None:
    """_handle_list_bugs should format bugs using format_bug_list."""
    from src.services.workflow_engine import _handle_list_bugs

    bug1 = MagicMock()
    bug1.description = "תמונה לא נשמרת"
    bug1.created_at = "2026-03-20T10:00:00"

    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [bug1]
    member = MagicMock()
    member.id = uuid4()

    result = await _handle_list_bugs(
        db, member, "באגים", MagicMock(), None, "list_bugs",
    )
    assert "תמונה לא נשמרת" in result


# ── store_info intent and node (Sprint 2 — Req 8.1, 8.3, 8.4) ──


from src.services.intent_detector import VALID_INTENTS
from src.services.workflow_engine import store_info_node


def test_store_info_in_valid_intents() -> None:
    """store_info should be a recognized intent."""
    assert "store_info" in VALID_INTENTS


@pytest.mark.asyncio
@patch("src.services.workflow_engine.save_memory", new_callable=AsyncMock)
async def test_store_info_node_saves_permanent_fact(mock_save) -> None:
    """store_info_node should save memory with category='fact' and memory_type='permanent'."""
    mock_memory = MagicMock()
    mock_memory.id = uuid4()
    mock_save.return_value = mock_memory

    state = _make_state(
        intent="store_info",
        message_text="הקוד לכספת הוא 1234",
        response="",
    )
    result = await store_info_node(state)

    mock_save.assert_called_once()
    call_kwargs = mock_save.call_args
    assert call_kwargs[1]["category"] == "fact"
    assert call_kwargs[1]["memory_type"] == "permanent"


@pytest.mark.asyncio
@patch("src.services.workflow_engine.save_memory", new_callable=AsyncMock)
async def test_store_info_node_uses_info_stored_template(mock_save) -> None:
    """store_info_node should return info_stored template on success."""
    from src.prompts.personality import TEMPLATES as PT

    mock_memory = MagicMock()
    mock_save.return_value = mock_memory

    state = _make_state(
        intent="store_info",
        message_text="הקוד לכספת הוא 1234",
        response="",
    )
    result = await store_info_node(state)

    assert "שמרתי את המידע" in result["response"]


@pytest.mark.asyncio
@patch("src.services.workflow_engine.save_memory", new_callable=AsyncMock)
async def test_store_info_node_fallback_on_exclusion(mock_save) -> None:
    """store_info_node should return error_fallback when memory is excluded."""
    from src.prompts.personality import TEMPLATES as PT

    mock_save.return_value = None  # excluded

    state = _make_state(
        intent="store_info",
        message_text="excluded content",
        response="",
    )
    result = await store_info_node(state)

    assert result["response"] == PT["error_fallback"]
