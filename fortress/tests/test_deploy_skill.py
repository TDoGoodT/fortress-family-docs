"""Unit tests for DeploySkill — role check, secret check, listener forwarding."""

import uuid
from unittest.mock import MagicMock, patch

import httpx
import pytest
from sqlalchemy.orm import Session

from src.models.schema import FamilyMember
from src.prompts.personality import TEMPLATES
from src.skills.base_skill import Command
from src.skills.deploy_skill import DeploySkill


@pytest.fixture()
def skill():
    return DeploySkill()


@pytest.fixture()
def mock_db():
    return MagicMock(spec=Session)


def _member(role: str = "parent", name: str = "אבא") -> MagicMock:
    m = MagicMock(spec=FamilyMember)
    m.id = uuid.uuid4()
    m.name = name
    m.phone = "+972501234567"
    m.role = role
    m.is_active = True
    return m


class TestPermissions:
    """R5: Only parent role can trigger deploy actions."""

    def test_parent_can_deploy(self, skill, mock_db):
        with patch("src.skills.deploy_skill.config") as cfg, \
             patch("src.skills.deploy_skill.httpx") as mock_httpx:
            cfg.DEPLOY_SECRET = "test-secret-123"
            cfg.DEPLOY_LISTENER_URL = "http://localhost:9111"
            mock_resp = MagicMock()
            mock_resp.status_code = 202
            mock_resp.json.return_value = {"status": "accepted"}
            mock_httpx.post.return_value = mock_resp

            cmd = Command(skill="deploy", action="deploy")
            result = skill.execute(mock_db, _member("parent"), cmd)
            assert result.success is True

    def test_child_cannot_deploy(self, skill, mock_db):
        cmd = Command(skill="deploy", action="deploy")
        result = skill.execute(mock_db, _member("child"), cmd)
        assert result.success is False
        assert "רק הורים" in result.message

    def test_child_cannot_restart(self, skill, mock_db):
        cmd = Command(skill="deploy", action="restart")
        result = skill.execute(mock_db, _member("child"), cmd)
        assert result.success is False
        assert "רק הורים" in result.message

    def test_child_cannot_status(self, skill, mock_db):
        cmd = Command(skill="deploy", action="status")
        result = skill.execute(mock_db, _member("child"), cmd)
        assert result.success is False
        assert "רק הורים" in result.message


class TestSecretConfig:
    """R1: Empty DEPLOY_SECRET blocks all deploy actions."""

    def test_empty_secret_returns_not_configured(self, skill, mock_db):
        with patch("src.skills.deploy_skill.config") as cfg:
            cfg.DEPLOY_SECRET = ""
            cmd = Command(skill="deploy", action="deploy")
            result = skill.execute(mock_db, _member("parent"), cmd)
            assert result.success is False
            assert result.message == TEMPLATES["deploy_not_configured"]

    def test_empty_secret_blocks_restart(self, skill, mock_db):
        with patch("src.skills.deploy_skill.config") as cfg:
            cfg.DEPLOY_SECRET = ""
            cmd = Command(skill="deploy", action="restart")
            result = skill.execute(mock_db, _member("parent"), cmd)
            assert result.success is False
            assert result.message == TEMPLATES["deploy_not_configured"]

    def test_empty_secret_blocks_status(self, skill, mock_db):
        with patch("src.skills.deploy_skill.config") as cfg:
            cfg.DEPLOY_SECRET = ""
            cmd = Command(skill="deploy", action="status")
            result = skill.execute(mock_db, _member("parent"), cmd)
            assert result.success is False
            assert result.message == TEMPLATES["deploy_not_configured"]


class TestListenerForwarding:
    """R1.6, R5.2: Correct token and action sent to listener."""

    def test_sends_correct_token(self, skill, mock_db):
        with patch("src.skills.deploy_skill.config") as cfg, \
             patch("src.skills.deploy_skill.httpx") as mock_httpx:
            cfg.DEPLOY_SECRET = "my-secret-token"
            cfg.DEPLOY_LISTENER_URL = "http://localhost:9111"
            mock_resp = MagicMock()
            mock_resp.status_code = 202
            mock_resp.json.return_value = {"status": "accepted"}
            mock_httpx.post.return_value = mock_resp

            cmd = Command(skill="deploy", action="deploy")
            skill.execute(mock_db, _member("parent"), cmd)

            call_args = mock_httpx.post.call_args
            assert call_args[1]["json"]["token"] == "my-secret-token"
            assert call_args[1]["json"]["action"] == "deploy"

    def test_sends_correct_action_restart(self, skill, mock_db):
        with patch("src.skills.deploy_skill.config") as cfg, \
             patch("src.skills.deploy_skill.httpx") as mock_httpx:
            cfg.DEPLOY_SECRET = "secret"
            cfg.DEPLOY_LISTENER_URL = "http://localhost:9111"
            mock_resp = MagicMock()
            mock_resp.status_code = 202
            mock_resp.json.return_value = {"status": "accepted"}
            mock_httpx.post.return_value = mock_resp

            cmd = Command(skill="deploy", action="restart")
            skill.execute(mock_db, _member("parent"), cmd)

            call_args = mock_httpx.post.call_args
            assert call_args[1]["json"]["action"] == "restart"

    def test_status_returns_output(self, skill, mock_db):
        with patch("src.skills.deploy_skill.config") as cfg, \
             patch("src.skills.deploy_skill.httpx") as mock_httpx:
            cfg.DEPLOY_SECRET = "secret"
            cfg.DEPLOY_LISTENER_URL = "http://localhost:9111"
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"status": "ok", "output": "all running"}
            mock_httpx.post.return_value = mock_resp

            cmd = Command(skill="deploy", action="status")
            result = skill.execute(mock_db, _member("parent"), cmd)
            assert result.success is True
            assert "all running" in result.message


class TestErrorHandling:
    """Error responses from listener are handled correctly."""

    def test_429_returns_rate_limited(self, skill, mock_db):
        with patch("src.skills.deploy_skill.config") as cfg, \
             patch("src.skills.deploy_skill.httpx") as mock_httpx:
            cfg.DEPLOY_SECRET = "secret"
            cfg.DEPLOY_LISTENER_URL = "http://localhost:9111"
            mock_resp = MagicMock()
            mock_resp.status_code = 429
            mock_httpx.post.return_value = mock_resp

            cmd = Command(skill="deploy", action="deploy")
            result = skill.execute(mock_db, _member("parent"), cmd)
            assert result.success is False
            assert result.message == TEMPLATES["deploy_rate_limited"]

    def test_403_returns_failed(self, skill, mock_db):
        with patch("src.skills.deploy_skill.config") as cfg, \
             patch("src.skills.deploy_skill.httpx") as mock_httpx:
            cfg.DEPLOY_SECRET = "secret"
            cfg.DEPLOY_LISTENER_URL = "http://localhost:9111"
            mock_resp = MagicMock()
            mock_resp.status_code = 403
            mock_httpx.post.return_value = mock_resp

            cmd = Command(skill="deploy", action="deploy")
            result = skill.execute(mock_db, _member("parent"), cmd)
            assert result.success is False
            assert "נכשל" in result.message

    def test_connection_error_returns_failed(self, skill, mock_db):
        with patch("src.skills.deploy_skill.config") as cfg, \
             patch("src.skills.deploy_skill.httpx") as mock_httpx:
            cfg.DEPLOY_SECRET = "secret"
            cfg.DEPLOY_LISTENER_URL = "http://localhost:9111"
            mock_httpx.post.side_effect = httpx.ConnectError("refused")
            mock_httpx.ConnectError = httpx.ConnectError

            cmd = Command(skill="deploy", action="deploy")
            result = skill.execute(mock_db, _member("parent"), cmd)
            assert result.success is False
            assert "נכשל" in result.message


class TestTemplatesExist:
    """All deploy templates must exist in TEMPLATES dict."""

    @pytest.mark.parametrize("key", [
        "deploy_started",
        "deploy_success",
        "deploy_failed",
        "deploy_status",
        "deploy_restarted",
        "deploy_not_configured",
        "deploy_rate_limited",
    ])
    def test_template_exists(self, key):
        assert key in TEMPLATES
        assert len(TEMPLATES[key]) > 0


class TestSkillMetadata:
    """Skill name, description, commands, and help are correct."""

    def test_name(self, skill):
        assert skill.name == "deploy"

    def test_description_hebrew(self, skill):
        assert "עדכון" in skill.description

    def test_commands_count(self, skill):
        assert len(skill.commands) == 3

    def test_help_text(self, skill):
        help_text = skill.get_help()
        assert "עדכן מערכת" in help_text
        assert "ריסטארט" in help_text
        assert "סטטוס" in help_text
