"""Unit tests for BugSkill — report, list, verify."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from src.models.schema import BugReport, FamilyMember
from src.prompts.personality import TEMPLATES
from src.skills.base_skill import Command, Result
from src.skills.bug_skill import BugSkill


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


def _bug(**overrides) -> MagicMock:
    b = MagicMock(spec=BugReport)
    b.id = overrides.get("id", uuid.uuid4())
    b.description = overrides.get("description", "הכפתור לא עובד")
    b.status = overrides.get("status", "open")
    b.reported_by = overrides.get("reported_by", uuid.uuid4())
    b.created_at = overrides.get("created_at", datetime.now(timezone.utc))
    return b


# ---------------------------------------------------------------------------
# Structure tests
# ---------------------------------------------------------------------------

class TestBugSkillStructure:
    def test_name(self):
        assert BugSkill().name == "bug"

    def test_description_is_hebrew(self):
        desc = BugSkill().description
        assert isinstance(desc, str)
        assert len(desc) > 0

    def test_commands_count(self):
        # Two report patterns (באג, bug) + one list pattern
        assert len(BugSkill().commands) == 3

    def test_get_help_returns_string(self):
        help_text = BugSkill().get_help()
        assert isinstance(help_text, str)
        assert "באג" in help_text

    def test_execute_unknown_action(self, mock_db: MagicMock):
        skill = BugSkill()
        member = _member()
        cmd = Command(skill="bug", action="unknown", params={})
        result = skill.execute(mock_db, member, cmd)
        assert not result.success
        assert result.message == TEMPLATES["error_fallback"]


# ---------------------------------------------------------------------------
# _report
# ---------------------------------------------------------------------------

class TestReport:
    @patch("src.skills.bug_skill.check_perm", return_value=None)
    def test_report_happy_path(self, _perm, mock_db: MagicMock):
        bug_id = uuid.uuid4()

        def _flush_side_effect():
            # Simulate DB assigning an id after flush
            mock_db.add.call_args[0][0].id = bug_id

        mock_db.flush.side_effect = _flush_side_effect

        skill = BugSkill()
        member = _member()
        cmd = Command(skill="bug", action="report", params={"description": "הכפתור לא עובד"})
        result = skill.execute(mock_db, member, cmd)

        assert result.success
        assert result.entity_type == "bug_report"
        assert result.entity_id == bug_id
        assert result.action == "reported"
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()

    @patch("src.skills.bug_skill.check_perm", return_value=None)
    def test_report_result_uses_template(self, _perm, mock_db: MagicMock):
        mock_db.flush.side_effect = lambda: None

        skill = BugSkill()
        member = _member()
        cmd = Command(skill="bug", action="report", params={"description": "שגיאה בדף הבית"})
        result = skill.execute(mock_db, member, cmd)

        assert result.success
        assert "שגיאה בדף הבית" in result.message

    @patch("src.skills.bug_skill.check_perm")
    def test_report_permission_denied(self, mock_perm, mock_db: MagicMock):
        mock_perm.return_value = Result(success=False, message=TEMPLATES["permission_denied"])

        skill = BugSkill()
        member = _member()
        cmd = Command(skill="bug", action="report", params={"description": "באג כלשהו"})
        result = skill.execute(mock_db, member, cmd)

        assert not result.success
        assert TEMPLATES["permission_denied"] in result.message
        mock_db.add.assert_not_called()

    @patch("src.skills.bug_skill.check_perm", return_value=None)
    def test_report_metadata_correct(self, _perm, mock_db: MagicMock):
        bug_id = uuid.uuid4()
        mock_db.flush.side_effect = lambda: setattr(
            mock_db.add.call_args[0][0], "id", bug_id
        )

        skill = BugSkill()
        member = _member()
        cmd = Command(skill="bug", action="report", params={"description": "בעיה"})
        result = skill.execute(mock_db, member, cmd)

        assert result.entity_type == "bug_report"
        assert result.entity_id == bug_id
        assert result.action == "reported"


# ---------------------------------------------------------------------------
# _list
# ---------------------------------------------------------------------------

class TestList:
    @patch("src.skills.bug_skill.check_perm", return_value=None)
    def test_list_open_bugs(self, _perm, mock_db: MagicMock):
        b1 = _bug(description="באג ראשון")
        b2 = _bug(description="באג שני")
        mock_db.query.return_value.filter.return_value.all.return_value = [b1, b2]

        skill = BugSkill()
        member = _member()
        cmd = Command(skill="bug", action="list", params={})
        result = skill.execute(mock_db, member, cmd)

        assert result.success
        assert "באג ראשון" in result.message
        assert "באג שני" in result.message

    @patch("src.skills.bug_skill.check_perm", return_value=None)
    def test_list_empty_returns_template(self, _perm, mock_db: MagicMock):
        mock_db.query.return_value.filter.return_value.all.return_value = []

        skill = BugSkill()
        member = _member()
        cmd = Command(skill="bug", action="list", params={})
        result = skill.execute(mock_db, member, cmd)

        assert result.success
        assert result.message == TEMPLATES["bug_list_empty"]

    @patch("src.skills.bug_skill.check_perm")
    def test_list_permission_denied(self, mock_perm, mock_db: MagicMock):
        mock_perm.return_value = Result(success=False, message=TEMPLATES["permission_denied"])

        skill = BugSkill()
        member = _member()
        cmd = Command(skill="bug", action="list", params={})
        result = skill.execute(mock_db, member, cmd)

        assert not result.success
        assert TEMPLATES["permission_denied"] in result.message


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------

class TestVerify:
    def test_verify_reported_bug_exists_open(self, mock_db: MagicMock):
        bug_id = uuid.uuid4()
        bug = _bug(id=bug_id, status="open")
        mock_db.query.return_value.filter.return_value.first.return_value = bug

        skill = BugSkill()
        result = Result(
            success=True, message="ok",
            entity_type="bug_report", entity_id=bug_id, action="reported",
        )
        assert skill.verify(mock_db, result) is True

    def test_verify_not_found_returns_false(self, mock_db: MagicMock):
        bug_id = uuid.uuid4()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        skill = BugSkill()
        result = Result(
            success=True, message="ok",
            entity_type="bug_report", entity_id=bug_id, action="reported",
        )
        assert skill.verify(mock_db, result) is False

    def test_verify_no_entity_id_returns_true(self, mock_db: MagicMock):
        skill = BugSkill()
        result = Result(success=True, message="ok")
        assert skill.verify(mock_db, result) is True
