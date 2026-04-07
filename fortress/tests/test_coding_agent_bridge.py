"""Unit tests for fortress.src.services.coding_agent_bridge — Phase C1."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from src.models.schema import FamilyMember
from src.services.coding_agent_bridge import (
    PromptResult,
    _assemble_prompt,
    _load_project_structure,
    _read_source_file,
    _resolve_prompts_dir,
    _sanitize_feature_name,
    generate_prompt,
)
from src.services.feature_planner import AttributedClaim, Plan
from src.skills.base_skill import Command
from src.skills.dev_skill import DevSkill


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_plan(
    request_summary: str = "Test feature",
    files_to_modify: list[AttributedClaim] | None = None,
    relevant_components: list[AttributedClaim] | None = None,
    missing_components: list[AttributedClaim] | None = None,
    development_tasks: list[AttributedClaim] | None = None,
    breaking_change_risks: list[AttributedClaim] | None = None,
) -> Plan:
    return Plan(
        request_summary=request_summary,
        files_to_modify=files_to_modify or [],
        relevant_components=relevant_components or [],
        missing_components=missing_components or [],
        development_tasks=development_tasks or [
            AttributedClaim(text="Do something", attribution="llm_assumption"),
        ],
        breaking_change_risks=breaking_change_risks or [],
        created_at="2025-01-01T00:00:00+00:00",
    )


def _member(is_admin: bool = True) -> MagicMock:
    m = MagicMock(spec=FamilyMember)
    m.id = uuid.uuid4()
    m.name = "Admin"
    m.is_admin = is_admin
    return m


# ---------------------------------------------------------------------------
# _sanitize_feature_name
# ---------------------------------------------------------------------------

class TestSanitizeFeatureName:
    def test_strips_timestamp_prefix(self):
        result = _sanitize_feature_name("20250101_143022_budget_tracking.md")
        assert result == "budget_tracking"

    def test_strips_md_suffix(self):
        result = _sanitize_feature_name("my_feature.md")
        assert result == "my_feature"

    def test_strips_both(self):
        result = _sanitize_feature_name("20250615_120000_add_auth.md")
        assert result == "add_auth"

    def test_no_timestamp_no_suffix(self):
        result = _sanitize_feature_name("plain_name")
        assert result == "plain_name"

    def test_empty_after_strip_returns_feature(self):
        result = _sanitize_feature_name("20250101_143022_.md")
        assert result == "feature"

    def test_special_chars_replaced(self):
        result = _sanitize_feature_name("20250101_143022_my-feature name.md")
        assert " " not in result
        assert "-" not in result


# ---------------------------------------------------------------------------
# _read_source_file
# ---------------------------------------------------------------------------

class TestReadSourceFile:
    def test_returns_context_unavailable_for_missing_file(self):
        content, truncated = _read_source_file("/nonexistent/path/file.py")
        assert content == "[CONTEXT UNAVAILABLE]"
        assert truncated is False

    def test_reads_existing_file(self, tmp_path: Path):
        f = tmp_path / "test.py"
        f.write_text("line1\nline2\nline3\n", encoding="utf-8")
        content, truncated = _read_source_file(str(f))
        assert "line1" in content
        assert truncated is False

    def test_truncates_file_over_max_lines(self, tmp_path: Path):
        f = tmp_path / "big.py"
        lines = [f"line{i}" for i in range(600)]
        f.write_text("\n".join(lines), encoding="utf-8")
        content, truncated = _read_source_file(str(f), max_lines=500)
        assert truncated is True
        assert len(content.splitlines()) == 500

    def test_no_truncation_under_max_lines(self, tmp_path: Path):
        f = tmp_path / "small.py"
        lines = [f"line{i}" for i in range(10)]
        f.write_text("\n".join(lines), encoding="utf-8")
        content, truncated = _read_source_file(str(f), max_lines=500)
        assert truncated is False
        assert len(content.splitlines()) == 10

    def test_exact_max_lines_not_truncated(self, tmp_path: Path):
        f = tmp_path / "exact.py"
        lines = [f"line{i}" for i in range(500)]
        f.write_text("\n".join(lines), encoding="utf-8")
        content, truncated = _read_source_file(str(f), max_lines=500)
        assert truncated is False


# ---------------------------------------------------------------------------
# _load_project_structure
# ---------------------------------------------------------------------------

class TestLoadProjectStructure:
    def test_returns_context_unavailable_when_no_index(self, tmp_path: Path):
        with patch("src.services.coding_agent_bridge.Path") as MockPath:
            # Make all candidate paths non-existent
            mock_instance = MagicMock()
            mock_instance.is_file.return_value = False
            MockPath.return_value = mock_instance
            MockPath.cwd.return_value = tmp_path
            result = _load_project_structure()
        # Since we can't easily mock Path.cwd in the function, test with a real tmp dir
        # that has no index file
        with patch("src.services.coding_agent_bridge.Path.cwd", return_value=tmp_path):
            result = _load_project_structure()
        assert result == "[CONTEXT UNAVAILABLE]"

    def test_loads_modules_from_index(self, tmp_path: Path):
        index_data = {
            "layers": {
                "modules": [
                    {
                        "file_path": "src/services/foo.py",
                        "classes": [{"name": "FooService"}],
                        "functions": ["bar", "baz"],
                    }
                ]
            }
        }
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        index_file = data_dir / "codebase_index.json"
        index_file.write_text(json.dumps(index_data), encoding="utf-8")

        with patch("src.services.coding_agent_bridge.Path.cwd", return_value=tmp_path):
            result = _load_project_structure()

        assert "src/services/foo.py" in result
        assert "FooService" in result

    def test_returns_context_unavailable_on_empty_modules(self, tmp_path: Path):
        index_data = {"layers": {"modules": []}}
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        index_file = data_dir / "codebase_index.json"
        index_file.write_text(json.dumps(index_data), encoding="utf-8")

        with patch("src.services.coding_agent_bridge.Path.cwd", return_value=tmp_path):
            result = _load_project_structure()

        assert result == "[CONTEXT UNAVAILABLE]"


# ---------------------------------------------------------------------------
# _assemble_prompt
# ---------------------------------------------------------------------------

class TestAssemblePrompt:
    REQUIRED_SECTIONS = [
        "## Feature Request",
        "## Project Structure",
        "## Files to Modify",
        "## New Files to Create",
        "## Development Tasks",
        "## Constraints and Risks",
        "## Test Requirements",
        "## Instructions",
    ]

    def _build_prompt(self, plan: Plan | None = None, **kwargs) -> str:
        if plan is None:
            plan = _make_plan()
        return _assemble_prompt(
            plan=plan,
            plan_filename=kwargs.get("plan_filename", "20250101_120000_test_feature.md"),
            file_contents=kwargs.get("file_contents", {}),
            project_structure=kwargs.get("project_structure", "- src/foo.py"),
            max_chars=kwargs.get("max_chars", 200_000),
        )

    def test_contains_all_required_sections(self):
        prompt = self._build_prompt()
        for section in self.REQUIRED_SECTIONS:
            assert section in prompt, f"Missing section: {section}"

    def test_contains_feature_request(self):
        plan = _make_plan(request_summary="Add budget tracking")
        prompt = self._build_prompt(plan=plan)
        assert "Add budget tracking" in prompt

    def test_contains_project_structure(self):
        prompt = self._build_prompt(project_structure="- src/services/foo.py — classes: FooService")
        assert "src/services/foo.py" in prompt

    def test_contains_file_content(self, tmp_path: Path):
        plan = _make_plan(
            files_to_modify=[
                AttributedClaim(text="Modify foo", attribution="indexed_fact", source_path="src/foo.py"),
            ]
        )
        prompt = self._build_prompt(
            plan=plan,
            file_contents={"src/foo.py": "def foo():\n    pass\n"},
        )
        assert "def foo():" in prompt

    def test_missing_file_shows_context_unavailable(self):
        plan = _make_plan(
            files_to_modify=[
                AttributedClaim(text="Modify bar", attribution="indexed_fact", source_path="src/bar.py"),
            ]
        )
        prompt = self._build_prompt(
            plan=plan,
            file_contents={"src/bar.py": None},
        )
        assert "[CONTEXT UNAVAILABLE]" in prompt

    def test_instructions_mention_branch(self):
        prompt = self._build_prompt()
        assert "branch" in prompt.lower() or "feature/" in prompt

    def test_instructions_mention_draft_pr(self):
        prompt = self._build_prompt()
        assert "draft" in prompt.lower()

    def test_instructions_say_never_merge(self):
        prompt = self._build_prompt()
        assert "never merge" in prompt.lower() or "אל תמזג" in prompt

    def test_instructions_say_never_deploy(self):
        prompt = self._build_prompt()
        assert "never deploy" in prompt.lower() or "אל תפרוס" in prompt

    def test_development_tasks_numbered(self):
        plan = _make_plan(
            development_tasks=[
                AttributedClaim(text="Task one", attribution="llm_assumption"),
                AttributedClaim(text="Task two", attribution="llm_assumption"),
            ]
        )
        prompt = self._build_prompt(plan=plan)
        assert "1." in prompt
        assert "2." in prompt

    def test_truncation_applied_when_over_max_chars(self, tmp_path: Path):
        big_content = "\n".join([f"line {i}" for i in range(1000)])
        plan = _make_plan(
            files_to_modify=[
                AttributedClaim(text="Modify big", attribution="indexed_fact", source_path="src/big.py"),
            ]
        )
        prompt = self._build_prompt(
            plan=plan,
            file_contents={"src/big.py": big_content},
            max_chars=500,
        )
        # Prompt should be within a reasonable range (truncation applied)
        # The header + static sections alone may exceed 500, so just verify
        # the file content was truncated (not all 1000 lines present)
        assert "line 999" not in prompt or len(prompt) <= 500 + 200  # some slack for static sections


# ---------------------------------------------------------------------------
# generate_prompt
# ---------------------------------------------------------------------------

class TestGeneratePrompt:
    def test_creates_file_in_prompts_dir(self, tmp_path: Path):
        plan = _make_plan()
        with patch("src.services.coding_agent_bridge._resolve_prompts_dir", return_value=tmp_path), \
             patch("src.services.coding_agent_bridge._load_project_structure", return_value="- src/foo.py"):
            result = generate_prompt(plan, "20250101_120000_test_feature.md")

        assert result.success is True
        assert result.prompt_path is not None
        assert result.prompt_path.exists()
        assert result.prompt_path.suffix == ".md"

    def test_filename_matches_timestamp_pattern(self, tmp_path: Path):
        plan = _make_plan()
        with patch("src.services.coding_agent_bridge._resolve_prompts_dir", return_value=tmp_path), \
             patch("src.services.coding_agent_bridge._load_project_structure", return_value="- src/foo.py"):
            result = generate_prompt(plan, "20250101_120000_test_feature.md")

        assert result.prompt_path is not None
        assert re.match(r"^\d{8}_\d{6}_.+\.md$", result.prompt_path.name)

    def test_returns_failure_on_write_error(self, tmp_path: Path):
        plan = _make_plan()
        with patch("src.services.coding_agent_bridge._resolve_prompts_dir", return_value=tmp_path), \
             patch("src.services.coding_agent_bridge._load_project_structure", return_value="- src/foo.py"), \
             patch("pathlib.Path.write_text", side_effect=OSError("disk full")):
            result = generate_prompt(plan, "20250101_120000_test_feature.md")

        assert result.success is False
        assert result.prompt_path is None

    def test_tracks_embedded_and_missing_counts(self, tmp_path: Path):
        src_file = tmp_path / "real_file.py"
        src_file.write_text("def foo(): pass\n", encoding="utf-8")

        plan = _make_plan(
            files_to_modify=[
                AttributedClaim(text="Modify real", attribution="indexed_fact", source_path=str(src_file)),
                AttributedClaim(text="Modify missing", attribution="indexed_fact", source_path="/nonexistent/file.py"),
            ]
        )
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        with patch("src.services.coding_agent_bridge._resolve_prompts_dir", return_value=prompts_dir), \
             patch("src.services.coding_agent_bridge._load_project_structure", return_value="- src/foo.py"):
            result = generate_prompt(plan, "20250101_120000_test.md")

        assert result.files_embedded == 1
        assert result.files_missing == 1

    def test_message_contains_filename(self, tmp_path: Path):
        plan = _make_plan()
        with patch("src.services.coding_agent_bridge._resolve_prompts_dir", return_value=tmp_path), \
             patch("src.services.coding_agent_bridge._load_project_structure", return_value="- src/foo.py"):
            result = generate_prompt(plan, "20250101_120000_test_feature.md")

        assert result.prompt_path is not None
        assert result.prompt_path.name in result.message or "test_feature" in result.message


# ---------------------------------------------------------------------------
# Admin gate — DevSkill generate_prompt action
# ---------------------------------------------------------------------------

class TestDevSkillAdminGate:
    def test_non_admin_gets_permission_denied(self):
        skill = DevSkill()
        db = MagicMock(spec=Session)
        result = skill.execute(
            db,
            _member(is_admin=False),
            Command(skill="dev", action="generate_prompt", params={}, raw_text="generate prompt"),
        )
        assert result.success is False
        assert "הרשאה" in result.message

    def test_admin_can_call_generate_prompt(self, tmp_path: Path):
        skill = DevSkill()
        db = MagicMock(spec=Session)

        # Create a fake plan file
        plans_dir = tmp_path / "plans"
        plans_dir.mkdir()
        plan_file = plans_dir / "20250101_120000_test.md"
        plan_file.write_text(
            "# Feature Plan: Test feature\n\n## Development Tasks\n\n- Do something _[llm_assumption]_\n",
            encoding="utf-8",
        )
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()

        with patch("src.services.feature_planner._resolve_plans_dir", return_value=plans_dir), \
             patch("src.services.coding_agent_bridge._resolve_prompts_dir", return_value=prompts_dir), \
             patch("src.services.coding_agent_bridge._load_project_structure", return_value="- src/foo.py"), \
             patch("src.skills.dev_skill.audit") as mock_audit:
            result = skill.execute(
                db,
                _member(is_admin=True),
                Command(
                    skill="dev",
                    action="generate_prompt",
                    params={"plan_filename": "20250101_120000_test.md"},
                    raw_text="generate prompt 20250101_120000_test.md",
                ),
            )

        assert result.success is True
        mock_audit.log_action.assert_called_once()
        call_kwargs = mock_audit.log_action.call_args
        assert "generate_prompt" in str(call_kwargs)
        assert "dev" in str(call_kwargs)
