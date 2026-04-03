"""Tests for command_parser.py — deterministic parser."""

import re

import pytest

from src.engine.command_parser import parse_command
from src.skills.registry import SkillRegistry


@pytest.fixture()
def empty_registry():
    return SkillRegistry()


class TestMediaPriority:
    def test_media_returns_media_save(self, empty_registry):
        cmd = parse_command("כן", empty_registry, has_media=True)
        assert cmd is not None
        assert cmd.skill == "document"
        assert cmd.action == "save"

    def test_media_with_file_path(self, empty_registry):
        cmd = parse_command("", empty_registry, has_media=True, media_file_path="/tmp/photo.jpg")
        assert cmd.params["media_file_path"] == "/tmp/photo.jpg"

    def test_media_overrides_cancel_text(self, empty_registry):
        cmd = parse_command("בטל", empty_registry, has_media=True)
        assert cmd.skill == "document"


class TestCancelPatterns:
    @pytest.mark.parametrize("text", ["לא", "עזוב", "תעזוב", "בטל", "תבטל", "ביטול", "cancel"])
    def test_cancel_keywords(self, text, empty_registry):
        cmd = parse_command(text, empty_registry)
        assert cmd is not None
        assert cmd.skill == "system"
        assert cmd.action == "cancel"

    def test_cancel_case_insensitive(self, empty_registry):
        cmd = parse_command("CANCEL", empty_registry)
        assert cmd is not None
        assert cmd.skill == "system"
        assert cmd.action == "cancel"

    def test_cancel_with_whitespace(self, empty_registry):
        cmd = parse_command("  בטל  ", empty_registry)
        assert cmd is not None
        assert cmd.skill == "system"
        assert cmd.action == "cancel"


class TestConfirmPatterns:
    @pytest.mark.parametrize("text", ["כן", "yes", "אישור", "אשר", "ok", "בטח", "אוקיי", "אוקי"])
    def test_confirm_keywords(self, text, empty_registry):
        cmd = parse_command(text, empty_registry)
        assert cmd is not None
        assert cmd.skill == "system"
        assert cmd.action == "confirm"

    def test_confirm_case_insensitive(self, empty_registry):
        cmd = parse_command("YES", empty_registry)
        assert cmd is not None
        assert cmd.action == "confirm"


class TestSkillPatterns:
    def test_skill_pattern_match(self):
        from unittest.mock import MagicMock
        from src.skills.base_skill import BaseSkill

        reg = SkillRegistry()
        skill = MagicMock(spec=BaseSkill)
        skill.name = "task"
        skill.commands = [(re.compile(r"^משימות$", re.IGNORECASE), "list")]
        reg.register(skill)

        cmd = parse_command("משימות", reg)
        assert cmd is not None
        assert cmd.skill == "task"
        assert cmd.action == "list"

    def test_named_groups_extracted(self):
        from unittest.mock import MagicMock
        from src.skills.base_skill import BaseSkill

        reg = SkillRegistry()
        skill = MagicMock(spec=BaseSkill)
        skill.name = "task"
        skill.commands = [(re.compile(r"^צור משימה (?P<title>.+)$", re.IGNORECASE), "create")]
        reg.register(skill)

        cmd = parse_command("צור משימה לקנות חלב", reg)
        assert cmd is not None
        assert cmd.params["title"] == "לקנות חלב"


class TestLLMFallback:
    def test_unmatched_returns_none(self, empty_registry):
        cmd = parse_command("מה המצב?", empty_registry)
        assert cmd is None

    def test_empty_message_returns_none(self, empty_registry):
        cmd = parse_command("", empty_registry)
        assert cmd is None

    def test_whitespace_only_returns_none(self, empty_registry):
        cmd = parse_command("   ", empty_registry)
        assert cmd is None
