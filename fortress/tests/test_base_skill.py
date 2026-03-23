"""Tests for base_skill.py — Command, Result, BaseSkill ABC."""

import uuid

import pytest

from src.skills.base_skill import BaseSkill, Command, Result


class TestCommand:
    def test_construction_defaults(self):
        cmd = Command(skill="task", action="create")
        assert cmd.skill == "task"
        assert cmd.action == "create"
        assert cmd.params == {}

    def test_construction_with_params(self):
        cmd = Command(skill="task", action="create", params={"title": "Buy milk"})
        assert cmd.params["title"] == "Buy milk"

    def test_params_default_is_independent(self):
        c1 = Command(skill="a", action="b")
        c2 = Command(skill="a", action="b")
        c1.params["x"] = 1
        assert "x" not in c2.params


class TestResult:
    def test_construction_minimal(self):
        r = Result(success=True, message="ok")
        assert r.success is True
        assert r.message == "ok"
        assert r.entity_type is None
        assert r.entity_id is None
        assert r.action is None
        assert r.data is None

    def test_construction_full(self):
        uid = uuid.uuid4()
        r = Result(
            success=True,
            message="done",
            entity_type="task",
            entity_id=uid,
            action="created",
            data={"key": "val"},
        )
        assert r.entity_type == "task"
        assert r.entity_id == uid
        assert r.action == "created"
        assert r.data == {"key": "val"}


class TestBaseSkillABC:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            BaseSkill()
