"""Unit tests for RecurringSkill — create, list, delete recurring patterns."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from src.models.schema import ConversationState, FamilyMember, RecurringPattern
from src.prompts.personality import TEMPLATES
from src.skills.base_skill import Command, Result
from src.skills.recurring_skill import (
    FREQUENCY_MAP,
    RecurringSkill,
    _next_due_date,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _member(**overrides) -> MagicMock:
    m = MagicMock(spec=FamilyMember)
    m.id = overrides.get("id", uuid.uuid4())
    m.name = overrides.get("name", "Test Parent")
    m.phone = overrides.get("phone", "+972501234567")
    m.role = overrides.get("role", "parent")
    m.is_active = True
    return m


def _pattern(**overrides) -> MagicMock:
    p = MagicMock(spec=RecurringPattern)
    p.id = overrides.get("id", uuid.uuid4())
    p.title = overrides.get("title", "ארנונה")
    p.frequency = overrides.get("frequency", "monthly")
    p.next_due_date = overrides.get("next_due_date", date.today() + timedelta(days=30))
    p.is_active = overrides.get("is_active", True)
    p.assigned_to = overrides.get("assigned_to", uuid.uuid4())
    return p


def _state(context: dict | None = None) -> MagicMock:
    s = MagicMock(spec=ConversationState)
    s.context = context or {}
    return s


# ---------------------------------------------------------------------------
# Class structure
# ---------------------------------------------------------------------------

class TestRecurringSkillStructure:
    def test_name(self):
        assert RecurringSkill().name == "recurring"

    def test_description_is_hebrew(self):
        desc = RecurringSkill().description
        assert "תזכורות" in desc

    def test_commands_count(self):
        assert len(RecurringSkill().commands) == 4

    def test_get_help_returns_string(self):
        assert isinstance(RecurringSkill().get_help(), str)

    def test_execute_unknown_action(self, mock_db: MagicMock):
        skill = RecurringSkill()
        member = _member()
        cmd = Command(skill="recurring", action="unknown", params={})
        result = skill.execute(mock_db, member, cmd)
        assert not result.success


# ---------------------------------------------------------------------------
# Frequency parsing / next_due_date
# ---------------------------------------------------------------------------

class TestFrequencyParsing:
    def test_hebrew_daily(self):
        assert FREQUENCY_MAP["יומי"] == "daily"

    def test_hebrew_weekly(self):
        assert FREQUENCY_MAP["שבועי"] == "weekly"

    def test_hebrew_monthly(self):
        assert FREQUENCY_MAP["חודשי"] == "monthly"

    def test_hebrew_yearly(self):
        assert FREQUENCY_MAP["שנתי"] == "yearly"

    def test_next_due_daily(self):
        today = date(2026, 3, 18)
        assert _next_due_date("daily", today) == date(2026, 3, 19)

    def test_next_due_weekly(self):
        today = date(2026, 3, 18)
        assert _next_due_date("weekly", today) == date(2026, 3, 25)

    def test_next_due_monthly(self):
        today = date(2026, 1, 15)
        assert _next_due_date("monthly", today) == date(2026, 2, 15)

    def test_next_due_yearly(self):
        today = date(2026, 3, 18)
        assert _next_due_date("yearly", today) == date(2027, 3, 18)

    def test_next_due_unknown_defaults_monthly(self):
        today = date(2026, 1, 15)
        assert _next_due_date("unknown", today) == date(2026, 2, 15)


# ---------------------------------------------------------------------------
# _create
# ---------------------------------------------------------------------------

class TestCreate:
    @patch("src.skills.recurring_skill.recurring.create_pattern")
    @patch("src.skills.recurring_skill.check_perm", return_value=None)
    def test_create_happy_path(self, _perm, mock_create, mock_db: MagicMock):
        pattern = _pattern(title="ארנונה", frequency="monthly")
        mock_create.return_value = pattern

        skill = RecurringSkill()
        member = _member()
        cmd = Command(skill="recurring", action="create", params={"title": "ארנונה, חודשי"})
        result = skill.execute(mock_db, member, cmd)

        assert result.success
        assert result.entity_type == "recurring_pattern"
        assert result.entity_id == pattern.id
        assert result.action == "created"
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args
        assert call_kwargs[0][1] == "ארנונה"  # title
        assert call_kwargs[0][2] == "monthly"  # frequency

    @patch("src.skills.recurring_skill.recurring.create_pattern")
    @patch("src.skills.recurring_skill.check_perm", return_value=None)
    def test_create_daily_frequency(self, _perm, mock_create, mock_db: MagicMock):
        pattern = _pattern(frequency="daily")
        mock_create.return_value = pattern

        skill = RecurringSkill()
        member = _member()
        cmd = Command(skill="recurring", action="create", params={"title": "ספורט, יומי"})
        result = skill.execute(mock_db, member, cmd)

        assert result.success
        call_kwargs = mock_create.call_args
        assert call_kwargs[0][2] == "daily"

    @patch("src.skills.recurring_skill.recurring.create_pattern")
    @patch("src.skills.recurring_skill.check_perm", return_value=None)
    def test_create_no_frequency_defaults_monthly(self, _perm, mock_create, mock_db: MagicMock):
        pattern = _pattern(frequency="monthly")
        mock_create.return_value = pattern

        skill = RecurringSkill()
        member = _member()
        cmd = Command(skill="recurring", action="create", params={"title": "ארנונה"})
        result = skill.execute(mock_db, member, cmd)

        assert result.success
        call_kwargs = mock_create.call_args
        assert call_kwargs[0][2] == "monthly"

    @patch("src.skills.recurring_skill.check_perm")
    def test_create_permission_denied(self, mock_perm, mock_db: MagicMock):
        mock_perm.return_value = Result(success=False, message=TEMPLATES["permission_denied"])

        skill = RecurringSkill()
        member = _member()
        cmd = Command(skill="recurring", action="create", params={"title": "ארנונה, חודשי"})
        result = skill.execute(mock_db, member, cmd)

        assert not result.success
        assert TEMPLATES["permission_denied"] in result.message

    @patch("src.skills.recurring_skill.recurring.create_pattern")
    @patch("src.skills.recurring_skill.check_perm", return_value=None)
    def test_create_response_uses_template(self, _perm, mock_create, mock_db: MagicMock):
        pattern = _pattern(title="ארנונה")
        mock_create.return_value = pattern

        skill = RecurringSkill()
        member = _member()
        cmd = Command(skill="recurring", action="create", params={"title": "ארנונה, חודשי"})
        result = skill.execute(mock_db, member, cmd)

        assert "ארנונה" in result.message
        assert "תזכורת חוזרת" in result.message


# ---------------------------------------------------------------------------
# _list
# ---------------------------------------------------------------------------

class TestList:
    @patch("src.skills.recurring_skill.update_state")
    @patch("src.skills.recurring_skill.recurring.list_patterns")
    @patch("src.skills.recurring_skill.check_perm", return_value=None)
    def test_list_happy_path(self, _perm, mock_list, mock_update, mock_db: MagicMock):
        patterns = [_pattern(title="ארנונה"), _pattern(title="ביטוח")]
        mock_list.return_value = patterns

        skill = RecurringSkill()
        member = _member()
        cmd = Command(skill="recurring", action="list", params={})
        result = skill.execute(mock_db, member, cmd)

        assert result.success
        assert "ארנונה" in result.message
        mock_update.assert_called_once()

    @patch("src.skills.recurring_skill.update_state")
    @patch("src.skills.recurring_skill.recurring.list_patterns")
    @patch("src.skills.recurring_skill.check_perm", return_value=None)
    def test_list_empty(self, _perm, mock_list, mock_update, mock_db: MagicMock):
        mock_list.return_value = []

        skill = RecurringSkill()
        member = _member()
        cmd = Command(skill="recurring", action="list", params={})
        result = skill.execute(mock_db, member, cmd)

        assert result.success
        assert result.message == TEMPLATES["recurring_list_empty"]

    @patch("src.skills.recurring_skill.check_perm")
    def test_list_permission_denied(self, mock_perm, mock_db: MagicMock):
        mock_perm.return_value = Result(success=False, message=TEMPLATES["permission_denied"])

        skill = RecurringSkill()
        member = _member()
        cmd = Command(skill="recurring", action="list", params={})
        result = skill.execute(mock_db, member, cmd)

        assert not result.success

    @patch("src.skills.recurring_skill.update_state")
    @patch("src.skills.recurring_skill.recurring.list_patterns")
    @patch("src.skills.recurring_skill.check_perm", return_value=None)
    def test_list_stores_pattern_order(self, _perm, mock_list, mock_update, mock_db: MagicMock):
        p1 = _pattern()
        p2 = _pattern()
        mock_list.return_value = [p1, p2]

        skill = RecurringSkill()
        member = _member()
        cmd = Command(skill="recurring", action="list", params={})
        skill.execute(mock_db, member, cmd)

        call_kwargs = mock_update.call_args
        ctx = call_kwargs[1]["context"]
        assert "pattern_list_order" in ctx
        assert len(ctx["pattern_list_order"]) == 2


# ---------------------------------------------------------------------------
# _delete
# ---------------------------------------------------------------------------

class TestDelete:
    @patch("src.skills.recurring_skill.set_pending_confirmation")
    @patch("src.skills.recurring_skill.get_state")
    @patch("src.skills.recurring_skill.check_perm", return_value=None)
    def test_delete_sets_confirmation(self, _perm, mock_state, mock_confirm, mock_db: MagicMock):
        pid = uuid.uuid4()
        mock_state.return_value = _state(context={"pattern_list_order": [str(pid)]})
        pattern = _pattern(id=pid, title="ארנונה")
        mock_db.query.return_value.filter.return_value.first.return_value = pattern

        skill = RecurringSkill()
        member = _member()
        cmd = Command(skill="recurring", action="delete", params={"index": "1"})
        result = skill.execute(mock_db, member, cmd)

        assert result.success
        assert "ארנונה" in result.message
        mock_confirm.assert_called_once()

    @patch("src.skills.recurring_skill.get_state")
    @patch("src.skills.recurring_skill.check_perm", return_value=None)
    def test_delete_no_list_first(self, _perm, mock_state, mock_db: MagicMock):
        mock_state.return_value = _state(context={})

        skill = RecurringSkill()
        member = _member()
        cmd = Command(skill="recurring", action="delete", params={"index": "1"})
        result = skill.execute(mock_db, member, cmd)

        assert not result.success
        assert result.message == TEMPLATES["need_list_first"]

    @patch("src.skills.recurring_skill.get_state")
    @patch("src.skills.recurring_skill.check_perm", return_value=None)
    def test_delete_out_of_range(self, _perm, mock_state, mock_db: MagicMock):
        mock_state.return_value = _state(context={"pattern_list_order": [str(uuid.uuid4())]})

        skill = RecurringSkill()
        member = _member()
        cmd = Command(skill="recurring", action="delete", params={"index": "5"})
        result = skill.execute(mock_db, member, cmd)

        assert not result.success
        assert result.message == TEMPLATES["recurring_not_found"]

    @patch("src.skills.recurring_skill.recurring.deactivate_pattern")
    @patch("src.skills.recurring_skill.check_perm", return_value=None)
    def test_delete_confirmed_redispatch(self, _perm, mock_deactivate, mock_db: MagicMock):
        pid = uuid.uuid4()
        pattern = _pattern(id=pid, title="ארנונה", is_active=False)
        mock_deactivate.return_value = pattern

        skill = RecurringSkill()
        member = _member()
        cmd = Command(skill="recurring", action="delete", params={"pattern_id": str(pid)})
        result = skill.execute(mock_db, member, cmd)

        assert result.success
        assert result.entity_type == "recurring_pattern"
        assert result.entity_id == pid
        assert result.action == "deleted"
        mock_deactivate.assert_called_once_with(mock_db, pid)

    @patch("src.skills.recurring_skill.recurring.deactivate_pattern")
    @patch("src.skills.recurring_skill.check_perm", return_value=None)
    def test_delete_confirmed_not_found(self, _perm, mock_deactivate, mock_db: MagicMock):
        mock_deactivate.return_value = None

        skill = RecurringSkill()
        member = _member()
        cmd = Command(skill="recurring", action="delete", params={"pattern_id": str(uuid.uuid4())})
        result = skill.execute(mock_db, member, cmd)

        assert not result.success
        assert result.message == TEMPLATES["recurring_not_found"]

    @patch("src.skills.recurring_skill.check_perm")
    def test_delete_permission_denied(self, mock_perm, mock_db: MagicMock):
        mock_perm.return_value = Result(success=False, message=TEMPLATES["permission_denied"])

        skill = RecurringSkill()
        member = _member()
        cmd = Command(skill="recurring", action="delete", params={"index": "1"})
        result = skill.execute(mock_db, member, cmd)

        assert not result.success


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------

class TestVerify:
    def test_verify_created_active(self, mock_db: MagicMock):
        pid = uuid.uuid4()
        pattern = _pattern(id=pid, is_active=True)
        mock_db.query.return_value.filter.return_value.first.return_value = pattern

        skill = RecurringSkill()
        result = Result(success=True, message="ok", entity_type="recurring_pattern", entity_id=pid, action="created")
        assert skill.verify(mock_db, result) is True

    def test_verify_created_inactive_fails(self, mock_db: MagicMock):
        pid = uuid.uuid4()
        pattern = _pattern(id=pid, is_active=False)
        mock_db.query.return_value.filter.return_value.first.return_value = pattern

        skill = RecurringSkill()
        result = Result(success=True, message="ok", entity_type="recurring_pattern", entity_id=pid, action="created")
        assert skill.verify(mock_db, result) is False

    def test_verify_deleted_inactive(self, mock_db: MagicMock):
        pid = uuid.uuid4()
        pattern = _pattern(id=pid, is_active=False)
        mock_db.query.return_value.filter.return_value.first.return_value = pattern

        skill = RecurringSkill()
        result = Result(success=True, message="ok", entity_type="recurring_pattern", entity_id=pid, action="deleted")
        assert skill.verify(mock_db, result) is True

    def test_verify_deleted_still_active_fails(self, mock_db: MagicMock):
        pid = uuid.uuid4()
        pattern = _pattern(id=pid, is_active=True)
        mock_db.query.return_value.filter.return_value.first.return_value = pattern

        skill = RecurringSkill()
        result = Result(success=True, message="ok", entity_type="recurring_pattern", entity_id=pid, action="deleted")
        assert skill.verify(mock_db, result) is False

    def test_verify_no_entity_id(self, mock_db: MagicMock):
        skill = RecurringSkill()
        result = Result(success=True, message="ok")
        assert skill.verify(mock_db, result) is True

    def test_verify_pattern_not_found(self, mock_db: MagicMock):
        pid = uuid.uuid4()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        skill = RecurringSkill()
        result = Result(success=True, message="ok", entity_type="recurring_pattern", entity_id=pid, action="created")
        assert skill.verify(mock_db, result) is False
