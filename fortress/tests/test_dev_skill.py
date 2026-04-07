"""Unit tests for DevSkill — admin gate, index action, query action."""

import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from sqlalchemy.orm import Session

from src.models.schema import FamilyMember
from src.skills.base_skill import Command
from src.skills.dev_skill import DevSkill


@pytest.fixture()
def skill():
    return DevSkill()


@pytest.fixture()
def mock_db():
    return MagicMock(spec=Session)


def _member(is_admin: bool = True, name: str = "Admin") -> MagicMock:
    m = MagicMock(spec=FamilyMember)
    m.id = uuid.uuid4()
    m.name = name
    m.phone = "+972501234567"
    m.role = "parent" if is_admin else "child"
    m.is_active = True
    m.is_admin = is_admin
    return m


class TestAdminGate:
    """Non-admin users must always get permission denied."""

    def test_non_admin_index_denied(self, skill, mock_db):
        result = skill.execute(
            mock_db, _member(is_admin=False), Command(skill="dev", action="index")
        )
        assert result.success is False
        assert "הרשאה" in result.message

    def test_non_admin_query_denied(self, skill, mock_db):
        result = skill.execute(
            mock_db,
            _member(is_admin=False),
            Command(skill="dev", action="query", params={"question": "what skills?"}),
        )
        assert result.success is False
        assert "הרשאה" in result.message

    def test_non_admin_plan_denied(self, skill, mock_db):
        result = skill.execute(
            mock_db,
            _member(is_admin=False),
            Command(skill="dev", action="plan", params={"feature_request": "add budget"}),
        )
        assert result.success is False
        assert "הרשאה" in result.message

    def test_permission_denied_no_file_paths(self, skill, mock_db):
        """Permission denied message must not leak internal file paths."""
        result = skill.execute(
            mock_db, _member(is_admin=False), Command(skill="dev", action="index")
        )
        assert "fortress/" not in result.message
        assert "src/" not in result.message
        assert ".py" not in result.message

    def test_admin_can_proceed(self, skill, mock_db):
        """Admin user should not get permission denied (may fail for other reasons)."""
        with patch("src.skills.dev_skill.build_index") as mock_build:
            mock_build.return_value = {
                "version": 1,
                "indexed_at": "2025-01-01T00:00:00+00:00",
                "layers": {
                    "modules": [{"file_path": "test.py"}],
                    "skills": [],
                    "tools": [],
                    "services": [],
                    "models": [],
                    "migrations": [],
                },
            }
            result = skill.execute(
                mock_db, _member(is_admin=True), Command(skill="dev", action="index")
            )
            assert result.success is True


class TestIndexAction:
    """Index action should call build_index and return a summary."""

    def test_index_returns_summary(self, skill, mock_db):
        fake_index = {
            "version": 1,
            "indexed_at": "2025-01-01T00:00:00+00:00",
            "layers": {
                "modules": [{"file_path": "a.py"}, {"file_path": "b.py"}],
                "skills": [{"name": "chat"}],
                "tools": [{"tool_name": "task_create"}, {"tool_name": "task_list"}],
                "services": [{"file_path": "svc.py"}],
                "models": [{"class_name": "Task"}],
                "migrations": [{"filename": "001.sql"}],
            },
        }
        with patch("src.skills.dev_skill.build_index", return_value=fake_index):
            result = skill.execute(
                mock_db, _member(), Command(skill="dev", action="index")
            )
        assert result.success is True
        assert "2" in result.message  # 2 modules
        assert "1" in result.message  # 1 skill
        assert result.data["modules"] == 2
        assert result.data["skills"] == 1
        assert result.data["tools"] == 2

    def test_index_calls_build_with_force(self, skill, mock_db):
        with patch("src.skills.dev_skill.build_index") as mock_build:
            mock_build.return_value = {
                "layers": {"modules": [], "skills": [], "tools": [],
                           "services": [], "models": [], "migrations": []}
            }
            skill.execute(mock_db, _member(), Command(skill="dev", action="index"))
            mock_build.assert_called_once_with(force=True)

    def test_index_logs_audit(self, skill, mock_db):
        with patch("src.skills.dev_skill.build_index") as mock_build, \
             patch("src.skills.dev_skill.audit") as mock_audit:
            mock_build.return_value = {
                "layers": {"modules": [], "skills": [], "tools": [],
                           "services": [], "models": [], "migrations": []}
            }
            member = _member()
            skill.execute(mock_db, member, Command(skill="dev", action="index"))
            mock_audit.log_action.assert_called_once()
            call_kwargs = mock_audit.log_action.call_args
            assert call_kwargs[1]["resource_type"] == "dev" or call_kwargs[0][3] == "dev"

    def test_index_failure_returns_error(self, skill, mock_db):
        with patch("src.skills.dev_skill.build_index", side_effect=RuntimeError("disk full")):
            result = skill.execute(
                mock_db, _member(), Command(skill="dev", action="index")
            )
        assert result.success is False
        assert "נכשלה" in result.message


class TestQueryAction:
    """Query action should search index and call LLM."""

    def test_query_empty_question_rejected(self, skill, mock_db):
        result = skill.execute(
            mock_db,
            _member(),
            Command(skill="dev", action="query", params={"question": ""}, raw_text=""),
        )
        assert result.success is False
        assert "שאלה" in result.message

    def test_query_with_mocked_llm(self, skill, mock_db):
        mock_response = MagicMock()
        mock_response.text = "ChatSkill handles greetings [indexed_fact]"

        with patch("src.skills.dev_skill.is_stale", return_value=False), \
             patch("src.skills.dev_skill.retrieve_relevant_context", return_value=[
                 {"layer": "skill", "name": "chat", "description": "שיחה חופשית"}
             ]), \
             patch("src.skills.dev_skill.audit"), \
             patch.object(skill, "_query_llm", return_value="ChatSkill handles greetings [indexed_fact]"):
            result = skill.execute(
                mock_db,
                _member(),
                Command(skill="dev", action="query", params={"question": "what is chat skill?"}),
            )
        assert result.success is True
        assert "ChatSkill" in result.message

    def test_query_triggers_reindex_when_stale(self, skill, mock_db):
        with patch("src.skills.dev_skill.is_stale", return_value=True), \
             patch("src.skills.dev_skill.build_index") as mock_build, \
             patch("src.skills.dev_skill.retrieve_relevant_context", return_value=[]), \
             patch("src.skills.dev_skill.load_index", return_value={"layers": {}}), \
             patch("src.skills.dev_skill.audit"), \
             patch.object(skill, "_query_llm", return_value="answer"):
            skill.execute(
                mock_db,
                _member(),
                Command(skill="dev", action="query", params={"question": "test"}),
            )
            mock_build.assert_called_once()

    def test_query_no_index_returns_error(self, skill, mock_db):
        with patch("src.skills.dev_skill.is_stale", return_value=False), \
             patch("src.skills.dev_skill.retrieve_relevant_context", return_value=[]), \
             patch("src.skills.dev_skill.load_index", return_value=None):
            result = skill.execute(
                mock_db,
                _member(),
                Command(skill="dev", action="query", params={"question": "test"}),
            )
        assert result.success is False
        assert "אינדקס" in result.message


class TestSkillMetadata:
    def test_name(self, skill):
        assert skill.name == "dev"

    def test_description_not_empty(self, skill):
        assert len(skill.description) > 0

    def test_commands_count(self, skill):
        assert len(skill.commands) == 4

    def test_help_mentions_actions(self, skill):
        help_text = skill.get_help()
        assert "index" in help_text
        assert "query" in help_text
        assert "plan" in help_text

    def test_unknown_action_returns_error(self, skill, mock_db):
        result = skill.execute(
            mock_db, _member(), Command(skill="dev", action="unknown_action")
        )
        assert result.success is False
