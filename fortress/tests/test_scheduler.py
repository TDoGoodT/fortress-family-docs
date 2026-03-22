"""Unit tests for the scheduler service."""

import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.schema import FamilyMember, Task
from src.services.scheduler import SchedulerResult, get_status, run_daily_schedule


def _make_task(**overrides) -> MagicMock:
    """Build a mock Task."""
    t = MagicMock(spec=Task)
    t.id = overrides.get("id", uuid.uuid4())
    t.title = overrides.get("title", "Pay rent")
    t.due_date = overrides.get("due_date", date(2026, 5, 1))
    t.assigned_to = overrides.get("assigned_to", uuid.uuid4())
    return t


def _make_member(member_id: uuid.UUID, phone: str = "+972501234567") -> MagicMock:
    """Build a mock FamilyMember."""
    m = MagicMock(spec=FamilyMember)
    m.id = member_id
    m.phone = phone
    return m


# ---- test_status_before_first_run ----

def test_status_before_first_run() -> None:
    """get_status() returns null/0 before any run."""
    import src.services.scheduler as mod
    # Reset module state
    mod._last_run = None
    mod._last_run_tasks = 0

    status = get_status()
    assert status["last_run"] is None
    assert status["tasks_created_last_run"] == 0


# ---- test_run_no_due_patterns_returns_empty ----

@pytest.mark.asyncio
@patch("src.services.scheduler.get_due_patterns", return_value=[])
async def test_run_no_due_patterns_returns_empty(mock_due: MagicMock, mock_db: MagicMock) -> None:
    """Empty result when no patterns are due."""
    result = await run_daily_schedule(mock_db)

    assert isinstance(result, SchedulerResult)
    assert result.tasks_created == 0
    assert result.notifications_sent == 0
    assert result.task_details == []


# ---- test_run_with_due_patterns_creates_tasks ----

@pytest.mark.asyncio
@patch("src.services.scheduler.send_text_message", new_callable=AsyncMock, return_value=True)
@patch("src.services.scheduler.generate_tasks_from_due_patterns")
@patch("src.services.scheduler.get_due_patterns")
async def test_run_with_due_patterns_creates_tasks(
    mock_due: MagicMock,
    mock_gen: MagicMock,
    mock_send: AsyncMock,
    mock_db: MagicMock,
) -> None:
    """Tasks are created and result is populated when patterns are due."""
    member_id = uuid.uuid4()
    task = _make_task(assigned_to=member_id)
    member = _make_member(member_id)

    mock_due.return_value = [MagicMock()]  # one due pattern
    mock_gen.return_value = [task]
    mock_db.query.return_value.filter.return_value.first.return_value = member

    result = await run_daily_schedule(mock_db)

    assert result.tasks_created == 1
    assert len(result.task_details) == 1
    assert result.task_details[0]["title"] == "Pay rent"


# ---- test_notifications_sent_for_created_tasks ----

@pytest.mark.asyncio
@patch("src.services.scheduler.send_text_message", new_callable=AsyncMock, return_value=True)
@patch("src.services.scheduler.generate_tasks_from_due_patterns")
@patch("src.services.scheduler.get_due_patterns")
async def test_notifications_sent_for_created_tasks(
    mock_due: MagicMock,
    mock_gen: MagicMock,
    mock_send: AsyncMock,
    mock_db: MagicMock,
) -> None:
    """send_text_message is called for each created task's assigned member."""
    member_id = uuid.uuid4()
    task1 = _make_task(title="Task A", assigned_to=member_id)
    task2 = _make_task(title="Task B", assigned_to=member_id)
    member = _make_member(member_id, phone="972501111111")

    mock_due.return_value = [MagicMock(), MagicMock()]
    mock_gen.return_value = [task1, task2]
    mock_db.query.return_value.filter.return_value.first.return_value = member

    result = await run_daily_schedule(mock_db)

    # 2 per-task notifications + 1 admin summary = 3 calls
    assert mock_send.call_count == 3
    assert result.notifications_sent == 2


# ---- test_notification_failure_does_not_crash ----

@pytest.mark.asyncio
@patch("src.services.scheduler.send_text_message", new_callable=AsyncMock, return_value=False)
@patch("src.services.scheduler.generate_tasks_from_due_patterns")
@patch("src.services.scheduler.get_due_patterns")
async def test_notification_failure_does_not_crash(
    mock_due: MagicMock,
    mock_gen: MagicMock,
    mock_send: AsyncMock,
    mock_db: MagicMock,
) -> None:
    """Scheduler continues when send_text_message returns False."""
    member_id = uuid.uuid4()
    task = _make_task(assigned_to=member_id)
    member = _make_member(member_id)

    mock_due.return_value = [MagicMock()]
    mock_gen.return_value = [task]
    mock_db.query.return_value.filter.return_value.first.return_value = member

    result = await run_daily_schedule(mock_db)

    assert result.tasks_created == 1
    assert result.notifications_sent == 0  # send returned False


# ---- test_admin_summary_sent_after_run ----

@pytest.mark.asyncio
@patch("src.services.scheduler.ADMIN_PHONE", "972540000000")
@patch("src.services.scheduler.send_text_message", new_callable=AsyncMock, return_value=True)
@patch("src.services.scheduler.generate_tasks_from_due_patterns")
@patch("src.services.scheduler.get_due_patterns")
async def test_admin_summary_sent_after_run(
    mock_due: MagicMock,
    mock_gen: MagicMock,
    mock_send: AsyncMock,
    mock_db: MagicMock,
) -> None:
    """Summary notification is sent to ADMIN_PHONE after run."""
    member_id = uuid.uuid4()
    task = _make_task(assigned_to=member_id)
    member = _make_member(member_id)

    mock_due.return_value = [MagicMock()]
    mock_gen.return_value = [task]
    mock_db.query.return_value.filter.return_value.first.return_value = member

    result = await run_daily_schedule(mock_db)

    # Last call should be the admin summary
    admin_call = mock_send.call_args_list[-1]
    assert admin_call[0][0] == "972540000000"
    assert "סיכום יומי" in admin_call[0][1]


# ---- test_status_updated_after_run ----

@pytest.mark.asyncio
@patch("src.services.scheduler.send_text_message", new_callable=AsyncMock, return_value=True)
@patch("src.services.scheduler.generate_tasks_from_due_patterns")
@patch("src.services.scheduler.get_due_patterns")
async def test_status_updated_after_run(
    mock_due: MagicMock,
    mock_gen: MagicMock,
    mock_send: AsyncMock,
    mock_db: MagicMock,
) -> None:
    """get_status() reflects last run after execution."""
    import src.services.scheduler as mod
    mod._last_run = None
    mod._last_run_tasks = 0

    member_id = uuid.uuid4()
    task = _make_task(assigned_to=member_id)
    member = _make_member(member_id)

    mock_due.return_value = [MagicMock()]
    mock_gen.return_value = [task]
    mock_db.query.return_value.filter.return_value.first.return_value = member

    await run_daily_schedule(mock_db)

    status = get_status()
    assert status["last_run"] is not None
    assert status["tasks_created_last_run"] == 1


# ---- test_single_pattern_error_continues_others ----

@pytest.mark.asyncio
@patch("src.services.scheduler.send_text_message", new_callable=AsyncMock, return_value=True)
@patch("src.services.scheduler.generate_tasks_from_due_patterns")
@patch("src.services.scheduler.get_due_patterns")
async def test_single_pattern_error_continues_others(
    mock_due: MagicMock,
    mock_gen: MagicMock,
    mock_send: AsyncMock,
    mock_db: MagicMock,
) -> None:
    """Scheduler handles generation errors gracefully and still completes."""
    mock_due.return_value = [MagicMock(), MagicMock()]
    mock_gen.side_effect = Exception("DB error on one pattern")

    result = await run_daily_schedule(mock_db)

    # Generation failed, so no tasks created, but scheduler didn't crash
    assert result.tasks_created == 0
    assert result.notifications_sent == 0
    # Admin summary should still be sent
    assert mock_send.call_count == 1  # only admin summary
