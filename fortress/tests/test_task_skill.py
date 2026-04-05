"""Unit tests for TaskSkill — create, list, delete, delete_all, complete, update, verify."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from src.models.schema import ConversationState, FamilyMember, Task
from src.prompts.personality import TEMPLATES
from src.skills.base_skill import Command, Result
from src.skills.task_skill import TaskSkill


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


def _task(**overrides) -> MagicMock:
    t = MagicMock(spec=Task)
    t.id = overrides.get("id", uuid.uuid4())
    t.title = overrides.get("title", "לקנות חלב")
    t.status = overrides.get("status", "open")
    t.priority = overrides.get("priority", "normal")
    t.due_date = overrides.get("due_date", None)
    t.assigned_to = overrides.get("assigned_to", uuid.uuid4())
    t.created_by = overrides.get("created_by", uuid.uuid4())
    t.created_at = overrides.get("created_at", datetime.now(timezone.utc))
    return t


def _state(context: dict | None = None, **overrides) -> MagicMock:
    s = MagicMock(spec=ConversationState)
    s.context = context or {}
    s.last_entity_type = overrides.get("last_entity_type", None)
    s.last_entity_id = overrides.get("last_entity_id", None)
    return s


# ---------------------------------------------------------------------------
# Structure tests
# ---------------------------------------------------------------------------

class TestTaskSkillStructure:
    def test_name(self):
        assert TaskSkill().name == "task"

    def test_description_is_hebrew(self):
        desc = TaskSkill().description
        assert "משימות" in desc

    def test_commands_count(self):
        assert len(TaskSkill().commands) == 25

    def test_get_help_returns_string(self):
        help_text = TaskSkill().get_help()
        assert isinstance(help_text, str)
        assert "משימה" in help_text

    def test_execute_unknown_action(self, mock_db: MagicMock):
        skill = TaskSkill()
        member = _member()
        cmd = Command(skill="task", action="unknown", params={})
        result = skill.execute(mock_db, member, cmd)
        assert not result.success


# ---------------------------------------------------------------------------
# _create
# ---------------------------------------------------------------------------

class TestCreate:
    @patch("src.skills.task_skill.tasks.create_task")
    @patch("src.skills.task_skill.check_perm", return_value=None)
    def test_create_happy_path(self, _perm, mock_create, mock_db: MagicMock):
        task = _task(title="לקנות חלב")
        mock_create.return_value = task
        # No duplicate found
        mock_db.query.return_value.filter.return_value.first.return_value = None

        skill = TaskSkill()
        member = _member()
        cmd = Command(skill="task", action="create", params={"title": "לקנות חלב"})
        result = skill.execute(mock_db, member, cmd)

        assert result.success
        assert result.entity_type == "task"
        assert result.entity_id == task.id
        assert result.action == "created"
        mock_create.assert_called_once()

    @patch("src.skills.task_skill.tasks.create_task")
    @patch("src.skills.task_skill.check_perm", return_value=None)
    def test_create_with_explicit_assignee(self, _perm, mock_create, mock_db: MagicMock):
        task = _task(title="לברר קוד לגן")
        assignee = _member(name="חן")
        mock_create.return_value = task
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.query.return_value.filter.return_value.all.return_value = [assignee]

        skill = TaskSkill()
        member = _member(name="שגב")
        cmd = Command(
            skill="task",
            action="create",
            params={"title": "לברר קוד לגן", "assignee_name": "חן"},
        )
        result = skill.execute(mock_db, member, cmd)

        assert result.success
        mock_create.assert_called_once_with(
            mock_db, "לברר קוד לגן", member.id, assigned_to=assignee.id
        )
        assert "לחן" in result.message

    @patch("src.skills.task_skill.tasks.create_task")
    @patch("src.skills.task_skill.check_perm", return_value=None)
    def test_create_result_uses_template(self, _perm, mock_create, mock_db: MagicMock):
        task = _task(title="לקנות חלב")
        mock_create.return_value = task
        mock_db.query.return_value.filter.return_value.first.return_value = None

        skill = TaskSkill()
        member = _member()
        cmd = Command(skill="task", action="create", params={"title": "לקנות חלב"})
        result = skill.execute(mock_db, member, cmd)

        assert "לקנות חלב" in result.message
        assert "✅" in result.message

    @patch("src.skills.task_skill.check_perm")
    def test_create_permission_denied(self, mock_perm, mock_db: MagicMock):
        mock_perm.return_value = Result(success=False, message=TEMPLATES["permission_denied"])

        skill = TaskSkill()
        member = _member()
        cmd = Command(skill="task", action="create", params={"title": "לקנות חלב"})
        result = skill.execute(mock_db, member, cmd)

        assert not result.success
        assert TEMPLATES["permission_denied"] in result.message

    @patch("src.skills.task_skill.set_pending_confirmation")
    @patch("src.skills.task_skill.check_perm", return_value=None)
    def test_create_duplicate_detection(self, _perm, mock_confirm, mock_db: MagicMock):
        existing = _task(title="לקנות חלב")
        mock_db.query.return_value.filter.return_value.first.return_value = existing

        skill = TaskSkill()
        member = _member()
        cmd = Command(skill="task", action="create", params={"title": "לקנות חלב"})
        result = skill.execute(mock_db, member, cmd)

        assert result.success
        assert "לקנות חלב" in result.message
        mock_confirm.assert_called_once()

    @patch("src.skills.task_skill.tasks.create_task")
    @patch("src.skills.task_skill.check_perm", return_value=None)
    def test_create_without_assignee_defaults_to_sender(self, _perm, mock_create, mock_db: MagicMock):
        task = _task(title="לקנות חלב")
        mock_create.return_value = task
        mock_db.query.return_value.filter.return_value.first.return_value = None

        skill = TaskSkill()
        member = _member(name="שגב")
        cmd = Command(skill="task", action="create", params={"title": "לקנות חלב"})
        result = skill.execute(mock_db, member, cmd)

        assert result.success
        mock_create.assert_called_once_with(
            mock_db, "לקנות חלב", member.id, assigned_to=member.id
        )

    @patch("src.skills.task_skill.tasks.create_task")
    @patch("src.skills.task_skill.check_perm", return_value=None)
    def test_create_with_title_shorthand_assigns_other_member(self, _perm, mock_create, mock_db: MagicMock):
        assignee = _member(name="חן")
        task = _task(title="ניסיון ניסיון", assigned_to=assignee.id)
        mock_create.return_value = task
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.query.return_value.filter.return_value.all.return_value = [assignee]

        skill = TaskSkill()
        member = _member(name="שגב")
        cmd = Command(skill="task", action="create", params={"title": "ניסיון ניסיון", "assignee_name": "חן"})
        result = skill.execute(mock_db, member, cmd)

        assert result.success
        mock_create.assert_called_once_with(
            mock_db, "ניסיון ניסיון", member.id, assigned_to=assignee.id
        )
        assert "לחן" in result.message

    @patch("src.skills.task_skill.update_state")
    @patch("src.skills.task_skill.tasks.list_tasks")
    @patch("src.skills.task_skill.check_perm", return_value=None)
    def test_list_phrase_what_are_my_tasks(self, _perm, mock_list, mock_update, mock_db: MagicMock):
        task = _task(title="ניסיון ניסיון")
        mock_list.return_value = [task]

        skill = TaskSkill()
        member = _member(name="חן")
        cmd = Command(skill="task", action="list", params={})
        result = skill.execute(mock_db, member, cmd)

        assert result.success
        assert "ניסיון ניסיון" in result.message

# ---------------------------------------------------------------------------
# _list
# ---------------------------------------------------------------------------

class TestList:
    @patch("src.skills.task_skill.update_state")
    @patch("src.skills.task_skill.tasks.list_tasks")
    @patch("src.skills.task_skill.check_perm", return_value=None)
    def test_list_happy_path(self, _perm, mock_list, mock_update, mock_db: MagicMock):
        t1 = _task(title="לקנות חלב")
        t2 = _task(title="לשלם ארנונה")
        mock_list.return_value = [t1, t2]

        skill = TaskSkill()
        member = _member()
        cmd = Command(skill="task", action="list", params={})
        result = skill.execute(mock_db, member, cmd)

        assert result.success
        assert "לקנות חלב" in result.message
        assert "לשלם ארנונה" in result.message

    @patch("src.skills.task_skill.check_perm")
    def test_list_permission_denied(self, mock_perm, mock_db: MagicMock):
        mock_perm.return_value = Result(success=False, message=TEMPLATES["permission_denied"])

        skill = TaskSkill()
        member = _member()
        cmd = Command(skill="task", action="list", params={})
        result = skill.execute(mock_db, member, cmd)

        assert not result.success

    @patch("src.skills.task_skill.update_state")
    @patch("src.skills.task_skill.tasks.list_tasks")
    @patch("src.skills.task_skill.check_perm", return_value=None)
    def test_list_empty(self, _perm, mock_list, mock_update, mock_db: MagicMock):
        mock_list.return_value = []

        skill = TaskSkill()
        member = _member()
        cmd = Command(skill="task", action="list", params={})
        result = skill.execute(mock_db, member, cmd)

        assert result.success
        assert result.message == TEMPLATES["task_list_empty"]

    @patch("src.skills.task_skill.update_state")
    @patch("src.skills.task_skill.tasks.list_tasks")
    @patch("src.skills.task_skill.check_perm", return_value=None)
    def test_list_stores_task_list_order(self, _perm, mock_list, mock_update, mock_db: MagicMock):
        t1 = _task()
        t2 = _task()
        mock_list.return_value = [t1, t2]

        skill = TaskSkill()
        member = _member()
        cmd = Command(skill="task", action="list", params={})
        skill.execute(mock_db, member, cmd)

        call_kwargs = mock_update.call_args
        ctx = call_kwargs[1]["context"]
        assert "task_list_order" in ctx
        assert len(ctx["task_list_order"]) == 2


# ---------------------------------------------------------------------------
# _delete
# ---------------------------------------------------------------------------

class TestDelete:
    @patch("src.skills.task_skill.set_pending_confirmation")
    @patch("src.skills.task_skill.tasks.get_task")
    @patch("src.skills.task_skill.get_state")
    @patch("src.skills.task_skill.check_perm", return_value=None)
    def test_delete_by_index_sets_confirmation(self, _perm, mock_state, mock_get, mock_confirm, mock_db: MagicMock):
        tid = uuid.uuid4()
        mock_state.return_value = _state(context={"task_list_order": [str(tid)]})
        task = _task(id=tid, title="לקנות חלב")
        mock_get.return_value = task

        skill = TaskSkill()
        member = _member()
        cmd = Command(skill="task", action="delete", params={"index": "1"})
        result = skill.execute(mock_db, member, cmd)

        assert result.success
        assert "לקנות חלב" in result.message
        mock_confirm.assert_called_once()

    @patch("src.skills.task_skill.get_state")
    @patch("src.skills.task_skill.check_perm", return_value=None)
    def test_delete_missing_task_list_order(self, _perm, mock_state, mock_db: MagicMock):
        mock_state.return_value = _state(context={})

        skill = TaskSkill()
        member = _member()
        cmd = Command(skill="task", action="delete", params={"index": "1"})
        result = skill.execute(mock_db, member, cmd)

        assert not result.success
        assert result.message == TEMPLATES["need_list_first"]

    @patch("src.skills.task_skill.get_state")
    @patch("src.skills.task_skill.check_perm", return_value=None)
    def test_delete_out_of_range(self, _perm, mock_state, mock_db: MagicMock):
        mock_state.return_value = _state(context={"task_list_order": [str(uuid.uuid4())]})

        skill = TaskSkill()
        member = _member()
        cmd = Command(skill="task", action="delete", params={"index": "5"})
        result = skill.execute(mock_db, member, cmd)

        assert not result.success
        assert result.message == TEMPLATES["task_not_found"]

    @patch("src.skills.task_skill.tasks.archive_task")
    @patch("src.skills.task_skill.check_perm", return_value=None)
    def test_delete_confirmed_redispatch(self, _perm, mock_archive, mock_db: MagicMock):
        tid = uuid.uuid4()
        task = _task(id=tid, title="לקנות חלב", status="archived")
        mock_archive.return_value = task

        skill = TaskSkill()
        member = _member()
        cmd = Command(skill="task", action="delete", params={"task_id": str(tid)})
        result = skill.execute(mock_db, member, cmd)

        assert result.success
        assert result.entity_type == "task"
        assert result.entity_id == tid
        assert result.action == "deleted"
        mock_archive.assert_called_once_with(mock_db, tid)

    @patch("src.skills.task_skill.tasks.archive_task")
    @patch("src.skills.task_skill.check_perm", return_value=None)
    def test_delete_confirmed_not_found(self, _perm, mock_archive, mock_db: MagicMock):
        mock_archive.return_value = None

        skill = TaskSkill()
        member = _member()
        cmd = Command(skill="task", action="delete", params={"task_id": str(uuid.uuid4())})
        result = skill.execute(mock_db, member, cmd)

        assert not result.success
        assert result.message == TEMPLATES["task_not_found"]

    @patch("src.skills.task_skill.check_perm")
    def test_delete_permission_denied(self, mock_perm, mock_db: MagicMock):
        mock_perm.return_value = Result(success=False, message=TEMPLATES["permission_denied"])

        skill = TaskSkill()
        member = _member()
        cmd = Command(skill="task", action="delete", params={"index": "1"})
        result = skill.execute(mock_db, member, cmd)

        assert not result.success


# ---------------------------------------------------------------------------
# _delete_all
# ---------------------------------------------------------------------------

class TestDeleteAll:
    @patch("src.skills.task_skill.set_pending_confirmation")
    @patch("src.skills.task_skill.tasks.list_tasks")
    @patch("src.skills.task_skill.check_perm", return_value=None)
    def test_delete_all_confirmation_with_count(self, _perm, mock_list, mock_confirm, mock_db: MagicMock):
        t1 = _task(title="משימה 1")
        t2 = _task(title="משימה 2")
        mock_list.return_value = [t1, t2]

        skill = TaskSkill()
        member = _member()
        cmd = Command(skill="task", action="delete_all", params={})
        result = skill.execute(mock_db, member, cmd)

        assert result.success
        assert "2" in result.message
        mock_confirm.assert_called_once()

    @patch("src.skills.task_skill.check_perm")
    def test_delete_all_permission_denied(self, mock_perm, mock_db: MagicMock):
        mock_perm.return_value = Result(success=False, message=TEMPLATES["permission_denied"])

        skill = TaskSkill()
        member = _member()
        cmd = Command(skill="task", action="delete_all", params={})
        result = skill.execute(mock_db, member, cmd)

        assert not result.success

    @patch("src.skills.task_skill.tasks.list_tasks")
    @patch("src.skills.task_skill.check_perm", return_value=None)
    def test_delete_all_empty_list(self, _perm, mock_list, mock_db: MagicMock):
        mock_list.return_value = []

        skill = TaskSkill()
        member = _member()
        cmd = Command(skill="task", action="delete_all", params={})
        result = skill.execute(mock_db, member, cmd)

        assert result.success
        assert result.message == TEMPLATES["task_list_empty"]


# ---------------------------------------------------------------------------
# _complete
# ---------------------------------------------------------------------------

class TestComplete:
    @patch("src.skills.task_skill.tasks.get_task")
    @patch("src.skills.task_skill.tasks.complete_task")
    @patch("src.skills.task_skill.get_state")
    @patch("src.skills.task_skill.check_perm", return_value=None)
    def test_complete_by_index(self, _perm, mock_state, mock_complete, mock_get_task, mock_db: MagicMock):
        tid = uuid.uuid4()
        mock_state.return_value = _state(context={"task_list_order": [str(tid)]})
        open_task = _task(id=tid, title="לקנות חלב", status="open")
        done_task = _task(id=tid, title="לקנות חלב", status="done")
        mock_get_task.return_value = open_task
        mock_complete.return_value = done_task

        skill = TaskSkill()
        member = _member()
        cmd = Command(skill="task", action="complete", params={"index": "1"})
        result = skill.execute(mock_db, member, cmd)

        assert result.success
        assert result.entity_type == "task"
        assert result.entity_id == tid
        assert result.action == "completed"
        assert "לקנות חלב" in result.message

    @patch("src.skills.task_skill.tasks.complete_task")
    @patch("src.skills.task_skill.get_state")
    @patch("src.skills.task_skill.check_perm", return_value=None)
    def test_complete_by_last_entity_id(self, _perm, mock_state, mock_complete, mock_db: MagicMock):
        tid = uuid.uuid4()
        mock_state.return_value = _state(last_entity_type="task", last_entity_id=tid)
        task = _task(id=tid, title="לקנות חלב", status="done")
        mock_complete.return_value = task

        skill = TaskSkill()
        member = _member()
        cmd = Command(skill="task", action="complete", params={})
        result = skill.execute(mock_db, member, cmd)

        assert result.success
        assert result.entity_id == tid
        assert result.action == "completed"

    @patch("src.skills.task_skill.check_perm")
    def test_complete_permission_denied(self, mock_perm, mock_db: MagicMock):
        mock_perm.return_value = Result(success=False, message=TEMPLATES["permission_denied"])

        skill = TaskSkill()
        member = _member()
        cmd = Command(skill="task", action="complete", params={"index": "1"})
        result = skill.execute(mock_db, member, cmd)

        assert not result.success


# ---------------------------------------------------------------------------
# _update
# ---------------------------------------------------------------------------

class TestUpdate:
    @patch("src.skills.task_skill.tasks.get_task")
    @patch("src.skills.task_skill.get_state")
    @patch("src.skills.task_skill.check_perm", return_value=None)
    def test_update_by_index(self, _perm, mock_state, mock_get, mock_db: MagicMock):
        tid = uuid.uuid4()
        mock_state.return_value = _state(context={"task_list_order": [str(tid)]})
        task = _task(id=tid, title="לקנות חלב")
        mock_get.return_value = task

        skill = TaskSkill()
        member = _member()
        cmd = Command(skill="task", action="update", params={"index": "1", "changes": "עדיפות דחוף"})
        result = skill.execute(mock_db, member, cmd)

        assert result.success
        assert result.entity_type == "task"
        assert result.entity_id == tid
        assert result.action == "updated"

    @patch("src.skills.task_skill.tasks.get_task")
    @patch("src.skills.task_skill.get_state")
    @patch("src.skills.task_skill.check_perm", return_value=None)
    def test_update_due_date_parsing(self, _perm, mock_state, mock_get, mock_db: MagicMock):
        tid = uuid.uuid4()
        mock_state.return_value = _state(context={"task_list_order": [str(tid)]})
        task = _task(id=tid, title="לקנות חלב")
        mock_get.return_value = task

        skill = TaskSkill()
        member = _member()
        cmd = Command(skill="task", action="update", params={"index": "1", "changes": "עד 2025-03-15"})
        result = skill.execute(mock_db, member, cmd)

        assert result.success
        assert task.due_date == date(2025, 3, 15)
        assert "תאריך" in result.message

    @patch("src.skills.task_skill.tasks.get_task")
    @patch("src.skills.task_skill.get_state")
    @patch("src.skills.task_skill.check_perm", return_value=None)
    def test_update_priority_parsing(self, _perm, mock_state, mock_get, mock_db: MagicMock):
        tid = uuid.uuid4()
        mock_state.return_value = _state(context={"task_list_order": [str(tid)]})
        task = _task(id=tid, title="לקנות חלב")
        mock_get.return_value = task

        skill = TaskSkill()
        member = _member()
        cmd = Command(skill="task", action="update", params={"index": "1", "changes": "דחוף"})
        result = skill.execute(mock_db, member, cmd)

        assert result.success
        assert task.priority == "urgent"
        assert "עדיפות" in result.message

    @patch("src.skills.task_skill.tasks.get_task")
    @patch("src.skills.task_skill.get_state")
    @patch("src.skills.task_skill.check_perm", return_value=None)
    def test_update_title_parsing(self, _perm, mock_state, mock_get, mock_db: MagicMock):
        tid = uuid.uuid4()
        mock_state.return_value = _state(context={"task_list_order": [str(tid)]})
        task = _task(id=tid, title="לקנות חלב")
        mock_get.return_value = task

        skill = TaskSkill()
        member = _member()
        cmd = Command(skill="task", action="update", params={"index": "1", "changes": "כותרת לקנות לחם"})
        result = skill.execute(mock_db, member, cmd)

        assert result.success
        assert task.title == "לקנות לחם"
        assert "כותרת" in result.message

    @patch("src.skills.task_skill.check_perm")
    def test_update_permission_denied(self, mock_perm, mock_db: MagicMock):
        mock_perm.return_value = Result(success=False, message=TEMPLATES["permission_denied"])

        skill = TaskSkill()
        member = _member()
        cmd = Command(skill="task", action="update", params={"index": "1", "changes": "דחוף"})
        result = skill.execute(mock_db, member, cmd)

        assert not result.success


# ---------------------------------------------------------------------------
# _reassign
# ---------------------------------------------------------------------------

class TestReassign:
    @patch("src.skills.task_skill.tasks.reassign_task")
    @patch("src.skills.task_skill.tasks.get_task")
    @patch("src.skills.task_skill.get_state")
    @patch("src.skills.task_skill.check_perm", return_value=None)
    def test_reassign_by_index(
        self, _perm, mock_state, mock_get_task, mock_reassign, mock_db: MagicMock
    ):
        tid = uuid.uuid4()
        assignee = _member(name="חן")
        task = _task(id=tid, title="לברר קוד לגן")
        mock_state.return_value = _state(context={"task_list_order": [str(tid)]})
        mock_get_task.return_value = task
        mock_reassign.return_value = task
        mock_db.query.return_value.filter.return_value.all.return_value = [assignee]

        skill = TaskSkill()
        member = _member(name="שגב")
        cmd = Command(
            skill="task",
            action="reassign",
            params={"index": "1", "assignee_name": "חן"},
        )
        result = skill.execute(mock_db, member, cmd)

        assert result.success
        mock_reassign.assert_called_once_with(
            mock_db, tid, assignee.id, actor_id=member.id
        )
        assert "לחן" in result.message

    @patch("src.skills.task_skill.check_perm", return_value=None)
    def test_reassign_ambiguous_assignee(self, _perm, mock_db: MagicMock):
        m1 = _member(name="חן")
        m2 = _member(name="חן")
        mock_db.query.return_value.filter.return_value.all.return_value = [m1, m2]

        skill = TaskSkill()
        member = _member(name="שגב")
        cmd = Command(
            skill="task",
            action="reassign",
            params={"index": "1", "assignee_name": "חן"},
        )
        result = skill.execute(mock_db, member, cmd)

        assert not result.success
        assert "כמה" in result.message


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------

class TestVerify:
    @patch("src.skills.task_skill.tasks.get_task")
    def test_verify_created_status_open(self, mock_get, mock_db: MagicMock):
        tid = uuid.uuid4()
        task = _task(id=tid, status="open")
        mock_get.return_value = task

        skill = TaskSkill()
        result = Result(success=True, message="ok", entity_type="task", entity_id=tid, action="created")
        assert skill.verify(mock_db, result) is True

    @patch("src.skills.task_skill.tasks.get_task")
    def test_verify_deleted_status_archived(self, mock_get, mock_db: MagicMock):
        tid = uuid.uuid4()
        task = _task(id=tid, status="archived")
        mock_get.return_value = task

        skill = TaskSkill()
        result = Result(success=True, message="ok", entity_type="task", entity_id=tid, action="deleted")
        assert skill.verify(mock_db, result) is True

    @patch("src.skills.task_skill.tasks.get_task")
    def test_verify_completed_status_done(self, mock_get, mock_db: MagicMock):
        tid = uuid.uuid4()
        task = _task(id=tid, status="done")
        mock_get.return_value = task

        skill = TaskSkill()
        result = Result(success=True, message="ok", entity_type="task", entity_id=tid, action="completed")
        assert skill.verify(mock_db, result) is True

    @patch("src.skills.task_skill.tasks.get_task")
    def test_verify_updated_exists(self, mock_get, mock_db: MagicMock):
        tid = uuid.uuid4()
        task = _task(id=tid)
        mock_get.return_value = task

        skill = TaskSkill()
        result = Result(success=True, message="ok", entity_type="task", entity_id=tid, action="updated")
        assert skill.verify(mock_db, result) is True

    def test_verify_no_entity_id(self, mock_db: MagicMock):
        skill = TaskSkill()
        result = Result(success=True, message="ok")
        assert skill.verify(mock_db, result) is True

    @patch("src.skills.task_skill.tasks.get_task")
    def test_verify_not_found_returns_false(self, mock_get, mock_db: MagicMock):
        tid = uuid.uuid4()
        mock_get.return_value = None

        skill = TaskSkill()
        result = Result(success=True, message="ok", entity_type="task", entity_id=tid, action="created")
        assert skill.verify(mock_db, result) is False
