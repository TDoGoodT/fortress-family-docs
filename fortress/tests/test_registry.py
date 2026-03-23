"""Tests for registry.py — SkillRegistry."""

import re
from unittest.mock import MagicMock

from src.skills.base_skill import BaseSkill
from src.skills.registry import SkillRegistry


def _make_skill(name="test", description="desc", commands=None):
    skill = MagicMock(spec=BaseSkill)
    skill.name = name
    skill.description = description
    skill.commands = commands or []
    return skill


class TestSkillRegistry:
    def test_register_and_get(self):
        reg = SkillRegistry()
        skill = _make_skill("task")
        reg.register(skill)
        assert reg.get("task") is skill

    def test_get_unknown_returns_none(self):
        reg = SkillRegistry()
        assert reg.get("nonexistent") is None

    def test_all_commands(self):
        reg = SkillRegistry()
        p1 = re.compile(r"^a$")
        p2 = re.compile(r"^b$")
        s1 = _make_skill("s1", commands=[(p1, "act1")])
        s2 = _make_skill("s2", commands=[(p2, "act2")])
        reg.register(s1)
        reg.register(s2)
        cmds = reg.all_commands()
        assert len(cmds) == 2
        assert cmds[0] == (p1, "act1", s1)
        assert cmds[1] == (p2, "act2", s2)

    def test_list_skills(self):
        reg = SkillRegistry()
        s1 = _make_skill("a")
        s2 = _make_skill("b")
        reg.register(s1)
        reg.register(s2)
        skills = reg.list_skills()
        assert len(skills) == 2
        assert s1 in skills
        assert s2 in skills

    def test_register_overwrites_same_name(self):
        reg = SkillRegistry()
        s1 = _make_skill("x")
        s2 = _make_skill("x")
        reg.register(s1)
        reg.register(s2)
        assert reg.get("x") is s2
        assert len(reg.list_skills()) == 1
