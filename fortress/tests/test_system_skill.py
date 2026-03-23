"""Tests for system_skill.py — cancel, confirm, help."""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from src.skills.system_skill import SystemSkill
from src.skills.base_skill import Command, Result


@pytest.fixture()
def skill():
    return SystemSkill()


@pytest.fixture()
def mock_db():
    return MagicMock()


@pytest.fixture()
def member():
    m = MagicMock()
    m.id = uuid.uuid4()
    m.name = "Test"
    return m


class TestCancel:
    @patch("src.skills.system_skill.clear_state")
    def test_cancel_clears_state(self, mock_clear, skill, mock_db, member):
        cmd = Command(skill="system", action="cancel")
        result = skill.execute(mock_db, member, cmd)
        assert result.success is True
        assert result.action == "cancel"
        mock_clear.assert_called_once_with(mock_db, member.id)


class TestConfirm:
    @patch("src.skills.system_skill.resolve_pending")
    @patch("src.skills.system_skill.get_state")
    def test_confirm_with_pending(self, mock_get_state, mock_resolve, skill, mock_db, member):
        state = MagicMock()
        state.pending_confirmation = True
        mock_get_state.return_value = state
        mock_resolve.return_value = {"type": "task.delete", "data": {"id": "123"}}

        cmd = Command(skill="system", action="confirm")
        result = skill.execute(mock_db, member, cmd)
        assert result.success is True
        assert result.action == "confirm"
        assert result.data["pending_action"] is not None

    @patch("src.skills.system_skill.get_state")
    def test_confirm_no_pending(self, mock_get_state, skill, mock_db, member):
        state = MagicMock()
        state.pending_confirmation = False
        mock_get_state.return_value = state

        cmd = Command(skill="system", action="confirm")
        result = skill.execute(mock_db, member, cmd)
        assert result.success is False
        assert "ממתינה" in result.message


class TestHelp:
    def test_help_returns_hebrew(self, skill, mock_db, member):
        """Help should return Hebrew text with 'פקודות' in it."""
        cmd = Command(skill="system", action="help")
        result = skill.execute(mock_db, member, cmd)
        assert result.success is True
        assert "פקודות" in result.message

    def test_help_lists_skills(self, skill, mock_db, member):
        """Help should list descriptions of registered skills."""
        from src.skills.registry import registry

        mock_skill = MagicMock()
        mock_skill.name = "task_test"
        mock_skill.description = "ניהול משימות"
        mock_skill.get_help.return_value = "משימות — רשימת משימות"
        registry.register(mock_skill)

        try:
            cmd = Command(skill="system", action="help")
            result = skill.execute(mock_db, member, cmd)
            assert "ניהול משימות" in result.message
        finally:
            # Clean up
            registry._skills.pop("task_test", None)


class TestVerify:
    def test_verify_always_true(self, skill, mock_db):
        result = Result(success=True, message="ok")
        assert skill.verify(mock_db, result) is True
