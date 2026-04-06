"""Tests for Phase A1: Prompt-first planning in the agent loop.

Covers:
- Planning instructions in system prompt (Req 1, 10.1)
- AgentResult telemetry defaults (Req 3, 10.2)
- _is_multi_tool_run() boundary cases (Req 4, 10.3)
- Integration tests with mocked Bedrock (Req 10.4–10.7)
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.schema import FamilyMember
from src.services.agent_loop import (
    PLANNING_INSTRUCTIONS,
    AgentResult,
    _is_multi_tool_run,
    build_system_prompt,
    run,
)
from src.services.bedrock_client import BedrockError, ConverseResponse, ToolCall


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_member(name: str = "Test User") -> MagicMock:
    m = MagicMock(spec=FamilyMember)
    m.id = uuid.uuid4()
    m.name = name
    m.role = "parent"
    m.is_active = True
    return m


def _text_response(text: str) -> ConverseResponse:
    """Bedrock response with text only (no tool calls)."""
    return ConverseResponse(text=text, tool_calls=[], stop_reason="end_turn")


def _tool_response(*tools: tuple[str, dict]) -> ConverseResponse:
    """Bedrock response with one or more tool calls."""
    calls = [
        ToolCall(tool_use_id=f"tu_{i}", name=name, arguments=args)
        for i, (name, args) in enumerate(tools)
    ]
    return ConverseResponse(text=None, tool_calls=calls, stop_reason="tool_use")


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


class TestBuildSystemPromptIncludesPlanning:
    """Req 1, 10.1: Planning instructions present in system prompt."""

    def test_contains_planning_heading(self, mock_db: MagicMock) -> None:
        member = _make_member()
        with patch("src.services.agent_loop._load_soul_md", return_value="אני פורטרס"):
            with patch("src.services.agent_loop._load_memories_text", return_value=""):
                prompt = build_system_prompt(mock_db, member)

        assert "חשיבה לפני פעולה" in prompt

    def test_contains_three_categories(self, mock_db: MagicMock) -> None:
        member = _make_member()
        with patch("src.services.agent_loop._load_soul_md", return_value="אני פורטרס"):
            with patch("src.services.agent_loop._load_memories_text", return_value=""):
                prompt = build_system_prompt(mock_db, member)

        assert "בקשות פשוטות" in prompt
        assert "בקשות מורכבות" in prompt
        assert "בקשות לא ברורות" in prompt

    def test_retains_existing_instructions(self, mock_db: MagicMock) -> None:
        member = _make_member()
        with patch("src.services.agent_loop._load_soul_md", return_value="אני פורטרס"):
            with patch("src.services.agent_loop._load_memories_text", return_value=""):
                prompt = build_system_prompt(mock_db, member)

        assert "הוראות לסוכן" in prompt
        assert "תמיד ענה בעברית" in prompt

    def test_contains_member_name(self, mock_db: MagicMock) -> None:
        member = _make_member(name="שגב")
        with patch("src.services.agent_loop._load_soul_md", return_value="אני פורטרס"):
            with patch("src.services.agent_loop._load_memories_text", return_value=""):
                prompt = build_system_prompt(mock_db, member)

        assert "שגב" in prompt

    def test_planning_instructions_is_static(self) -> None:
        assert isinstance(PLANNING_INSTRUCTIONS, str)
        assert len(PLANNING_INSTRUCTIONS) > 100


class TestAgentResultTelemetryDefaults:
    """Req 3, 10.2: Telemetry fields default correctly."""

    def test_defaults(self) -> None:
        result = AgentResult(response="test")
        assert result.multi_tool_run is False
        assert result.tool_calls_count == 0
        assert result.distinct_tools_count == 0

    def test_existing_fields_unchanged(self) -> None:
        result = AgentResult(response="test")
        assert result.tool_name is None
        assert result.iterations == 0
        assert result.fallback_used is False


class TestIsMultiToolRun:
    """Req 4, 10.3: _is_multi_tool_run() boundary cases."""

    def test_no_tools(self) -> None:
        assert _is_multi_tool_run(0, 0) is False

    def test_single_tool_single_call(self) -> None:
        assert _is_multi_tool_run(1, 1) is False

    def test_single_tool_two_calls(self) -> None:
        assert _is_multi_tool_run(2, 1) is False

    def test_single_tool_three_calls(self) -> None:
        # >2 total calls triggers True even with 1 distinct tool
        assert _is_multi_tool_run(3, 1) is True

    def test_two_distinct_tools(self) -> None:
        assert _is_multi_tool_run(2, 2) is True

    def test_many_distinct_tools(self) -> None:
        assert _is_multi_tool_run(5, 3) is True

    def test_tool_calls_can_exceed_iterations(self) -> None:
        """A single iteration can return multiple tool calls."""
        # 4 tool calls, 3 distinct — valid even if iterations < tool_calls_count
        assert _is_multi_tool_run(4, 3) is True


# ---------------------------------------------------------------------------
# Integration tests (mocked Bedrock)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("src.services.agent_loop.execute_tool", return_value="יצרתי משימה ✅")
@patch("src.services.agent_loop.get_tool_schemas", return_value=[])
@patch("src.services.agent_loop.load_conversation_history", return_value=[])
@patch("src.services.agent_loop.build_system_prompt", return_value="test prompt")
async def test_simple_request_single_tool(
    mock_prompt, mock_history, mock_schemas, mock_exec, mock_db
) -> None:
    """Req 10.4: Simple request produces tool_calls_count==1, multi_tool_run==False."""
    member = _make_member()

    call_count = {"i": 0}

    async def mock_converse(**kwargs):
        call_count["i"] += 1
        if call_count["i"] == 1:
            return _tool_response(("task_create", {"title": "לקנות חלב"}))
        return _text_response("יצרתי משימה: לקנות חלב ✅")

    mock_bedrock = MagicMock()
    mock_bedrock.converse = AsyncMock(side_effect=mock_converse)

    with patch("src.services.agent_loop.BedrockClient", return_value=mock_bedrock):
        result = await run(mock_db, member, "צור משימה לקנות חלב")

    assert result.tool_calls_count == 1
    assert result.distinct_tools_count == 1
    assert result.multi_tool_run is False
    assert result.iterations <= 2
    assert result.fallback_used is False


@pytest.mark.asyncio
@patch("src.services.agent_loop.execute_tool")
@patch("src.services.agent_loop.get_tool_schemas", return_value=[])
@patch("src.services.agent_loop.load_conversation_history", return_value=[])
@patch("src.services.agent_loop.build_system_prompt", return_value="test prompt")
async def test_multi_step_uses_multiple_tools(
    mock_prompt, mock_history, mock_schemas, mock_exec, mock_db
) -> None:
    """Req 10.5: Multi-step request produces distinct_tools_count>=2, multi_tool_run==True."""
    member = _make_member()

    mock_exec.side_effect = [
        "נמצאו 3 חשבוניות",
        "יצרתי משימה ✅",
    ]

    call_count = {"i": 0}

    async def mock_converse(**kwargs):
        call_count["i"] += 1
        if call_count["i"] == 1:
            return _tool_response(("document_search", {"doc_type": "חשבוניות"}))
        if call_count["i"] == 2:
            return _tool_response(("task_create", {"title": "לשלם חשבונית"}))
        return _text_response("מצאתי 3 חשבוניות ויצרתי משימה לכל אחת ✅")

    mock_bedrock = MagicMock()
    mock_bedrock.converse = AsyncMock(side_effect=mock_converse)

    with patch("src.services.agent_loop.BedrockClient", return_value=mock_bedrock):
        result = await run(mock_db, member, "מצא חשבוניות וצור משימה לכל אחת")

    assert result.tool_calls_count >= 2
    assert result.distinct_tools_count >= 2
    assert result.multi_tool_run is True
    assert result.fallback_used is False


@pytest.mark.asyncio
@patch("src.services.agent_loop.get_tool_schemas", return_value=[])
@patch("src.services.agent_loop.load_conversation_history", return_value=[])
@patch("src.services.agent_loop.build_system_prompt", return_value="test prompt")
async def test_ambiguous_request_no_tool_call(
    mock_prompt, mock_history, mock_schemas, mock_db
) -> None:
    """Req 10.6: Ambiguous request produces tool_calls_count==0, multi_tool_run==False."""
    member = _make_member()

    async def mock_converse(**kwargs):
        return _text_response("במה בדיוק לטפל? 🤔")

    mock_bedrock = MagicMock()
    mock_bedrock.converse = AsyncMock(side_effect=mock_converse)

    with patch("src.services.agent_loop.BedrockClient", return_value=mock_bedrock):
        result = await run(mock_db, member, "תטפל בזה")

    assert result.tool_calls_count == 0
    assert result.distinct_tools_count == 0
    assert result.multi_tool_run is False
    assert result.iterations == 1
    assert result.fallback_used is False


@pytest.mark.asyncio
@patch("src.services.agent_loop.execute_tool", return_value="ok")
@patch("src.services.agent_loop.get_tool_schemas", return_value=[])
@patch("src.services.agent_loop.load_conversation_history", return_value=[])
@patch("src.services.agent_loop.build_system_prompt", return_value="test prompt")
async def test_max_iterations_respected(
    mock_prompt, mock_history, mock_schemas, mock_exec, mock_db
) -> None:
    """Req 10.7: Iteration count does not exceed AGENT_MAX_TOOL_ITERATIONS."""
    member = _make_member()

    async def mock_converse(**kwargs):
        return _tool_response(("task_list", {}))

    mock_bedrock = MagicMock()
    mock_bedrock.converse = AsyncMock(side_effect=mock_converse)

    with patch("src.services.agent_loop.BedrockClient", return_value=mock_bedrock):
        with patch("src.services.agent_loop.AGENT_MAX_TOOL_ITERATIONS", 7):
            result = await run(mock_db, member, "loop forever")

    assert result.iterations == 7
    assert result.iterations <= 7


@pytest.mark.asyncio
@patch("src.services.agent_loop.get_tool_schemas", return_value=[])
@patch("src.services.agent_loop.load_conversation_history", return_value=[])
@patch("src.services.agent_loop.build_system_prompt", return_value="test prompt")
async def test_fallback_on_bedrock_error(
    mock_prompt, mock_history, mock_schemas, mock_db
) -> None:
    """Req 7.2: Bedrock error triggers fallback with telemetry fields populated."""
    member = _make_member()

    async def mock_converse(**kwargs):
        raise BedrockError("test error")

    mock_bedrock = MagicMock()
    mock_bedrock.converse = AsyncMock(side_effect=mock_converse)

    with patch("src.services.agent_loop.BedrockClient", return_value=mock_bedrock):
        result = await run(mock_db, member, "test")

    assert result.fallback_used is True
    assert result.multi_tool_run is False
    assert result.tool_calls_count == 0
    assert result.distinct_tools_count == 0
