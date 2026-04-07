"""Tests for fortress.src.services.feature_planner — Tasks 6.1, 6.2, 6.3."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from src.models.schema import FamilyMember
from src.services.feature_planner import (
    VALID_ATTRIBUTIONS,
    AttributedClaim,
    Plan,
    _parse_claims,
    _parse_plan_response,
    _render_claims_markdown,
    plan_summary,
    save_plan_markdown,
)
from src.skills.base_skill import Command
from src.skills.dev_skill import DevSkill


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _member(is_admin: bool = True) -> MagicMock:
    m = MagicMock(spec=FamilyMember)
    m.id = uuid.uuid4()
    m.name = "Admin"
    m.phone = "+972501234567"
    m.role = "parent"
    m.is_active = True
    m.is_admin = is_admin
    return m


_SAMPLE_LLM_JSON = json.dumps({
    "request_summary": "Add a budget tracking feature",
    "relevant_components": [
        {"text": "TaskService handles task CRUD", "attribution": "indexed_fact", "source_path": "src/services/tasks.py"},
        {"text": "All skills inherit BaseSkill", "attribution": "inferred_pattern", "source_path": None},
    ],
    "missing_components": [
        {"text": "BudgetService needs to be created", "attribution": "llm_assumption", "source_path": None},
    ],
    "files_to_modify": [
        {"text": "tool_registry.py needs new budget tools", "attribution": "inferred_pattern", "source_path": "src/engine/tool_registry.py"},
    ],
    "breaking_change_risks": [
        {"text": "Schema migration required for budget table", "attribution": "llm_assumption", "source_path": None},
    ],
    "development_tasks": [
        {"text": "Create BudgetService", "attribution": "llm_assumption", "source_path": None},
        {"text": "Add budget_skill.py", "attribution": "llm_assumption", "source_path": None},
        {"text": "Write migration 013_budget.sql", "attribution": "llm_assumption", "source_path": None},
    ],
})


# ---------------------------------------------------------------------------
# Plan structure completeness
# ---------------------------------------------------------------------------

class TestPlanStructure:
    """Plan dataclass must have all required sections."""

    def test_plan_has_all_sections(self):
        plan = _parse_plan_response(_SAMPLE_LLM_JSON, "budget feature")
        assert plan.request_summary
        assert isinstance(plan.relevant_components, list)
        assert isinstance(plan.missing_components, list)
        assert isinstance(plan.files_to_modify, list)
        assert isinstance(plan.breaking_change_risks, list)
        assert isinstance(plan.development_tasks, list)
        assert plan.created_at  # ISO 8601

    def test_plan_sections_populated(self):
        plan = _parse_plan_response(_SAMPLE_LLM_JSON, "budget feature")
        assert len(plan.relevant_components) == 2
        assert len(plan.missing_components) == 1
        assert len(plan.files_to_modify) == 1
        assert len(plan.breaking_change_risks) == 1
        assert len(plan.development_tasks) == 3

    def test_plan_created_at_is_iso8601(self):
        plan = _parse_plan_response(_SAMPLE_LLM_JSON, "budget feature")
        # Should parse without error
        datetime.fromisoformat(plan.created_at)

    def test_plan_request_summary_from_llm(self):
        plan = _parse_plan_response(_SAMPLE_LLM_JSON, "budget feature")
        assert plan.request_summary == "Add a budget tracking feature"

    def test_plan_fallback_on_invalid_json(self):
        plan = _parse_plan_response("not valid json at all", "my feature")
        assert plan.request_summary == "my feature"
        assert len(plan.development_tasks) == 1
        assert plan.development_tasks[0].attribution == "llm_assumption"

    def test_plan_handles_markdown_fenced_json(self):
        fenced = f"```json\n{_SAMPLE_LLM_JSON}\n```"
        plan = _parse_plan_response(fenced, "budget feature")
        assert plan.request_summary == "Add a budget tracking feature"
        assert len(plan.relevant_components) == 2


# ---------------------------------------------------------------------------
# Attribution validation
# ---------------------------------------------------------------------------

class TestAttribution:
    """Every claim must have a valid source attribution."""

    def test_all_claims_have_valid_attribution(self):
        plan = _parse_plan_response(_SAMPLE_LLM_JSON, "budget feature")
        all_claims = (
            plan.relevant_components
            + plan.missing_components
            + plan.files_to_modify
            + plan.breaking_change_risks
            + plan.development_tasks
        )
        for claim in all_claims:
            assert claim.attribution in VALID_ATTRIBUTIONS, (
                f"Invalid attribution: {claim.attribution}"
            )

    def test_invalid_attribution_defaults_to_llm_assumption(self):
        raw = [{"text": "something", "attribution": "made_up_source"}]
        claims = _parse_claims(raw)
        assert claims[0].attribution == "llm_assumption"

    def test_source_path_preserved(self):
        plan = _parse_plan_response(_SAMPLE_LLM_JSON, "budget feature")
        # First relevant component has a source_path
        assert plan.relevant_components[0].source_path == "src/services/tasks.py"
        # Second one has None
        assert plan.relevant_components[1].source_path is None

    def test_null_string_source_path_becomes_none(self):
        raw = [{"text": "x", "attribution": "indexed_fact", "source_path": "null"}]
        claims = _parse_claims(raw)
        assert claims[0].source_path is None

    def test_empty_source_path_becomes_none(self):
        raw = [{"text": "x", "attribution": "indexed_fact", "source_path": ""}]
        claims = _parse_claims(raw)
        assert claims[0].source_path is None


# ---------------------------------------------------------------------------
# Markdown persistence
# ---------------------------------------------------------------------------

class TestPlanPersistence:
    """Plans must be saved as Markdown files."""

    def test_save_creates_markdown_file(self, tmp_path: Path):
        plan = _parse_plan_response(_SAMPLE_LLM_JSON, "budget feature")
        with patch("src.services.feature_planner._resolve_plans_dir", return_value=tmp_path):
            path = save_plan_markdown(plan, "budget tracking")
        assert path.exists()
        assert path.suffix == ".md"
        content = path.read_text(encoding="utf-8")
        assert "budget" in content.lower()

    def test_saved_file_contains_all_sections(self, tmp_path: Path):
        plan = _parse_plan_response(_SAMPLE_LLM_JSON, "budget feature")
        with patch("src.services.feature_planner._resolve_plans_dir", return_value=tmp_path):
            path = save_plan_markdown(plan, "budget tracking")
        content = path.read_text(encoding="utf-8")
        assert "Relevant Components" in content
        assert "Missing Components" in content
        assert "Files to Modify" in content
        assert "Breaking Change Risks" in content
        assert "Development Tasks" in content

    def test_saved_file_contains_attributions(self, tmp_path: Path):
        plan = _parse_plan_response(_SAMPLE_LLM_JSON, "budget feature")
        with patch("src.services.feature_planner._resolve_plans_dir", return_value=tmp_path):
            path = save_plan_markdown(plan, "budget tracking")
        content = path.read_text(encoding="utf-8")
        assert "[indexed_fact]" in content
        assert "[inferred_pattern]" in content
        assert "[llm_assumption]" in content

    def test_filename_contains_date_and_feature(self, tmp_path: Path):
        plan = _parse_plan_response(_SAMPLE_LLM_JSON, "budget feature")
        with patch("src.services.feature_planner._resolve_plans_dir", return_value=tmp_path):
            path = save_plan_markdown(plan, "budget tracking")
        assert "budget" in path.name.lower()
        # Filename starts with date pattern YYYYMMDD
        assert path.name[:8].isdigit()

    def test_empty_sections_omitted(self, tmp_path: Path):
        plan = Plan(
            request_summary="minimal plan",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        with patch("src.services.feature_planner._resolve_plans_dir", return_value=tmp_path):
            path = save_plan_markdown(plan, "minimal")
        content = path.read_text(encoding="utf-8")
        assert "Relevant Components" not in content
        assert "minimal plan" in content


# ---------------------------------------------------------------------------
# WhatsApp summary
# ---------------------------------------------------------------------------

class TestPlanSummary:
    def test_summary_contains_counts(self):
        plan = _parse_plan_response(_SAMPLE_LLM_JSON, "budget feature")
        summary = plan_summary(plan)
        assert "2" in summary  # relevant_components
        assert "1" in summary  # missing_components
        assert "3" in summary  # development_tasks

    def test_summary_contains_request(self):
        plan = _parse_plan_response(_SAMPLE_LLM_JSON, "budget feature")
        summary = plan_summary(plan)
        assert "budget" in summary.lower()


# ---------------------------------------------------------------------------
# Retrieval-based context selection (via generate_plan)
# ---------------------------------------------------------------------------

class TestGeneratePlan:
    """generate_plan should use retrieve_relevant_context, not full index."""

    @pytest.mark.asyncio
    async def test_generate_plan_calls_retrieve_context(self):
        mock_response = MagicMock()
        mock_response.text = _SAMPLE_LLM_JSON

        with patch("src.services.feature_planner.is_stale", return_value=False), \
             patch("src.services.feature_planner.retrieve_relevant_context", return_value=[
                 {"layer": "skill", "name": "task"}
             ]) as mock_retrieve, \
             patch("src.services.feature_planner.BedrockClient") as MockClient:
            instance = MockClient.return_value
            instance.converse = AsyncMock(return_value=mock_response)

            from src.services.feature_planner import generate_plan
            plan = await generate_plan("add budget tracking")

            mock_retrieve.assert_called_once()
            assert plan.request_summary == "Add a budget tracking feature"

    @pytest.mark.asyncio
    async def test_generate_plan_triggers_reindex_when_stale(self):
        mock_response = MagicMock()
        mock_response.text = _SAMPLE_LLM_JSON

        with patch("src.services.feature_planner.is_stale", return_value=True), \
             patch("src.services.feature_planner.build_index") as mock_build, \
             patch("src.services.feature_planner.retrieve_relevant_context", return_value=[]), \
             patch("src.services.feature_planner.BedrockClient") as MockClient:
            instance = MockClient.return_value
            instance.converse = AsyncMock(return_value=mock_response)

            from src.services.feature_planner import generate_plan
            plan = await generate_plan("add budget tracking")

            mock_build.assert_called_once()


# ---------------------------------------------------------------------------
# DevSkill._handle_plan wiring (Task 6.3)
# ---------------------------------------------------------------------------

class TestDevSkillPlanAction:
    """Plan action in DevSkill should call generate_plan and log audit."""

    def test_plan_empty_request_rejected(self):
        skill = DevSkill()
        db = MagicMock(spec=Session)
        result = skill.execute(
            db, _member(), Command(skill="dev", action="plan", params={"feature_request": ""}, raw_text=""),
        )
        assert result.success is False
        assert "פיצ׳ר" in result.message

    def test_plan_calls_generate_plan_and_saves(self):
        skill = DevSkill()
        db = MagicMock(spec=Session)
        plan = _parse_plan_response(_SAMPLE_LLM_JSON, "budget feature")

        with patch("src.skills.dev_skill.audit") as mock_audit, \
             patch("src.services.feature_planner.generate_plan", new_callable=AsyncMock, return_value=plan) as mock_gen, \
             patch("src.services.feature_planner.save_plan_markdown", return_value=Path("/tmp/plan.md")) as mock_save:
            result = skill.execute(
                db, _member(),
                Command(skill="dev", action="plan", params={"feature_request": "add budget"}),
            )

        assert result.success is True
        assert "plan.md" in result.message
        mock_audit.log_action.assert_called_once()
        call_kwargs = mock_audit.log_action.call_args
        # Check resource_type="dev" and action="plan"
        assert "dev" in str(call_kwargs)
        assert "plan" in str(call_kwargs)

    def test_plan_failure_returns_error(self):
        skill = DevSkill()
        db = MagicMock(spec=Session)

        with patch("src.services.feature_planner.generate_plan", new_callable=AsyncMock, side_effect=RuntimeError("LLM down")):
            result = skill.execute(
                db, _member(),
                Command(skill="dev", action="plan", params={"feature_request": "add budget"}),
            )

        assert result.success is False
        assert "נכשל" in result.message

    def test_plan_non_admin_denied(self):
        skill = DevSkill()
        db = MagicMock(spec=Session)
        result = skill.execute(
            db, _member(is_admin=False),
            Command(skill="dev", action="plan", params={"feature_request": "add budget"}),
        )
        assert result.success is False
        assert "הרשאה" in result.message


# ---------------------------------------------------------------------------
# Render helpers
# ---------------------------------------------------------------------------

class TestRenderClaims:
    def test_render_empty_list_returns_empty(self):
        assert _render_claims_markdown([], "Header") == ""

    def test_render_includes_header(self):
        claims = [AttributedClaim(text="test", attribution="indexed_fact")]
        result = _render_claims_markdown(claims, "My Section")
        assert "## My Section" in result

    def test_render_includes_attribution_tag(self):
        claims = [AttributedClaim(text="test claim", attribution="inferred_pattern")]
        result = _render_claims_markdown(claims, "Section")
        assert "[inferred_pattern]" in result

    def test_render_includes_source_path(self):
        claims = [AttributedClaim(text="test", attribution="indexed_fact", source_path="src/foo.py")]
        result = _render_claims_markdown(claims, "Section")
        assert "src/foo.py" in result
