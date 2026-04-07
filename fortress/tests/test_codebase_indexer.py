"""Tests for fortress.src.services.codebase_indexer — Task 1.1."""

from __future__ import annotations

import ast
import json
import os
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.services.codebase_indexer import (
    _build_module_regex_map,
    _extract_classes,
    _extract_columns,
    _extract_commands_from_property,
    _extract_config_keys,
    _extract_functions,
    _extract_input_schema_summary,
    _extract_internal_imports,
    _extract_migration_description,
    _extract_property_string,
    _extract_relationships,
    _extract_routers,
    _extract_scheduler_jobs,
    _extract_tablename,
    _extract_tool_map,
    _extract_tool_schemas,
    _scan_infrastructure,
    _scan_migrations,
    _scan_models,
    _scan_python_modules,
    _scan_services,
    _scan_skills,
    _scan_tools,
    build_index,
    ensure_fresh,
    is_stale,
    load_index,
)


# ---------------------------------------------------------------------------
# AST helper tests
# ---------------------------------------------------------------------------

def _parse(code: str) -> ast.Module:
    return ast.parse(textwrap.dedent(code))


class TestExtractClasses:
    def test_simple_class(self):
        tree = _parse("""
            class Foo:
                def bar(self): ...
                def baz(self): ...
        """)
        classes = _extract_classes(tree)
        assert len(classes) == 1
        assert classes[0]["name"] == "Foo"
        assert classes[0]["bases"] == []
        assert set(classes[0]["methods"]) == {"bar", "baz"}
        assert classes[0]["is_dataclass"] is False

    def test_class_with_bases(self):
        tree = _parse("""
            class Child(Parent, Mixin):
                pass
        """)
        classes = _extract_classes(tree)
        assert classes[0]["bases"] == ["Parent", "Mixin"]

    def test_dataclass_detected(self):
        tree = _parse("""
            from dataclasses import dataclass
            @dataclass
            class Point:
                x: int
                y: int
        """)
        classes = _extract_classes(tree)
        assert classes[0]["is_dataclass"] is True

    def test_no_classes(self):
        tree = _parse("x = 1")
        assert _extract_classes(tree) == []



class TestExtractFunctions:
    def test_top_level_functions(self):
        tree = _parse("""
            def foo(): ...
            async def bar(): ...
            class C:
                def method(self): ...
        """)
        funcs = _extract_functions(tree)
        assert funcs == ["foo", "bar"]

    def test_no_functions(self):
        tree = _parse("x = 1")
        assert _extract_functions(tree) == []


class TestExtractInternalImports:
    def test_from_src_import(self):
        tree = _parse("""
            from src.services.foo import bar
            from src.config import DB_URL
        """)
        imports = _extract_internal_imports(tree)
        assert "src.services.foo" in imports
        assert "src.config" in imports

    def test_fortress_prefix_normalised(self):
        tree = _parse("from fortress.src.models.schema import Base")
        imports = _extract_internal_imports(tree)
        assert imports == ["src.models.schema"]

    def test_external_imports_ignored(self):
        tree = _parse("""
            import os
            from pathlib import Path
            from sqlalchemy.orm import Session
        """)
        assert _extract_internal_imports(tree) == []


# ---------------------------------------------------------------------------
# Module scanner tests (using a temp directory)
# ---------------------------------------------------------------------------

class TestScanPythonModules:
    def test_scans_valid_file(self, tmp_path: Path):
        py = tmp_path / "hello.py"
        py.write_text("def greet(): ...\n")
        modules = _scan_python_modules(tmp_path)
        assert len(modules) == 1
        assert modules[0]["functions"] == ["greet"]
        assert "mtime" in modules[0]

    def test_skips_syntax_error(self, tmp_path: Path):
        bad = tmp_path / "bad.py"
        bad.write_text("def (broken\n")
        good = tmp_path / "good.py"
        good.write_text("x = 1\n")
        modules = _scan_python_modules(tmp_path)
        # Only the good file should be indexed
        assert len(modules) == 1
        assert "good.py" in modules[0]["file_path"]

    def test_skips_encoding_error(self, tmp_path: Path):
        bad = tmp_path / "bad.py"
        bad.write_bytes(b"\x80\x81\x82")  # invalid UTF-8
        modules = _scan_python_modules(tmp_path)
        assert modules == []

    def test_nonexistent_dir(self, tmp_path: Path):
        modules = _scan_python_modules(tmp_path / "nope")
        assert modules == []

    def test_nested_files(self, tmp_path: Path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "__init__.py").write_text("")
        (sub / "mod.py").write_text("class A:\n    def m(self): ...\n")
        modules = _scan_python_modules(tmp_path)
        assert len(modules) == 2  # __init__.py + mod.py


# ---------------------------------------------------------------------------
# Public API tests (using a temp directory as base_path)
# ---------------------------------------------------------------------------

class TestBuildIndex:
    def test_produces_valid_structure(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "app.py").write_text("def main(): ...\n")
        (tmp_path / "migrations").mkdir()

        index = build_index(base_path=tmp_path)

        assert index["version"] == 1
        assert "indexed_at" in index
        # Verify ISO 8601 parseable
        datetime.fromisoformat(index["indexed_at"])
        assert "layers" in index
        layers = index["layers"]
        assert "modules" in layers
        assert "skills" in layers
        assert "tools" in layers
        assert "services" in layers
        assert "models" in layers
        assert "migrations" in layers
        assert "infrastructure" in layers

    def test_persists_json_file(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "x.py").write_text("y = 1\n")
        (tmp_path / "migrations").mkdir()

        build_index(base_path=tmp_path)

        index_path = tmp_path / "data" / "codebase_index.json"
        assert index_path.is_file()
        data = json.loads(index_path.read_text())
        assert data["version"] == 1

    def test_modules_layer_populated(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "config.py").write_text(
            "from src.models.schema import Base\nDB = 'x'\n"
        )
        (tmp_path / "migrations").mkdir()

        index = build_index(base_path=tmp_path)
        modules = index["layers"]["modules"]
        assert len(modules) == 1
        assert modules[0]["imports"] == ["src.models.schema"]


class TestLoadIndex:
    def test_returns_none_when_missing(self, tmp_path: Path):
        assert load_index(base_path=tmp_path) is None

    def test_loads_persisted_index(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.py").write_text("")
        (tmp_path / "migrations").mkdir()

        build_index(base_path=tmp_path)
        loaded = load_index(base_path=tmp_path)
        assert loaded is not None
        assert loaded["version"] == 1


class TestIsStale:
    def test_stale_when_missing(self, tmp_path: Path):
        assert is_stale(base_path=tmp_path) is True

    def test_fresh_after_build(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (tmp_path / "migrations").mkdir()
        build_index(base_path=tmp_path)
        assert is_stale(base_path=tmp_path) is False

    def test_stale_with_zero_max_age(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (tmp_path / "migrations").mkdir()
        build_index(base_path=tmp_path)
        # 0 hours max age means always stale
        assert is_stale(0.0, base_path=tmp_path) is True


class TestEnsureFresh:
    def test_builds_when_missing(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (tmp_path / "migrations").mkdir()
        index = ensure_fresh(base_path=tmp_path)
        assert index["version"] == 1

    def test_returns_existing_when_fresh(self, tmp_path: Path):
        src = tmp_path / "src"
        src.mkdir()
        (tmp_path / "migrations").mkdir()
        first = build_index(base_path=tmp_path)
        second = ensure_fresh(base_path=tmp_path)
        assert first["indexed_at"] == second["indexed_at"]



# ---------------------------------------------------------------------------
# Skills layer AST helper tests
# ---------------------------------------------------------------------------

_SAMPLE_SKILL = textwrap.dedent("""\
    import re
    from src.skills.base_skill import BaseSkill, Command, Result
    from src.services.memory_service import load_memories

    class SampleSkill(BaseSkill):
        @property
        def name(self) -> str:
            return "sample"

        @property
        def description(self) -> str:
            return "A sample skill for testing"

        @property
        def commands(self) -> list:
            return [
                (re.compile(r"^hello$", re.IGNORECASE), "greet"),
                (re.compile(r"^bye$"), "farewell"),
            ]

        def execute(self, db, member, command):
            return Result(success=True, message="ok")

        def verify(self, db, result):
            return True

        def get_help(self):
            return "hello — greet"
""")

_SKILL_WITH_MODULE_PATTERNS = textwrap.dedent("""\
    import re
    from src.skills.base_skill import BaseSkill, Command, Result
    from src.config import DEPLOY_SECRET

    _TRIGGER_A = re.compile(r"^deploy$", re.IGNORECASE)
    _TRIGGER_B = re.compile(r"^status$")

    class DeployLikeSkill(BaseSkill):
        @property
        def name(self) -> str:
            return "deploy_like"

        @property
        def description(self) -> str:
            return "Deploy-like skill"

        @property
        def commands(self) -> list:
            return [
                (_TRIGGER_A, "deploy"),
                (_TRIGGER_B, "status"),
            ]

        def execute(self, db, member, command):
            return Result(success=True, message="ok")

        def verify(self, db, result):
            return True

        def get_help(self):
            return "deploy / status"
""")


class TestExtractPropertyString:
    def test_extracts_name(self):
        tree = _parse(_SAMPLE_SKILL)
        cls_node = next(n for n in ast.iter_child_nodes(tree) if isinstance(n, ast.ClassDef))
        assert _extract_property_string(cls_node, "name") == "sample"

    def test_extracts_description(self):
        tree = _parse(_SAMPLE_SKILL)
        cls_node = next(n for n in ast.iter_child_nodes(tree) if isinstance(n, ast.ClassDef))
        assert _extract_property_string(cls_node, "description") == "A sample skill for testing"

    def test_returns_none_for_missing_property(self):
        tree = _parse(_SAMPLE_SKILL)
        cls_node = next(n for n in ast.iter_child_nodes(tree) if isinstance(n, ast.ClassDef))
        assert _extract_property_string(cls_node, "nonexistent") is None

    def test_returns_none_for_non_property_method(self):
        tree = _parse(textwrap.dedent("""\
            class Foo:
                def name(self) -> str:
                    return "not_a_property"
        """))
        cls_node = next(n for n in ast.iter_child_nodes(tree) if isinstance(n, ast.ClassDef))
        assert _extract_property_string(cls_node, "name") is None


class TestExtractCommandsFromProperty:
    def test_inline_re_compile(self):
        tree = _parse(_SAMPLE_SKILL)
        cls_node = next(n for n in ast.iter_child_nodes(tree) if isinstance(n, ast.ClassDef))
        commands = _extract_commands_from_property(cls_node, {})
        assert len(commands) == 2
        assert commands[0] == {"pattern": "^hello$", "action": "greet"}
        assert commands[1] == {"pattern": "^bye$", "action": "farewell"}

    def test_module_level_patterns(self):
        tree = _parse(_SKILL_WITH_MODULE_PATTERNS)
        cls_node = next(n for n in ast.iter_child_nodes(tree) if isinstance(n, ast.ClassDef))
        regex_map = _build_module_regex_map(tree)
        commands = _extract_commands_from_property(cls_node, regex_map)
        assert len(commands) == 2
        assert commands[0] == {"pattern": "^deploy$", "action": "deploy"}
        assert commands[1] == {"pattern": "^status$", "action": "status"}

    def test_empty_commands(self):
        tree = _parse(textwrap.dedent("""\
            class EmptySkill:
                @property
                def commands(self):
                    return []
        """))
        cls_node = next(n for n in ast.iter_child_nodes(tree) if isinstance(n, ast.ClassDef))
        assert _extract_commands_from_property(cls_node, {}) == []


class TestBuildModuleRegexMap:
    def test_finds_module_level_patterns(self):
        tree = _parse(_SKILL_WITH_MODULE_PATTERNS)
        regex_map = _build_module_regex_map(tree)
        assert regex_map["_TRIGGER_A"] == "^deploy$"
        assert regex_map["_TRIGGER_B"] == "^status$"

    def test_ignores_non_regex_assignments(self):
        tree = _parse("x = 42\ny = 'hello'\n")
        assert _build_module_regex_map(tree) == {}


# ---------------------------------------------------------------------------
# Tools layer AST helper tests
# ---------------------------------------------------------------------------

_SAMPLE_TOOL_REGISTRY = textwrap.dedent("""\
    from __future__ import annotations
    from typing import Any

    ToolSchema = dict[str, Any]

    _TOOL_MAP: dict[str, tuple[str, str]] = {
        "task_create": ("task", "create"),
        "task_list":   ("task", "list"),
        "bug_report":  ("bug", "report"),
    }

    _TOOL_SCHEMAS: list[ToolSchema] = [
        {
            "toolSpec": {
                "name": "task_create",
                "description": "Create a new task.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "Task title"},
                            "assignee": {"type": "string", "description": "Assignee name"},
                            "priority": {"type": "string", "description": "Priority level"},
                        },
                        "required": ["title"],
                    }
                },
            }
        },
        {
            "toolSpec": {
                "name": "task_list",
                "description": "List open tasks.",
                "inputSchema": {"json": {"type": "object", "properties": {}}},
            }
        },
        {
            "toolSpec": {
                "name": "bug_report",
                "description": "Report a bug.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "description": {"type": "string", "description": "Bug description"},
                        },
                        "required": ["description"],
                    }
                },
            }
        },
    ]
""")


class TestExtractToolMap:
    def test_extracts_tool_map(self):
        tree = _parse(_SAMPLE_TOOL_REGISTRY)
        tool_map = _extract_tool_map(tree)
        assert tool_map == {
            "task_create": ("task", "create"),
            "task_list": ("task", "list"),
            "bug_report": ("bug", "report"),
        }

    def test_empty_when_no_tool_map(self):
        tree = _parse("x = 1\n")
        assert _extract_tool_map(tree) == {}


class TestExtractToolSchemas:
    def test_extracts_schemas(self):
        tree = _parse(_SAMPLE_TOOL_REGISTRY)
        schemas = _extract_tool_schemas(tree)
        assert "task_create" in schemas
        assert schemas["task_create"]["description"] == "Create a new task."
        assert schemas["task_create"]["input_schema_summary"] == {
            "required": ["title"],
            "optional": ["assignee", "priority"],
        }

    def test_no_properties_tool(self):
        tree = _parse(_SAMPLE_TOOL_REGISTRY)
        schemas = _extract_tool_schemas(tree)
        assert schemas["task_list"]["input_schema_summary"] == {
            "required": [],
            "optional": [],
        }

    def test_empty_when_no_schemas(self):
        tree = _parse("x = 1\n")
        assert _extract_tool_schemas(tree) == {}


class TestExtractInputSchemaSummary:
    def test_required_and_optional(self):
        tree = _parse(textwrap.dedent("""\
            x = {
                "json": {
                    "type": "object",
                    "properties": {
                        "a": {"type": "string"},
                        "b": {"type": "string"},
                        "c": {"type": "string"},
                    },
                    "required": ["a"],
                }
            }
        """))
        # Get the dict node from the assignment
        assign = tree.body[0]
        summary = _extract_input_schema_summary(assign.value)
        assert summary == {"required": ["a"], "optional": ["b", "c"]}

    def test_no_required_field(self):
        tree = _parse(textwrap.dedent("""\
            x = {
                "json": {
                    "type": "object",
                    "properties": {
                        "a": {"type": "string"},
                    },
                }
            }
        """))
        assign = tree.body[0]
        summary = _extract_input_schema_summary(assign.value)
        assert summary == {"required": [], "optional": ["a"]}

    def test_empty_properties(self):
        tree = _parse(textwrap.dedent("""\
            x = {"json": {"type": "object", "properties": {}}}
        """))
        assign = tree.body[0]
        summary = _extract_input_schema_summary(assign.value)
        assert summary == {"required": [], "optional": []}


# ---------------------------------------------------------------------------
# Tools scanner tests (using a temp directory)
# ---------------------------------------------------------------------------

class TestScanTools:
    def test_scans_tool_registry(self, tmp_path: Path):
        engine_dir = tmp_path / "engine"
        engine_dir.mkdir()
        (engine_dir / "tool_registry.py").write_text(
            _SAMPLE_TOOL_REGISTRY, encoding="utf-8",
        )

        tools = _scan_tools(tmp_path)
        assert len(tools) == 3
        names = [t["tool_name"] for t in tools]
        assert "task_create" in names
        assert "task_list" in names
        assert "bug_report" in names

        tc = next(t for t in tools if t["tool_name"] == "task_create")
        assert tc["skill"] == "task"
        assert tc["action"] == "create"
        assert tc["description"] == "Create a new task."
        assert tc["input_schema_summary"]["required"] == ["title"]
        assert set(tc["input_schema_summary"]["optional"]) == {"assignee", "priority"}

    def test_tool_without_schema(self, tmp_path: Path):
        """A tool in _TOOL_MAP but missing from _TOOL_SCHEMAS gets empty defaults."""
        engine_dir = tmp_path / "engine"
        engine_dir.mkdir()
        code = textwrap.dedent("""\
            _TOOL_MAP = {"orphan_tool": ("orphan", "action")}
            _TOOL_SCHEMAS = []
        """)
        (engine_dir / "tool_registry.py").write_text(code, encoding="utf-8")

        tools = _scan_tools(tmp_path)
        assert len(tools) == 1
        assert tools[0]["tool_name"] == "orphan_tool"
        assert tools[0]["description"] == ""
        assert tools[0]["input_schema_summary"] == {"required": [], "optional": []}

    def test_no_engine_dir(self, tmp_path: Path):
        assert _scan_tools(tmp_path) == []

    def test_syntax_error_in_registry(self, tmp_path: Path):
        engine_dir = tmp_path / "engine"
        engine_dir.mkdir()
        (engine_dir / "tool_registry.py").write_text("def (broken\n", encoding="utf-8")
        assert _scan_tools(tmp_path) == []

    def test_encoding_error(self, tmp_path: Path):
        engine_dir = tmp_path / "engine"
        engine_dir.mkdir()
        (engine_dir / "tool_registry.py").write_bytes(b"\x80\x81\x82")
        assert _scan_tools(tmp_path) == []


# ---------------------------------------------------------------------------
# Skills scanner tests (using a temp directory)
# ---------------------------------------------------------------------------

class TestScanSkills:
    def test_scans_skill_file(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "sample_skill.py").write_text(_SAMPLE_SKILL, encoding="utf-8")

        skills = _scan_skills(tmp_path)
        assert len(skills) == 1
        skill = skills[0]
        assert skill["name"] == "sample"
        assert skill["description"] == "A sample skill for testing"
        assert len(skill["commands"]) == 2
        assert skill["commands"][0]["pattern"] == "^hello$"
        assert skill["commands"][0]["action"] == "greet"
        assert "sample_skill.py" in skill["source_file"]
        assert "src.services.memory_service" in skill["imports"]

    def test_scans_module_level_patterns(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "deploy_like_skill.py").write_text(_SKILL_WITH_MODULE_PATTERNS, encoding="utf-8")

        skills = _scan_skills(tmp_path)
        assert len(skills) == 1
        assert skills[0]["name"] == "deploy_like"
        assert len(skills[0]["commands"]) == 2
        assert skills[0]["commands"][0]["pattern"] == "^deploy$"

    def test_ignores_non_skill_classes(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "helper.py").write_text("class Helper:\n    pass\n", encoding="utf-8")

        skills = _scan_skills(tmp_path)
        assert skills == []

    def test_skips_syntax_errors(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "bad.py").write_text("def (broken\n", encoding="utf-8")
        (skills_dir / "good_skill.py").write_text(_SAMPLE_SKILL, encoding="utf-8")

        skills = _scan_skills(tmp_path)
        assert len(skills) == 1
        assert skills[0]["name"] == "sample"

    def test_empty_skills_dir(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        assert _scan_skills(tmp_path) == []

    def test_no_skills_dir(self, tmp_path: Path):
        assert _scan_skills(tmp_path) == []

    def test_skill_without_name_property_uses_class_name(self, tmp_path: Path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        code = textwrap.dedent("""\
            import re
            from src.skills.base_skill import BaseSkill

            class WeirdSkill(BaseSkill):
                def name(self):
                    return "not_a_property"

                @property
                def description(self) -> str:
                    return "desc"

                @property
                def commands(self):
                    return []

                def execute(self, db, member, command): ...
                def verify(self, db, result): ...
                def get_help(self): ...
        """)
        (skills_dir / "weird_skill.py").write_text(code, encoding="utf-8")

        skills = _scan_skills(tmp_path)
        assert len(skills) == 1
        # Falls back to class name since name() is not a @property
        assert skills[0]["name"] == "WeirdSkill"


# ---------------------------------------------------------------------------
# Smoke test against the real codebase
# ---------------------------------------------------------------------------

class TestRealCodebase:
    """Run the indexer against the actual fortress/src/ tree."""

    def test_indexes_real_codebase(self):
        """Verify the indexer works on the real codebase and finds known files."""
        # Determine the fortress base path from the test file location
        base = Path(__file__).resolve().parent.parent  # fortress/
        index = build_index(base_path=base)

        assert index["version"] == 1
        datetime.fromisoformat(index["indexed_at"])

        modules = index["layers"]["modules"]
        assert len(modules) > 10, "Expected many modules in fortress/src/"

        # Check that known files are indexed
        paths = [m["file_path"] for m in modules]
        # At least config.py and this indexer itself should be present
        assert any("config.py" in p for p in paths)
        assert any("codebase_indexer.py" in p for p in paths)

        # Verify a known class is found (BaseSkill in base_skill.py)
        base_skill_mod = next(
            (m for m in modules if "base_skill.py" in m["file_path"]), None
        )
        assert base_skill_mod is not None
        class_names = [c["name"] for c in base_skill_mod["classes"]]
        assert "BaseSkill" in class_names
        assert "Command" in class_names
        assert "Result" in class_names

    def test_skills_layer_on_real_codebase(self):
        """Verify the skills layer finds known skills in the real codebase."""
        base = Path(__file__).resolve().parent.parent  # fortress/
        index = build_index(base_path=base)

        skills = index["layers"]["skills"]
        assert len(skills) >= 5, f"Expected at least 5 skills, got {len(skills)}"

        skill_names = [s["name"] for s in skills]
        # Known skills that must be present
        assert "chat" in skill_names
        assert "deploy" in skill_names
        assert "memory" in skill_names
        assert "bug" in skill_names

        # Verify chat skill has expected structure
        chat = next(s for s in skills if s["name"] == "chat")
        assert chat["description"] == "שיחה חופשית וברכות"
        assert len(chat["commands"]) >= 1
        assert any(c["action"] == "greet" for c in chat["commands"])
        assert "chat_skill.py" in chat["source_file"]
        assert len(chat["imports"]) > 0

        # Verify deploy skill resolves module-level patterns
        deploy = next(s for s in skills if s["name"] == "deploy")
        assert deploy["description"] == "עדכון ופריסה מרחוק (הורים בלבד)"
        assert len(deploy["commands"]) >= 4
        deploy_actions = [c["action"] for c in deploy["commands"]]
        assert "deploy_all" in deploy_actions
        assert "status" in deploy_actions

    def test_tools_layer_on_real_codebase(self):
        """Verify the tools layer finds known tools in the real codebase."""
        base = Path(__file__).resolve().parent.parent  # fortress/
        index = build_index(base_path=base)

        tools = index["layers"]["tools"]
        assert len(tools) >= 10, f"Expected at least 10 tools, got {len(tools)}"

        tool_names = [t["tool_name"] for t in tools]
        # Known tools that must be present
        assert "task_create" in tool_names
        assert "task_list" in tool_names
        assert "document_list" in tool_names
        assert "bug_report" in tool_names
        assert "memory_list" in tool_names
        assert "save_text" in tool_names

        # Verify task_create has expected structure
        tc = next(t for t in tools if t["tool_name"] == "task_create")
        assert tc["skill"] == "task"
        assert tc["action"] == "create"
        assert "title" in tc["input_schema_summary"]["required"]
        assert len(tc["description"]) > 0

        # Verify every tool has the expected keys
        for tool in tools:
            assert "tool_name" in tool
            assert "skill" in tool
            assert "action" in tool
            assert "description" in tool
            assert "input_schema_summary" in tool
            assert "required" in tool["input_schema_summary"]
            assert "optional" in tool["input_schema_summary"]


# ---------------------------------------------------------------------------
# Services layer tests
# ---------------------------------------------------------------------------

_SAMPLE_SERVICE = textwrap.dedent("""\
    from src.config import DATABASE_URL
    from src.models.schema import Task

    class TaskService:
        def create_task(self, title): ...
        def list_tasks(self): ...
        def _internal_helper(self): ...

    async def run_daily_schedule(db): ...

    def _private_func(): ...
""")


class TestScanServices:
    def test_scans_service_files(self, tmp_path: Path):
        services_dir = tmp_path / "services"
        services_dir.mkdir()
        (services_dir / "__init__.py").write_text("")
        (services_dir / "tasks.py").write_text(_SAMPLE_SERVICE, encoding="utf-8")

        services = _scan_services(tmp_path)
        assert len(services) == 1
        svc = services[0]
        assert "tasks.py" in svc["file_path"]
        assert "TaskService" in svc["classes"]
        assert "create_task" in svc["public_methods"]
        assert "list_tasks" in svc["public_methods"]
        assert "run_daily_schedule" in svc["public_methods"]
        # Private methods/functions excluded
        assert "_internal_helper" not in svc["public_methods"]
        assert "_private_func" not in svc["public_methods"]
        assert "src.config" in svc["imports"]

    def test_skips_init_file(self, tmp_path: Path):
        services_dir = tmp_path / "services"
        services_dir.mkdir()
        (services_dir / "__init__.py").write_text("x = 1\n")
        services = _scan_services(tmp_path)
        assert services == []

    def test_uses_modules_data(self, tmp_path: Path):
        """When modules data is provided, uses it instead of scanning."""
        services_dir = tmp_path / "services"
        services_dir.mkdir()
        modules = [{
            "file_path": str(services_dir / "agent_loop.py"),
            "classes": [{"name": "AgentResult", "methods": ["run", "_build"]}],
            "functions": ["build_system_prompt", "_helper"],
            "imports": ["src.config", "src.engine.tool_executor"],
        }]
        services = _scan_services(tmp_path, modules)
        assert len(services) == 1
        assert services[0]["classes"] == ["AgentResult"]
        assert "run" in services[0]["public_methods"]
        assert "build_system_prompt" in services[0]["public_methods"]
        assert "_build" not in services[0]["public_methods"]
        assert "_helper" not in services[0]["public_methods"]

    def test_empty_services_dir(self, tmp_path: Path):
        services_dir = tmp_path / "services"
        services_dir.mkdir()
        assert _scan_services(tmp_path) == []

    def test_no_services_dir(self, tmp_path: Path):
        assert _scan_services(tmp_path) == []


# ---------------------------------------------------------------------------
# Models layer tests
# ---------------------------------------------------------------------------

_SAMPLE_SCHEMA = textwrap.dedent("""\
    from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
    from sqlalchemy import Text, Boolean, ForeignKey
    from sqlalchemy.dialects.postgresql import UUID

    class Base(DeclarativeBase):
        pass

    class User(Base):
        __tablename__ = "users"
        id: Mapped[int] = mapped_column(UUID, primary_key=True)
        name: Mapped[str] = mapped_column(Text, nullable=False)
        is_active: Mapped[bool] = mapped_column(Boolean, nullable=True)
        tasks: Mapped[list["Task"]] = relationship(back_populates="owner")

    class Task(Base):
        __tablename__ = "tasks"
        id: Mapped[int] = mapped_column(UUID, primary_key=True)
        title: Mapped[str] = mapped_column(Text, nullable=False)
        owner_id: Mapped[int] = mapped_column(UUID, ForeignKey("users.id"), nullable=True)
        owner: Mapped["User"] = relationship(back_populates="tasks", foreign_keys=[owner_id])
""")


class TestScanModels:
    def test_scans_schema(self, tmp_path: Path):
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (models_dir / "schema.py").write_text(_SAMPLE_SCHEMA, encoding="utf-8")

        models = _scan_models(tmp_path)
        assert len(models) == 2

        user = next(m for m in models if m["class_name"] == "User")
        assert user["table_name"] == "users"
        col_names = [c["name"] for c in user["columns"]]
        assert "id" in col_names
        assert "name" in col_names
        assert "is_active" in col_names
        # Check column properties
        id_col = next(c for c in user["columns"] if c["name"] == "id")
        assert id_col["primary_key"] is True
        name_col = next(c for c in user["columns"] if c["name"] == "name")
        assert name_col["nullable"] is False
        # Check relationships
        assert len(user["relationships"]) == 1
        assert user["relationships"][0]["name"] == "tasks"
        assert user["relationships"][0]["target"] == "Task"

    def test_extracts_foreign_keys(self, tmp_path: Path):
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (models_dir / "schema.py").write_text(_SAMPLE_SCHEMA, encoding="utf-8")

        models = _scan_models(tmp_path)
        task = next(m for m in models if m["class_name"] == "Task")
        owner_rel = next(r for r in task["relationships"] if r["name"] == "owner")
        assert owner_rel["target"] == "User"
        assert owner_rel["foreign_key"] == "owner_id"

    def test_referenced_by_populated(self, tmp_path: Path):
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (models_dir / "schema.py").write_text(_SAMPLE_SCHEMA, encoding="utf-8")

        modules = [
            {"file_path": "services/tasks.py", "imports": ["src.models.schema"]},
            {"file_path": "services/auth.py", "imports": ["src.config"]},
        ]
        models = _scan_models(tmp_path, modules)
        for m in models:
            assert "services/tasks.py" in m["referenced_by"]
            assert "services/auth.py" not in m["referenced_by"]

    def test_no_schema_file(self, tmp_path: Path):
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        assert _scan_models(tmp_path) == []

    def test_ignores_non_base_classes(self, tmp_path: Path):
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        code = textwrap.dedent("""\
            from sqlalchemy.orm import DeclarativeBase

            class Base(DeclarativeBase):
                pass

            class Helper:
                pass
        """)
        (models_dir / "schema.py").write_text(code, encoding="utf-8")
        models = _scan_models(tmp_path)
        assert models == []  # Base itself has no __tablename__, Helper doesn't inherit Base


class TestExtractTablename:
    def test_simple_tablename(self):
        tree = _parse(textwrap.dedent("""\
            class Foo:
                __tablename__ = "foos"
        """))
        cls = next(n for n in ast.iter_child_nodes(tree) if isinstance(n, ast.ClassDef))
        assert _extract_tablename(cls) == "foos"

    def test_no_tablename(self):
        tree = _parse(textwrap.dedent("""\
            class Foo:
                pass
        """))
        cls = next(n for n in ast.iter_child_nodes(tree) if isinstance(n, ast.ClassDef))
        assert _extract_tablename(cls) is None


class TestExtractColumns:
    def test_extracts_mapped_columns(self):
        tree = _parse(textwrap.dedent("""\
            class Foo:
                id: Mapped[int] = mapped_column(UUID, primary_key=True)
                name: Mapped[str] = mapped_column(Text, nullable=False)
        """))
        cls = next(n for n in ast.iter_child_nodes(tree) if isinstance(n, ast.ClassDef))
        cols = _extract_columns(cls)
        assert len(cols) == 2
        assert cols[0]["name"] == "id"
        assert cols[0]["type"] == "UUID"
        assert cols[0]["primary_key"] is True
        assert cols[1]["name"] == "name"
        assert cols[1]["nullable"] is False

    def test_skips_private_attrs(self):
        tree = _parse(textwrap.dedent("""\
            class Foo:
                __tablename__ = "foos"
                _internal: Mapped[str] = mapped_column(Text)
        """))
        cls = next(n for n in ast.iter_child_nodes(tree) if isinstance(n, ast.ClassDef))
        cols = _extract_columns(cls)
        assert cols == []


class TestExtractRelationships:
    def test_extracts_relationships(self):
        tree = _parse(textwrap.dedent("""\
            class Foo:
                items: Mapped[list["Item"]] = relationship(back_populates="foo")
        """))
        cls = next(n for n in ast.iter_child_nodes(tree) if isinstance(n, ast.ClassDef))
        rels = _extract_relationships(cls)
        assert len(rels) == 1
        assert rels[0]["name"] == "items"
        assert rels[0]["target"] == "Item"

    def test_extracts_foreign_key(self):
        tree = _parse(textwrap.dedent("""\
            class Foo:
                owner: Mapped["User"] = relationship(back_populates="foos", foreign_keys=[owner_id])
        """))
        cls = next(n for n in ast.iter_child_nodes(tree) if isinstance(n, ast.ClassDef))
        rels = _extract_relationships(cls)
        assert rels[0]["foreign_key"] == "owner_id"


# ---------------------------------------------------------------------------
# Migrations layer tests
# ---------------------------------------------------------------------------

class TestScanMigrations:
    def test_scans_sql_files(self, tmp_path: Path):
        (tmp_path / "001_initial.sql").write_text("-- Initial schema\nBEGIN;\n")
        (tmp_path / "002_tasks.sql").write_text("BEGIN;\n-- Tasks table\n")

        migrations = _scan_migrations(tmp_path)
        assert len(migrations) == 2
        assert migrations[0]["filename"] == "001_initial.sql"
        assert migrations[0]["description"] == "Initial schema"

    def test_fallback_to_filename(self, tmp_path: Path):
        """When no comment is found, derives description from filename."""
        (tmp_path / "003_add_users.sql").write_text("BEGIN;\nCREATE TABLE users();\n")
        migrations = _scan_migrations(tmp_path)
        assert migrations[0]["description"] == "Add users"

    def test_empty_dir(self, tmp_path: Path):
        assert _scan_migrations(tmp_path) == []

    def test_nonexistent_dir(self, tmp_path: Path):
        assert _scan_migrations(tmp_path / "nope") == []

    def test_skips_non_sql_files(self, tmp_path: Path):
        (tmp_path / "readme.md").write_text("# Migrations\n")
        (tmp_path / "001_init.sql").write_text("-- Init\n")
        migrations = _scan_migrations(tmp_path)
        assert len(migrations) == 1


class TestExtractMigrationDescription:
    def test_first_comment_line(self, tmp_path: Path):
        f = tmp_path / "test.sql"
        f.write_text("-- Fortress 2.0 Initial Schema\n-- More details\n")
        assert _extract_migration_description(f) == "Fortress 2.0 Initial Schema"

    def test_skips_blank_lines(self, tmp_path: Path):
        f = tmp_path / "test.sql"
        f.write_text("\n\n-- After blanks\n")
        assert _extract_migration_description(f) == "After blanks"

    def test_fallback_filename(self, tmp_path: Path):
        f = tmp_path / "005_cleanup_data.sql"
        f.write_text("BEGIN;\n")
        assert _extract_migration_description(f) == "Cleanup data"


# ---------------------------------------------------------------------------
# Infrastructure layer tests
# ---------------------------------------------------------------------------

_SAMPLE_MAIN = textwrap.dedent("""\
    from fastapi import FastAPI
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    from src.routers import health, whatsapp, scheduler, dashboard

    _scheduler = AsyncIOScheduler()

    async def lifespan(app):
        _scheduler.add_job(
            _scheduled_run,
            CronTrigger(hour=7, minute=0),
            id="daily_recurring",
            replace_existing=True,
        )
        yield

    app = FastAPI()
    app.include_router(health.router)
    app.include_router(whatsapp.router)
    app.include_router(scheduler.router)
    app.include_router(dashboard.router)
""")

_SAMPLE_CONFIG = textwrap.dedent("""\
    import os
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    WAHA_API_URL: str = os.getenv("WAHA_API_URL", "")
    _internal = "not a config key"
    lowercase_var = "also not"
""")


class TestScanInfrastructure:
    def test_scans_main_and_config(self, tmp_path: Path):
        (tmp_path / "main.py").write_text(_SAMPLE_MAIN, encoding="utf-8")
        (tmp_path / "config.py").write_text(_SAMPLE_CONFIG, encoding="utf-8")
        # Create external integration files
        services_dir = tmp_path / "services"
        services_dir.mkdir()
        (services_dir / "whatsapp_client.py").write_text("")
        (services_dir / "bedrock_client.py").write_text("")
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "deploy_skill.py").write_text("")

        infra = _scan_infrastructure(tmp_path)
        assert str(tmp_path / "main.py") in infra["entrypoints"]
        assert "health" in infra["routers"]
        assert "whatsapp" in infra["routers"]
        assert "scheduler" in infra["routers"]
        assert "dashboard" in infra["routers"]
        assert len(infra["scheduler_jobs"]) == 1
        assert infra["scheduler_jobs"][0]["id"] == "daily_recurring"
        assert "DATABASE_URL" in infra["config_keys"]
        assert "WAHA_API_URL" in infra["config_keys"]
        assert "_internal" not in infra["config_keys"]
        assert "lowercase_var" not in infra["config_keys"]
        assert "whatsapp_client.py" in infra["external_integrations"]
        assert "bedrock_client.py" in infra["external_integrations"]
        assert "deploy_skill.py" in infra["external_integrations"]

    def test_no_main_or_config(self, tmp_path: Path):
        infra = _scan_infrastructure(tmp_path)
        assert infra["entrypoints"] == []
        assert infra["routers"] == []
        assert infra["config_keys"] == []


class TestExtractRouters:
    def test_extracts_routers(self):
        tree = _parse(_SAMPLE_MAIN)
        routers = _extract_routers(tree)
        assert routers == ["health", "whatsapp", "scheduler", "dashboard"]

    def test_no_routers(self):
        tree = _parse("x = 1\n")
        assert _extract_routers(tree) == []


class TestExtractSchedulerJobs:
    def test_extracts_jobs(self):
        tree = _parse(_SAMPLE_MAIN)
        jobs = _extract_scheduler_jobs(tree)
        assert len(jobs) == 1
        assert jobs[0]["id"] == "daily_recurring"
        assert "CronTrigger" in jobs[0]["trigger"]


class TestExtractConfigKeys:
    def test_extracts_uppercase_keys(self):
        tree = _parse(_SAMPLE_CONFIG)
        keys = _extract_config_keys(tree)
        assert "DATABASE_URL" in keys
        assert "WAHA_API_URL" in keys
        assert "_internal" not in keys
        assert "lowercase_var" not in keys


# ---------------------------------------------------------------------------
# Real codebase smoke tests for new layers
# ---------------------------------------------------------------------------

class TestRealCodebaseNewLayers:
    """Run the new layer scanners against the actual fortress codebase."""

    def test_services_layer_on_real_codebase(self):
        base = Path(__file__).resolve().parent.parent  # fortress/
        index = build_index(base_path=base)
        services = index["layers"]["services"]
        assert len(services) >= 10, f"Expected at least 10 services, got {len(services)}"

        # Known services should be present
        filenames = [Path(s["file_path"]).name for s in services]
        assert "agent_loop.py" in filenames
        assert "scheduler.py" in filenames
        assert "whatsapp_client.py" in filenames
        assert "bedrock_client.py" in filenames

        # Verify structure
        for svc in services:
            assert "file_path" in svc
            assert "classes" in svc
            assert "public_methods" in svc
            assert "imports" in svc
            assert isinstance(svc["classes"], list)
            assert isinstance(svc["public_methods"], list)

    def test_models_layer_on_real_codebase(self):
        base = Path(__file__).resolve().parent.parent
        index = build_index(base_path=base)
        models = index["layers"]["models"]
        assert len(models) >= 8, f"Expected at least 8 models, got {len(models)}"

        model_names = [m["class_name"] for m in models]
        assert "FamilyMember" in model_names
        assert "Task" in model_names
        assert "Document" in model_names
        assert "Conversation" in model_names

        # Verify FamilyMember structure
        fm = next(m for m in models if m["class_name"] == "FamilyMember")
        assert fm["table_name"] == "family_members"
        col_names = [c["name"] for c in fm["columns"]]
        assert "id" in col_names
        assert "name" in col_names
        assert "phone" in col_names
        assert len(fm["relationships"]) > 0
        assert len(fm["referenced_by"]) > 0

        # Verify Task has foreign key relationships
        task = next(m for m in models if m["class_name"] == "Task")
        assert task["table_name"] == "tasks"
        rel_names = [r["name"] for r in task["relationships"]]
        assert "assignee" in rel_names
        assignee_rel = next(r for r in task["relationships"] if r["name"] == "assignee")
        assert assignee_rel["target"] == "FamilyMember"
        assert assignee_rel.get("foreign_key") == "assigned_to"

    def test_migrations_layer_on_real_codebase(self):
        base = Path(__file__).resolve().parent.parent
        index = build_index(base_path=base)
        migrations = index["layers"]["migrations"]
        assert len(migrations) >= 10, f"Expected at least 10 migrations, got {len(migrations)}"

        filenames = [m["filename"] for m in migrations]
        assert "001_initial_schema.sql" in filenames
        assert "002_tasks_and_recurring.sql" in filenames

        # Verify structure
        for mig in migrations:
            assert "filename" in mig
            assert "description" in mig
            assert len(mig["description"]) > 0

        # First migration should have a meaningful description
        first = next(m for m in migrations if m["filename"] == "001_initial_schema.sql")
        assert "initial" in first["description"].lower() or "schema" in first["description"].lower()

    def test_infrastructure_layer_on_real_codebase(self):
        base = Path(__file__).resolve().parent.parent
        index = build_index(base_path=base)
        infra = index["layers"]["infrastructure"]

        assert len(infra["entrypoints"]) >= 1
        assert any("main.py" in e for e in infra["entrypoints"])
        assert "health" in infra["routers"]
        assert "whatsapp" in infra["routers"]
        assert "scheduler" in infra["routers"]
        assert "dashboard" in infra["routers"]
        assert len(infra["scheduler_jobs"]) >= 1
        assert any(j["id"] == "daily_recurring" for j in infra["scheduler_jobs"])
        assert "whatsapp_client.py" in infra["external_integrations"]
        assert "bedrock_client.py" in infra["external_integrations"]
        assert "deploy_skill.py" in infra["external_integrations"]
        assert "DATABASE_URL" in infra["config_keys"]
        assert "WAHA_API_URL" in infra["config_keys"]
        assert "BEDROCK_API_KEY" in infra["config_keys"]
        assert "DEPLOY_SECRET" in infra["config_keys"]


# ---------------------------------------------------------------------------
# Incremental re-indexing tests (Task 1.5)
# ---------------------------------------------------------------------------

from src.services.codebase_indexer import _incremental_scan_modules


class TestIncrementalReindexing:
    """Tests for incremental re-indexing support (Requirement 1.9)."""

    def _setup_base(self, tmp_path: Path):
        """Create a minimal project structure and return base path."""
        src = tmp_path / "src"
        src.mkdir()
        (tmp_path / "migrations").mkdir()
        return tmp_path

    def test_unchanged_files_preserve_entries(self, tmp_path: Path):
        """Unchanged files (same mtime) should keep their existing entries."""
        base = self._setup_base(tmp_path)
        src = base / "src"
        (src / "a.py").write_text("def hello(): ...\n")
        (src / "b.py").write_text("def world(): ...\n")

        # Build initial index
        first = build_index(base_path=base)
        first_modules = first["layers"]["modules"]
        assert len(first_modules) == 2

        # Build again without force — files haven't changed
        second = build_index(base_path=base)
        second_modules = second["layers"]["modules"]
        assert len(second_modules) == 2

        # Entries should be identical (preserved from existing index)
        for fm, sm in zip(first_modules, second_modules):
            assert fm["file_path"] == sm["file_path"]
            assert fm["mtime"] == sm["mtime"]
            assert fm["functions"] == sm["functions"]
            assert fm["classes"] == sm["classes"]
            assert fm["imports"] == sm["imports"]

    def test_modified_files_get_rescanned(self, tmp_path: Path):
        """Files with changed mtime should be re-scanned."""
        base = self._setup_base(tmp_path)
        src = base / "src"
        py_file = src / "mod.py"
        py_file.write_text("def original(): ...\n")

        first = build_index(base_path=base)
        assert first["layers"]["modules"][0]["functions"] == ["original"]

        # Modify the file — change content and force a different mtime
        import time
        time.sleep(0.05)  # Ensure mtime changes
        py_file.write_text("def updated(): ...\ndef extra(): ...\n")
        # Touch to ensure mtime is different
        os.utime(py_file, None)

        second = build_index(base_path=base)
        mod = second["layers"]["modules"][0]
        assert "updated" in mod["functions"]
        assert "extra" in mod["functions"]
        assert "original" not in mod["functions"]

    def test_deleted_files_are_removed(self, tmp_path: Path):
        """Files that no longer exist should be dropped from the index."""
        base = self._setup_base(tmp_path)
        src = base / "src"
        (src / "keep.py").write_text("x = 1\n")
        (src / "remove.py").write_text("y = 2\n")

        first = build_index(base_path=base)
        assert len(first["layers"]["modules"]) == 2

        # Delete one file
        (src / "remove.py").unlink()

        second = build_index(base_path=base)
        paths = [m["file_path"] for m in second["layers"]["modules"]]
        assert len(paths) == 1
        assert any("keep.py" in p for p in paths)
        assert not any("remove.py" in p for p in paths)

    def test_new_files_are_added(self, tmp_path: Path):
        """New files should be scanned and added to the index."""
        base = self._setup_base(tmp_path)
        src = base / "src"
        (src / "existing.py").write_text("a = 1\n")

        first = build_index(base_path=base)
        assert len(first["layers"]["modules"]) == 1

        # Add a new file
        (src / "brand_new.py").write_text("def fresh(): ...\n")

        second = build_index(base_path=base)
        assert len(second["layers"]["modules"]) == 2
        paths = [m["file_path"] for m in second["layers"]["modules"]]
        assert any("brand_new.py" in p for p in paths)
        new_mod = next(m for m in second["layers"]["modules"] if "brand_new.py" in m["file_path"])
        assert new_mod["functions"] == ["fresh"]

    def test_force_true_always_does_full_scan(self, tmp_path: Path):
        """force=True should do a full scan regardless of existing index."""
        base = self._setup_base(tmp_path)
        src = base / "src"
        (src / "a.py").write_text("def foo(): ...\n")

        # Build initial index
        build_index(base_path=base)

        # Build with force=True — should still work and produce valid index
        forced = build_index(force=True, base_path=base)
        assert forced["version"] == 1
        assert len(forced["layers"]["modules"]) == 1
        assert forced["layers"]["modules"][0]["functions"] == ["foo"]


class TestIncrementalScanModules:
    """Unit tests for the _incremental_scan_modules helper."""

    def test_reuses_unchanged_entry(self, tmp_path: Path):
        py = tmp_path / "hello.py"
        py.write_text("def greet(): ...\n")
        mtime = py.stat().st_mtime

        existing = [{
            "file_path": str(py),
            "mtime": mtime,
            "classes": [],
            "functions": ["greet"],
            "imports": [],
        }]

        result = _incremental_scan_modules(tmp_path, existing)
        assert len(result) == 1
        # Should be the exact same dict object (preserved)
        assert result[0] is existing[0]

    def test_rescans_when_mtime_differs(self, tmp_path: Path):
        py = tmp_path / "hello.py"
        py.write_text("def updated(): ...\n")

        existing = [{
            "file_path": str(py),
            "mtime": 0.0,  # Stale mtime
            "classes": [],
            "functions": ["old_func"],
            "imports": [],
        }]

        result = _incremental_scan_modules(tmp_path, existing)
        assert len(result) == 1
        assert result[0]["functions"] == ["updated"]
        assert result[0] is not existing[0]

    def test_drops_deleted_files(self, tmp_path: Path):
        existing = [{
            "file_path": str(tmp_path / "gone.py"),
            "mtime": 12345.0,
            "classes": [],
            "functions": ["ghost"],
            "imports": [],
        }]

        result = _incremental_scan_modules(tmp_path, existing)
        assert result == []

    def test_adds_new_files(self, tmp_path: Path):
        py = tmp_path / "new.py"
        py.write_text("class Fresh: ...\n")

        result = _incremental_scan_modules(tmp_path, [])
        assert len(result) == 1
        assert result[0]["classes"][0]["name"] == "Fresh"

    def test_empty_src_root(self, tmp_path: Path):
        result = _incremental_scan_modules(tmp_path / "nonexistent", [])
        assert result == []
