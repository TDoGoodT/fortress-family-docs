"""Unit tests for DeploySkill — exact trigger, role check, listener forwarding."""

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
    m.is_admin = role in ("parent", "admin")
    return m


class TestPermissions:
    def test_child_cannot_deploy_app(self, skill, mock_db):
        result = skill.execute(mock_db, _member("child"), Command(skill="deploy", action="deploy_app"))
        assert result.success is False
        assert "מנהל" in result.message or "הורים" in result.message

    def test_child_cannot_deploy_db(self, skill, mock_db):
        result = skill.execute(mock_db, _member("child"), Command(skill="deploy", action="deploy_db"))
        assert result.success is False

    def test_child_cannot_deploy_all(self, skill, mock_db):
        result = skill.execute(mock_db, _member("child"), Command(skill="deploy", action="deploy_all"))
        assert result.success is False

    def test_child_cannot_restart(self, skill, mock_db):
        result = skill.execute(mock_db, _member("child"), Command(skill="deploy", action="restart"))
        assert result.success is False

    def test_child_cannot_status(self, skill, mock_db):
        result = skill.execute(mock_db, _member("child"), Command(skill="deploy", action="status"))
        assert result.success is False


class TestSecretConfig:
    def test_empty_secret_blocks_all(self, skill, mock_db):
        with patch("src.skills.deploy_skill.config") as cfg:
            cfg.DEPLOY_SECRET = ""
            for action in ("deploy_app", "deploy_db", "deploy_all", "restart", "status"):
                result = skill.execute(mock_db, _member("parent"), Command(skill="deploy", action=action))
                assert result.success is False
                assert result.message == TEMPLATES["deploy_not_configured"]


class TestExactTriggers:
    """Exact trigger phrases must match — no fuzzy, no partial."""

    @pytest.mark.parametrize("text,action", [
        ("פורטרס תתחדש APP", "deploy_app"),
        ("פורטרס תתחדש app", "deploy_app"),
        ("פורטרס תתחדש DB", "deploy_db"),
        ("פורטרס תתחדש db", "deploy_db"),
        ("פורטרס תתחדש ALL", "deploy_all"),
        ("פורטרס תתחדש all", "deploy_all"),
        ("פורטרס תתחדש", "deploy_all"),
        ("פורטרס הפעל מחדש", "restart"),
        ("restart", "restart"),
        ("פורטרס סטטוס", "status"),
        ("status", "status"),
    ])
    def test_exact_match(self, skill, text, action):
        matched = any(p.match(text) for p, a in skill.commands if a == action)
        assert matched, f"'{text}' should match action '{action}'"

    @pytest.mark.parametrize("text", [
        "עדכן מערכת",
        "עדכן מערכת עכשיו",
        "deploy",
        "סטטוס מערכת",
        "פורטרס שדרג מערכת בבקשה",
        " פורטרס שדרג מערכת",
        "פורטרס תתחדש SOMETHING",
    ])
    def test_no_fuzzy_match(self, skill, text):
        matched = any(p.match(text) for p, _ in skill.commands)
        assert not matched, f"'{text}' should NOT match any trigger"


class TestListenerForwarding:
    def test_sends_token_and_action(self, skill, mock_db):
        with patch("src.skills.deploy_skill.config") as cfg, \
             patch("src.skills.deploy_skill.httpx") as mock_httpx:
            cfg.DEPLOY_SECRET = "my-secret"
            cfg.DEPLOY_LISTENER_URL = "http://localhost:9111"
            mock_resp = MagicMock()
            mock_resp.status_code = 202
            mock_resp.json.return_value = {"status": "accepted"}
            mock_httpx.post.return_value = mock_resp

            skill.execute(mock_db, _member("parent"), Command(skill="deploy", action="deploy_all"))

            payload = mock_httpx.post.call_args[1]["json"]
            assert payload["token"] == "my-secret"
            assert payload["action"] == "deploy_all"

    def test_sends_sender_identity(self, skill, mock_db):
        with patch("src.skills.deploy_skill.config") as cfg, \
             patch("src.skills.deploy_skill.httpx") as mock_httpx:
            cfg.DEPLOY_SECRET = "secret"
            cfg.DEPLOY_LISTENER_URL = "http://localhost:9111"
            mock_resp = MagicMock()
            mock_resp.status_code = 202
            mock_resp.json.return_value = {"status": "accepted"}
            mock_httpx.post.return_value = mock_resp

            skill.execute(mock_db, _member("parent", name="שגב"), Command(skill="deploy", action="deploy_all"))

            payload = mock_httpx.post.call_args[1]["json"]
            assert payload["sender"] == "שגב"

    def test_status_returns_output(self, skill, mock_db):
        with patch("src.skills.deploy_skill.config") as cfg, \
             patch("src.skills.deploy_skill.httpx") as mock_httpx:
            cfg.DEPLOY_SECRET = "secret"
            cfg.DEPLOY_LISTENER_URL = "http://localhost:9111"
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"status": "ok", "output": "all running"}
            mock_httpx.post.return_value = mock_resp

            result = skill.execute(mock_db, _member("parent"), Command(skill="deploy", action="status"))
            assert result.success is True
            assert "all running" in result.message

    def test_status_handles_non_json_response(self, skill, mock_db):
        with patch("src.skills.deploy_skill.config") as cfg, \
             patch("src.skills.deploy_skill.httpx") as mock_httpx:
            cfg.DEPLOY_SECRET = "secret"
            cfg.DEPLOY_LISTENER_URL = "http://localhost:9111"
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.side_effect = ValueError("not json")
            mock_resp.text = "plain status line"
            mock_httpx.post.return_value = mock_resp

            result = skill.execute(mock_db, _member("parent"), Command(skill="deploy", action="status"))
            assert result.success is True
            assert "plain status line" in result.message

    def test_status_partial_has_warning_lines(self, skill, mock_db):
        with patch("src.skills.deploy_skill.config") as cfg, \
             patch("src.skills.deploy_skill.httpx") as mock_httpx:
            cfg.DEPLOY_SECRET = "secret"
            cfg.DEPLOY_LISTENER_URL = "http://localhost:9111"
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "status": "partial",
                "output": "base status",
                "errors": ["db timeout", "waha missing"],
            }
            mock_httpx.post.return_value = mock_resp

            result = skill.execute(mock_db, _member("parent"), Command(skill="deploy", action="status"))
            assert result.success is True
            assert "base status" in result.message
            assert "בדיקות חלקיות נכשלו" in result.message
            assert "db timeout" in result.message


class TestErrorHandling:
    def test_429_rate_limited(self, skill, mock_db):
        with patch("src.skills.deploy_skill.config") as cfg, \
             patch("src.skills.deploy_skill.httpx") as mock_httpx:
            cfg.DEPLOY_SECRET = "secret"
            cfg.DEPLOY_LISTENER_URL = "http://localhost:9111"
            mock_resp = MagicMock()
            mock_resp.status_code = 429
            mock_httpx.post.return_value = mock_resp

            result = skill.execute(mock_db, _member("parent"), Command(skill="deploy", action="deploy_all"))
            assert result.success is False
            assert result.message == TEMPLATES["deploy_rate_limited"]

    def test_connection_error(self, skill, mock_db):
        with patch("src.skills.deploy_skill.config") as cfg, \
             patch("src.skills.deploy_skill.httpx") as mock_httpx:
            cfg.DEPLOY_SECRET = "secret"
            cfg.DEPLOY_LISTENER_URL = "http://localhost:9111"
            mock_httpx.post.side_effect = httpx.ConnectError("refused")
            mock_httpx.ConnectError = httpx.ConnectError

            result = skill.execute(mock_db, _member("parent"), Command(skill="deploy", action="deploy_all"))
            assert result.success is False
            assert "נכשל" in result.message

    def test_timeout_error(self, skill, mock_db):
        with patch("src.skills.deploy_skill.config") as cfg, \
             patch("src.skills.deploy_skill.httpx") as mock_httpx:
            cfg.DEPLOY_SECRET = "secret"
            cfg.DEPLOY_LISTENER_URL = "http://localhost:9111"
            mock_httpx.post.side_effect = httpx.ReadTimeout("timed out")
            mock_httpx.ConnectError = httpx.ConnectError
            mock_httpx.TimeoutException = httpx.TimeoutException
            mock_httpx.HTTPError = httpx.HTTPError

            result = skill.execute(mock_db, _member("parent"), Command(skill="deploy", action="status"))
            assert result.success is False
            assert "לקחה יותר מדי זמן" in result.message


class TestTemplatesExist:
    @pytest.mark.parametrize("key", [
        "deploy_started", "deploy_failed", "deploy_status",
        "deploy_restarted", "deploy_not_configured", "deploy_rate_limited",
        "deploy_app_started", "deploy_app_success",
        "deploy_db_started", "deploy_db_success",
        "deploy_all_started", "deploy_all_success",
    ])
    def test_template_exists(self, key):
        assert key in TEMPLATES


class TestSkillMetadata:
    def test_name(self, skill):
        assert skill.name == "deploy"

    def test_commands_count(self, skill):
        assert len(skill.commands) == 6

    def test_help_mentions_exact_phrases(self, skill):
        help_text = skill.get_help()
        assert "פורטרס תתחדש" in help_text
        assert "פורטרס הפעל מחדש" in help_text
        assert "פורטרס סטטוס" in help_text
        assert "APP" in help_text
        assert "DB" in help_text
