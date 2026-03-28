"""Tests for MorningSkill — briefing and summary actions."""

import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from src.models.schema import FamilyMember, RecurringPattern
from src.prompts.personality import TEMPLATES
from src.skills.base_skill import Command, Result
from src.skills.morning_skill import MorningSkill


@pytest.fixture()
def skill():
    return MorningSkill()


@pytest.fixture()
def parent_member():
    m = MagicMock(spec=FamilyMember)
    m.id = uuid.uuid4()
    m.name = "אבא"
    m.phone = "+972501234567"
    m.role = "parent"
    m.is_active = True
    return m


@pytest.fixture()
def child_member():
    m = MagicMock(spec=FamilyMember)
    m.id = uuid.uuid4()
    m.name = "ילד"
    m.phone = "+972501234568"
    m.role = "child"
    m.is_active = True
    return m


# ------------------------------------------------------------------
# Skill metadata
# ------------------------------------------------------------------


def test_name(skill):
    assert skill.name == "morning"


def test_description(skill):
    assert skill.description == "סיכום בוקר ודוחות"


def test_commands_count(skill):
    assert len(skill.commands) == 3


def test_commands_briefing_patterns(skill):
    pattern, action = skill.commands[0]
    assert action == "briefing"
    for text in ["בוקר", "morning", "סיכום בוקר"]:
        assert pattern.match(text), f"Pattern should match '{text}'"


def test_commands_status_patterns(skill):
    pattern, action = skill.commands[1]
    assert action == "status"
    for text in ["סטטוס", "status"]:
        assert pattern.match(text), f"Pattern should match '{text}'"


def test_commands_summary_patterns(skill):
    pattern, action = skill.commands[2]
    assert action == "summary"
    for text in ["דוח", "report", "סיכום"]:
        assert pattern.match(text), f"Pattern should match '{text}'"


def test_get_help(skill):
    help_text = skill.get_help()
    assert "בוקר" in help_text
    assert "דוח" in help_text


# ------------------------------------------------------------------
# Briefing
# ------------------------------------------------------------------


def _setup_briefing_db(mock_db, task_count=3, recurring_count=1, doc_count=2, bug_count=1, next_pattern=None):
    """Wire up mock_db.query(...).filter(...).count() chains for briefing."""
    count_results = {
        "task": task_count,
        "recurring_count": recurring_count,
        "doc": doc_count,
        "bug": bug_count,
    }

    call_index = {"i": 0}

    def make_query(model):
        q = MagicMock()
        idx = call_index["i"]
        call_index["i"] += 1

        if idx == 0:  # Task count
            q.filter.return_value.count.return_value = count_results["task"]
        elif idx == 1:  # RecurringPattern count
            q.filter.return_value.count.return_value = count_results["recurring_count"]
        elif idx == 2:  # Document count
            q.filter.return_value.filter.return_value = q.filter.return_value
            q.filter.return_value.count.return_value = count_results["doc"]
        elif idx == 3:  # BugReport count
            q.filter.return_value.count.return_value = count_results["bug"]
        elif idx == 4:  # RecurringPattern next upcoming
            q.filter.return_value.order_by.return_value.first.return_value = next_pattern
        return q

    mock_db.query.side_effect = make_query
    return mock_db


def test_briefing_parent_includes_bugs(skill, parent_member):
    """Parent role should see the bugs section."""
    mock_db = MagicMock(spec=Session)
    _setup_briefing_db(mock_db, task_count=5, recurring_count=2, doc_count=1, bug_count=3)

    cmd = Command(skill="morning", action="briefing", params={})
    result = skill.execute(mock_db, parent_member, cmd)

    assert result.success is True
    assert parent_member.name in result.message
    assert "5" in result.message  # task count
    assert "1" in result.message  # doc count
    assert "3" in result.message  # bug count


def test_briefing_child_hides_bugs(skill, child_member):
    """Non-parent role should NOT see the bugs section."""
    mock_db = MagicMock(spec=Session)
    _setup_briefing_db(mock_db, task_count=2, recurring_count=0, doc_count=0, bug_count=5)

    cmd = Command(skill="morning", action="briefing", params={})
    result = skill.execute(mock_db, child_member, cmd)

    assert result.success is True
    assert child_member.name in result.message
    # Bugs section should not appear for child
    assert "🐛" not in result.message


def test_briefing_with_next_recurring(skill, parent_member):
    """When there's a next recurring pattern, show its title and days."""
    mock_db = MagicMock(spec=Session)
    pattern = MagicMock(spec=RecurringPattern)
    pattern.title = "תשלום חשמל"
    pattern.next_due_date = date.today() + timedelta(days=3)

    _setup_briefing_db(mock_db, task_count=1, recurring_count=1, doc_count=0, bug_count=0, next_pattern=pattern)

    cmd = Command(skill="morning", action="briefing", params={})
    result = skill.execute(mock_db, parent_member, cmd)

    assert result.success is True
    assert "תשלום חשמל" in result.message


def test_briefing_no_recurring(skill, parent_member):
    """When no recurring patterns, show fallback."""
    mock_db = MagicMock(spec=Session)
    _setup_briefing_db(mock_db, task_count=0, recurring_count=0, doc_count=0, bug_count=0, next_pattern=None)

    cmd = Command(skill="morning", action="briefing", params={})
    result = skill.execute(mock_db, parent_member, cmd)

    assert result.success is True
    assert "—" in result.message or "0" in result.message


def test_briefing_zero_counts(skill, parent_member):
    """All zero counts should still produce a valid briefing."""
    mock_db = MagicMock(spec=Session)
    _setup_briefing_db(mock_db, task_count=0, recurring_count=0, doc_count=0, bug_count=0, next_pattern=None)

    cmd = Command(skill="morning", action="briefing", params={})
    result = skill.execute(mock_db, parent_member, cmd)

    assert result.success is True
    assert parent_member.name in result.message


# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------


@patch("src.skills.morning_skill.check_perm")
def test_summary_permission_denied(mock_check_perm, skill, parent_member):
    """Summary should deny access when finance/read permission is missing."""
    mock_check_perm.return_value = Result(
        success=False, message=TEMPLATES["permission_denied"]
    )
    mock_db = MagicMock(spec=Session)

    cmd = Command(skill="morning", action="summary", params={})
    result = skill.execute(mock_db, parent_member, cmd)

    assert result.success is False
    assert result.message == TEMPLATES["permission_denied"]
    mock_check_perm.assert_called_once_with(mock_db, parent_member, "finance", "read")


@patch("src.skills.morning_skill.check_perm")
def test_summary_with_permission(mock_check_perm, skill, parent_member):
    """Summary should return no_report_yet when permission is granted."""
    mock_check_perm.return_value = None
    mock_db = MagicMock(spec=Session)

    cmd = Command(skill="morning", action="summary", params={})
    result = skill.execute(mock_db, parent_member, cmd)

    assert result.success is True
    assert result.message == TEMPLATES["no_report_yet"]


# ------------------------------------------------------------------
# Verify
# ------------------------------------------------------------------


def test_verify_always_true(skill):
    """Verify should always return True for read-only operations."""
    mock_db = MagicMock(spec=Session)
    result = Result(success=True, message="test")
    assert skill.verify(mock_db, result) is True


def test_verify_with_entity_id(skill):
    """Verify should still return True even with entity_id (read-only)."""
    mock_db = MagicMock(spec=Session)
    result = Result(success=True, message="test", entity_id=uuid.uuid4())
    assert skill.verify(mock_db, result) is True


# ------------------------------------------------------------------
# Execute dispatch
# ------------------------------------------------------------------


def test_execute_unknown_action(skill, parent_member):
    """Unknown action should return error_fallback."""
    mock_db = MagicMock(spec=Session)
    cmd = Command(skill="morning", action="unknown", params={})
    result = skill.execute(mock_db, parent_member, cmd)

    assert result.success is False
    assert result.message == TEMPLATES["error_fallback"]
