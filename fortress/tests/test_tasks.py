"""Unit tests for the task service."""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.models.schema import Task
from src.services.tasks import (
    archive_task,
    complete_task,
    create_task,
    list_tasks,
    reassign_task,
    update_task_status,
)


_ACTOR_ID = uuid.uuid4()


def _make_task(**overrides) -> MagicMock:
    """Build a mock Task with sensible defaults."""
    t = MagicMock(spec=Task)
    t.id = overrides.get("id", uuid.uuid4())
    t.title = overrides.get("title", "Buy groceries")
    t.status = overrides.get("status", "open")
    t.priority = overrides.get("priority", "normal")
    t.created_by = overrides.get("created_by", _ACTOR_ID)
    t.assigned_to = overrides.get("assigned_to", None)
    t.due_date = overrides.get("due_date", None)
    t.category = overrides.get("category", None)
    t.description = overrides.get("description", None)
    t.source_document_id = overrides.get("source_document_id", None)
    t.recurring_pattern_id = overrides.get("recurring_pattern_id", None)
    t.completed_at = overrides.get("completed_at", None)
    return t


@patch("src.services.tasks.log_action")
def test_create_task_minimal(mock_log: MagicMock, mock_db: MagicMock) -> None:
    """Create a task with only title and created_by."""
    task = create_task(mock_db, "Buy milk", _ACTOR_ID)
    mock_db.add.assert_called_once()
    mock_db.flush.assert_called()
    added = mock_db.add.call_args[0][0]
    assert added.title == "Buy milk"
    assert added.created_by == _ACTOR_ID
    mock_log.assert_called_once()


@patch("src.services.tasks.log_action")
def test_create_task_all_fields(mock_log: MagicMock, mock_db: MagicMock) -> None:
    """Create a task with all optional fields populated."""
    doc_id = uuid.uuid4()
    pattern_id = uuid.uuid4()
    assignee = uuid.uuid4()
    from datetime import date

    task = create_task(
        mock_db,
        "Pay electric bill",
        _ACTOR_ID,
        assigned_to=assignee,
        due_date=date(2026, 4, 1),
        category="bills",
        priority="high",
        description="Monthly electric",
        source_document_id=doc_id,
        recurring_pattern_id=pattern_id,
    )
    added = mock_db.add.call_args[0][0]
    assert added.title == "Pay electric bill"
    assert added.assigned_to == assignee
    assert added.category == "bills"
    assert added.priority == "high"
    assert added.source_document_id == doc_id
    assert added.recurring_pattern_id == pattern_id


def test_list_tasks_open_only(mock_db: MagicMock) -> None:
    """list_tasks with default status returns only open tasks."""
    open_task = _make_task(status="open")
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
        open_task
    ]
    result = list_tasks(mock_db)
    assert len(result) == 1
    assert result[0].status == "open"


def test_list_tasks_filter_assigned_to(mock_db: MagicMock) -> None:
    """list_tasks filters by assigned_to when provided."""
    assignee = uuid.uuid4()
    task = _make_task(assigned_to=assignee)
    mock_db.query.return_value.filter.return_value.filter.return_value.order_by.return_value.all.return_value = [
        task
    ]
    result = list_tasks(mock_db, assigned_to=assignee)
    assert len(result) == 1


def test_list_tasks_filter_category(mock_db: MagicMock) -> None:
    """list_tasks filters by category when provided."""
    task = _make_task(category="groceries")
    mock_db.query.return_value.filter.return_value.filter.return_value.order_by.return_value.all.return_value = [
        task
    ]
    result = list_tasks(mock_db, category="groceries")
    assert len(result) == 1


@patch("src.services.tasks.log_action")
@patch("src.services.tasks.get_task")
def test_complete_task_sets_done(
    mock_get: MagicMock, mock_log: MagicMock, mock_db: MagicMock
) -> None:
    """complete_task sets status='done' and populates completed_at."""
    task = _make_task()
    mock_get.return_value = task
    result = complete_task(mock_db, task.id)
    assert result is not None
    assert task.status == "done"
    assert task.completed_at is not None


@patch("src.services.tasks.log_action")
@patch("src.services.tasks.get_task")
def test_archive_task_sets_archived(
    mock_get: MagicMock, mock_log: MagicMock, mock_db: MagicMock
) -> None:
    """archive_task sets status='archived'."""
    task = _make_task()
    mock_get.return_value = task
    result = archive_task(mock_db, task.id)
    assert result is not None
    assert task.status == "archived"


@patch("src.services.tasks.log_action")
@patch("src.services.tasks.get_task")
def test_update_task_status_custom_completed_at(
    mock_get: MagicMock, mock_log: MagicMock, mock_db: MagicMock
) -> None:
    """update_task_status with explicit completed_at uses that value."""
    task = _make_task()
    mock_get.return_value = task
    custom_time = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
    result = update_task_status(mock_db, task.id, "done", completed_at=custom_time)
    assert result is not None
    assert task.completed_at == custom_time
    assert task.status == "done"


@patch("src.services.tasks.log_action")
@patch("src.services.tasks.get_task")
def test_reassign_task_updates_assignee(
    mock_get: MagicMock, mock_log: MagicMock, mock_db: MagicMock
) -> None:
    """reassign_task updates assigned_to and logs reassignment."""
    task = _make_task(assigned_to=uuid.uuid4())
    new_assignee = uuid.uuid4()
    mock_get.return_value = task

    result = reassign_task(mock_db, task.id, new_assignee, actor_id=_ACTOR_ID)

    assert result is task
    assert task.assigned_to == new_assignee
    mock_db.flush.assert_called_once()
    mock_log.assert_called_once()
