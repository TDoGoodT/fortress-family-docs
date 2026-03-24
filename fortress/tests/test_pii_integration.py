"""Integration tests for PII Guard — ChatSkill, memory extraction, executor audit, personality."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from src.models.schema import FamilyMember
from src.prompts.personality import TEMPLATES
from src.services.pii_guard import ReplacementRecord, strip_pii
from src.skills.base_skill import Command, Result
from src.skills.chat_skill import ChatSkill


@pytest.fixture()
def skill():
    return ChatSkill()


@pytest.fixture()
def db():
    return MagicMock(spec=Session)


@pytest.fixture()
def member():
    m = MagicMock(spec=FamilyMember)
    m.id = uuid.uuid4()
    m.name = "שגב"
    m.phone = "+972501234567"
    m.role = "parent"
    return m


# ------------------------------------------------------------------
# 9.1 — ChatSkill LLM path PII stripping
# ------------------------------------------------------------------


@pytest.mark.asyncio
@patch("src.skills.chat_skill.load_memories", return_value=[])
async def test_respond_strips_pii_before_llm(mock_memories, skill, db, member):
    """strip_pii is called on the message text and the cleaned text (with
    placeholders) is sent to the LLM, not the original PII."""
    original_msg = "ת.ז. שלי 123456789"

    captured_prompts: list[str] = []

    async def _capture_dispatch(prompt, **kwargs):
        captured_prompts.append(prompt)
        return "תודה, קיבלתי"

    with patch.object(skill, "_dispatch_llm", side_effect=_capture_dispatch):
        await skill.respond(db, member, original_msg)

    assert len(captured_prompts) == 1
    prompt_sent = captured_prompts[0]
    # The prompt must contain the placeholder, not the raw ID
    assert "[ת.ז._1]" in prompt_sent
    assert "123456789" not in prompt_sent


# ------------------------------------------------------------------
# 9.2 — ChatSkill PII restoration in response
# ------------------------------------------------------------------


@pytest.mark.asyncio
@patch("src.skills.chat_skill.load_memories", return_value=[])
async def test_respond_restores_pii_in_llm_response(mock_memories, skill, db, member):
    """When the LLM returns text containing indexed placeholders, restore_pii
    replaces them with the original PII values."""
    original_msg = "הטלפון שלי 0521234567"

    # The LLM echoes back the placeholder
    async def _echo_placeholder(prompt, **kwargs):
        return "מספר הטלפון שלך הוא [טלפון_1]"

    with patch.object(skill, "_dispatch_llm", side_effect=_echo_placeholder):
        result = await skill.respond(db, member, original_msg)

    # The final response should have the original phone number restored
    assert "0521234567" in result
    assert "[טלפון_1]" not in result


# ------------------------------------------------------------------
# 9.3 — Memory extraction PII stripping
# ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_memories_strips_pii_before_bedrock(db):
    """extract_memories_from_message calls strip_pii on the combined text
    before sending to Bedrock."""
    from src.services.memory_service import extract_memories_from_message

    bedrock = AsyncMock()
    bedrock.generate = AsyncMock(return_value="[]")

    member_id = uuid.uuid4()
    msg_in = "ת.ז. שלי 123456789"
    msg_out = "תודה"

    await extract_memories_from_message(db, member_id, msg_in, msg_out, bedrock)

    bedrock.generate.assert_called_once()
    prompt_sent = bedrock.generate.call_args.kwargs.get(
        "prompt", bedrock.generate.call_args[0][0] if bedrock.generate.call_args[0] else ""
    )
    # Prompt must contain the placeholder, not the raw ID
    assert "[ת.ז._1]" in prompt_sent
    assert "123456789" not in prompt_sent


# ------------------------------------------------------------------
# 9.4 — strip_pii failure graceful fallback
# ------------------------------------------------------------------


@pytest.mark.asyncio
@patch("src.skills.chat_skill.load_memories", return_value=[])
@patch("src.skills.chat_skill.strip_pii", side_effect=RuntimeError("boom"))
async def test_respond_fallback_when_strip_pii_fails(
    mock_strip, mock_memories, skill, db, member
):
    """When strip_pii raises, ChatSkill.respond still works using the original
    text and does not crash."""
    captured_prompts: list[str] = []

    async def _capture(prompt, **kwargs):
        captured_prompts.append(prompt)
        return "הכל בסדר"

    with patch.object(skill, "_dispatch_llm", side_effect=_capture):
        result = await skill.respond(db, member, "מה קורה?")

    # Should still return a valid response
    assert result == "הכל בסדר"
    # The original text should appear in the prompt (fallback path)
    assert "מה קורה?" in captured_prompts[0]


# ------------------------------------------------------------------
# 9.5 — Executor audit log structured details
# ------------------------------------------------------------------


class TestExecutorAuditLogDetails:
    """Verify the executor writes audit log entries with the required
    structured details fields."""

    @pytest.fixture(autouse=True)
    def _patch_registry(self):
        from src.skills.registry import SkillRegistry

        reg = SkillRegistry()
        with patch("src.engine.executor.registry", reg):
            yield reg

    @pytest.fixture()
    def mock_db(self):
        return MagicMock()

    @pytest.fixture()
    def member(self):
        m = MagicMock()
        m.id = uuid.uuid4()
        m.name = "Test"
        return m

    def _make_skill(self, name="task"):
        from src.skills.base_skill import BaseSkill

        skill = MagicMock(spec=BaseSkill)
        skill.name = name
        return skill

    @patch("src.engine.executor.update_state")
    @patch("src.engine.executor.log_action")
    def test_audit_log_has_structured_details_with_entity(
        self, mock_log, mock_state, _patch_registry, mock_db, member
    ):
        """Audit log details contain original_message, detected_intent,
        success, and pii_stripped when entity_id is present."""
        from src.engine.executor import execute

        skill = self._make_skill("task")
        uid = uuid.uuid4()
        skill.execute.return_value = Result(
            success=True, message="ok", entity_type="task",
            entity_id=uid, action="created",
        )
        skill.verify.return_value = True
        _patch_registry.register(skill)

        cmd = Command(
            skill="task", action="create",
            params={"_original_message": "צור משימה", "_pii_stripped": False},
        )
        execute(mock_db, member, cmd)

        mock_log.assert_called_once()
        details = mock_log.call_args.kwargs.get(
            "details", mock_log.call_args[1].get("details")
        )
        assert details["original_message"] == "צור משימה"
        assert details["detected_intent"] == "task.create"
        assert details["success"] is True
        assert details["pii_stripped"] is False

    @patch("src.engine.executor.update_state")
    @patch("src.engine.executor.log_action")
    def test_audit_log_written_without_entity_id(
        self, mock_log, mock_state, _patch_registry, mock_db, member
    ):
        """Audit log is written even when the result has no entity_id."""
        from src.engine.executor import execute

        skill = self._make_skill("chat")
        skill.execute.return_value = Result(
            success=True, message="שלום", entity_type=None,
            entity_id=None, action="greet",
        )
        skill.verify.return_value = True
        _patch_registry.register(skill)

        cmd = Command(
            skill="chat", action="greet",
            params={"_original_message": "שלום", "_pii_stripped": False},
        )
        execute(mock_db, member, cmd)

        mock_log.assert_called_once()
        details = mock_log.call_args.kwargs.get(
            "details", mock_log.call_args[1].get("details")
        )
        assert details["detected_intent"] == "chat.greet"
        assert details["success"] is True

    @patch("src.engine.executor.update_state")
    @patch("src.engine.executor.log_action")
    def test_audit_log_pii_stripped_appends_marker(
        self, mock_log, mock_state, _patch_registry, mock_db, member
    ):
        """When pii_stripped=True, original_message ends with '[PII removed]'."""
        from src.engine.executor import execute

        skill = self._make_skill("task")
        uid = uuid.uuid4()
        skill.execute.return_value = Result(
            success=True, message="ok", entity_type="task",
            entity_id=uid, action="created",
        )
        skill.verify.return_value = True
        _patch_registry.register(skill)

        cmd = Command(
            skill="task", action="create",
            params={
                "_original_message": "ת.ז. שלי 123456789",
                "_pii_stripped": True,
            },
        )
        execute(mock_db, member, cmd)

        mock_log.assert_called_once()
        details = mock_log.call_args.kwargs.get(
            "details", mock_log.call_args[1].get("details")
        )
        assert details["original_message"].endswith("[PII removed]")
        assert details["pii_stripped"] is True


# ------------------------------------------------------------------
# 9.6 — Personality template
# ------------------------------------------------------------------


def test_pii_detected_template_exists():
    """TEMPLATES dict has a 'pii_detected' key."""
    assert "pii_detected" in TEMPLATES


def test_pii_detected_template_is_nonempty_hebrew_with_lock():
    """The pii_detected template is a non-empty Hebrew string containing 🔒."""
    value = TEMPLATES["pii_detected"]
    assert isinstance(value, str)
    assert len(value) > 0
    assert "🔒" in value
    # Verify it contains Hebrew characters
    assert any("\u0590" <= ch <= "\u05FF" for ch in value)
