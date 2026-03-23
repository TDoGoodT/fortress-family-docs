"""Tests for executor.py — dispatch → verify → state → audit."""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from src.skills.base_skill import BaseSkill, Command, Result
from src.skills.registry import SkillRegistry


@pytest.fixture(autouse=True)
def _patch_registry():
    """Patch the global registry used by executor."""
    reg = SkillRegistry()
    with patch("src.engine.executor.registry", reg):
        yield reg


@pytest.fixture()
def mock_db():
    db = MagicMock()
    return db


@pytest.fixture()
def member():
    m = MagicMock()
    m.id = uuid.uuid4()
    m.name = "Test"
    return m


def _make_skill(name="test"):
    skill = MagicMock(spec=BaseSkill)
    skill.name = name
    return skill


class TestExecuteSuccess:
    def test_calls_skill_execute(self, _patch_registry, mock_db, member):
        from src.engine.executor import execute

        skill = _make_skill("task")
        result = Result(success=True, message="ok", entity_type="task", entity_id=uuid.uuid4(), action="created")
        skill.execute.return_value = result
        skill.verify.return_value = True
        _patch_registry.register(skill)

        cmd = Command(skill="task", action="create")
        with patch("src.engine.executor.update_state"), patch("src.engine.executor.log_action"):
            out = execute(mock_db, member, cmd)

        skill.execute.assert_called_once_with(mock_db, member, cmd)
        assert out.success is True

    @patch("src.engine.executor.update_state")
    @patch("src.engine.executor.log_action")
    def test_state_updated_on_success(self, mock_audit, mock_state, _patch_registry, mock_db, member):
        from src.engine.executor import execute

        skill = _make_skill("task")
        uid = uuid.uuid4()
        skill.execute.return_value = Result(success=True, message="ok", entity_type="task", entity_id=uid, action="created")
        skill.verify.return_value = True
        _patch_registry.register(skill)

        execute(mock_db, member, Command(skill="task", action="create"))
        mock_state.assert_called_once()

    @patch("src.engine.executor.update_state")
    @patch("src.engine.executor.log_action")
    def test_audit_logged_on_success_with_entity(self, mock_audit, mock_state, _patch_registry, mock_db, member):
        from src.engine.executor import execute

        skill = _make_skill("task")
        uid = uuid.uuid4()
        skill.execute.return_value = Result(success=True, message="ok", entity_type="task", entity_id=uid, action="created")
        skill.verify.return_value = True
        _patch_registry.register(skill)

        execute(mock_db, member, Command(skill="task", action="create"))
        mock_audit.assert_called_once()


class TestVerificationFailure:
    @patch("src.engine.executor.update_state")
    @patch("src.engine.executor.log_action")
    def test_verify_false_returns_failure(self, mock_audit, mock_state, _patch_registry, mock_db, member):
        from src.engine.executor import execute

        skill = _make_skill("task")
        uid = uuid.uuid4()
        skill.execute.return_value = Result(success=True, message="ok", entity_type="task", entity_id=uid, action="created")
        skill.verify.return_value = False
        _patch_registry.register(skill)

        out = execute(mock_db, member, Command(skill="task", action="create"))
        assert out.success is False
        assert "השתבש" in out.message or "נכשלה" in out.message


class TestExceptionHandling:
    def test_skill_exception_returns_error(self, _patch_registry, mock_db, member):
        from src.engine.executor import execute

        skill = _make_skill("task")
        skill.execute.side_effect = RuntimeError("boom")
        _patch_registry.register(skill)

        out = execute(mock_db, member, Command(skill="task", action="create"))
        assert out.success is False
        mock_db.rollback.assert_called_once()

    def test_unknown_skill_returns_error(self, _patch_registry, mock_db, member):
        from src.engine.executor import execute

        out = execute(mock_db, member, Command(skill="nonexistent", action="x"))
        assert out.success is False


class TestSystemCommands:
    @patch("src.engine.executor.clear_state")
    def test_cancel_clears_state(self, mock_clear, _patch_registry, mock_db, member):
        from src.engine.executor import execute

        skill = _make_skill("system")
        skill.execute.return_value = Result(success=True, message="בסדר", action="cancel")
        _patch_registry.register(skill)

        out = execute(mock_db, member, Command(skill="system", action="cancel"))
        assert out.success is True
        mock_clear.assert_called_once_with(mock_db, member.id)

    @patch("src.engine.executor.resolve_pending")
    def test_confirm_with_pending(self, mock_resolve, _patch_registry, mock_db, member):
        from src.engine.executor import execute

        # Set up system skill for confirm
        system_skill = _make_skill("system")
        system_skill.execute.return_value = Result(success=True, message="", action="confirm")
        _patch_registry.register(system_skill)

        # Set up target skill
        target_skill = _make_skill("task")
        target_skill.execute.return_value = Result(success=True, message="done", action="deleted")
        target_skill.verify.return_value = True
        _patch_registry.register(target_skill)

        mock_resolve.return_value = {"type": "task.delete", "data": {"id": "123"}}

        with patch("src.engine.executor.update_state"), patch("src.engine.executor.log_action"):
            out = execute(mock_db, member, Command(skill="system", action="confirm"))

        assert out.success is True

    @patch("src.engine.executor.resolve_pending")
    def test_confirm_no_pending(self, mock_resolve, _patch_registry, mock_db, member):
        from src.engine.executor import execute

        system_skill = _make_skill("system")
        _patch_registry.register(system_skill)

        mock_resolve.return_value = None

        out = execute(mock_db, member, Command(skill="system", action="confirm"))
        assert out.success is False
        assert "ממתינה" in out.message
