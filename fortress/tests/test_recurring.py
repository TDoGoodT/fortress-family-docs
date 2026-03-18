"""Unit tests for the recurring pattern service."""

import uuid
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from src.models.schema import RecurringPattern
from src.services.recurring import (
    _advance_date,
    create_pattern,
    deactivate_pattern,
    generate_tasks_from_due_patterns,
    get_due_patterns,
)


_ACTOR_ID = uuid.uuid4()


def _make_pattern(**overrides) -> MagicMock:
    """Build a mock RecurringPattern."""
    p = MagicMock(spec=RecurringPattern)
    p.id = overrides.get("id", uuid.uuid4())
    p.title = overrides.get("title", "Monthly rent")
    p.frequency = overrides.get("frequency", "monthly")
    p.next_due_date = overrides.get("next_due_date", date(2026, 4, 1))
    p.auto_create_days_before = overrides.get("auto_create_days_before", 7)
    p.is_active = overrides.get("is_active", True)
    p.assigned_to = overrides.get("assigned_to", _ACTOR_ID)
    p.category = overrides.get("category", "bills")
    p.description = overrides.get("description", None)
    return p


def test_create_pattern_required_fields(mock_db: MagicMock) -> None:
    """create_pattern with required fields adds to session."""
    pattern = create_pattern(
        mock_db,
        title="Monthly rent",
        frequency="monthly",
        next_due_date=date(2026, 4, 1),
    )
    mock_db.add.assert_called_once()
    added = mock_db.add.call_args[0][0]
    assert added.title == "Monthly rent"
    assert added.frequency == "monthly"


def test_get_due_patterns_returns_due(mock_db: MagicMock) -> None:
    """get_due_patterns returns patterns that are due."""
    due_pattern = _make_pattern(
        next_due_date=date.today(),
        auto_create_days_before=7,
    )
    mock_db.query.return_value.filter.return_value.all.return_value = [due_pattern]
    result = get_due_patterns(mock_db)
    assert len(result) == 1


def test_get_due_patterns_excludes_inactive(mock_db: MagicMock) -> None:
    """get_due_patterns should not return inactive patterns."""
    mock_db.query.return_value.filter.return_value.all.return_value = []
    result = get_due_patterns(mock_db)
    assert len(result) == 0


@patch("src.services.recurring.log_action")
@patch("src.services.recurring.create_task")
@patch("src.services.recurring.get_due_patterns")
def test_generate_tasks_creates_and_advances(
    mock_due: MagicMock,
    mock_create: MagicMock,
    mock_log: MagicMock,
    mock_db: MagicMock,
) -> None:
    """generate_tasks_from_due_patterns creates tasks and advances dates."""
    pattern = _make_pattern(
        frequency="monthly",
        next_due_date=date(2026, 4, 1),
    )
    mock_due.return_value = [pattern]
    mock_task = MagicMock()
    mock_task.id = uuid.uuid4()
    mock_create.return_value = mock_task

    result = generate_tasks_from_due_patterns(mock_db)

    assert len(result) == 1
    mock_create.assert_called_once()
    # next_due_date should have been advanced to May 1
    assert pattern.next_due_date == date(2026, 5, 1)


# --- Date advancement tests ---

def test_advance_daily() -> None:
    assert _advance_date(date(2026, 3, 18), "daily") == date(2026, 3, 19)


def test_advance_weekly() -> None:
    assert _advance_date(date(2026, 3, 18), "weekly") == date(2026, 3, 25)


def test_advance_monthly() -> None:
    assert _advance_date(date(2026, 3, 31), "monthly") == date(2026, 4, 30)


def test_advance_monthly_normal() -> None:
    assert _advance_date(date(2026, 1, 15), "monthly") == date(2026, 2, 15)


def test_advance_yearly() -> None:
    assert _advance_date(date(2026, 3, 18), "yearly") == date(2027, 3, 18)


def test_advance_yearly_leap() -> None:
    """Feb 29 in a leap year advances to Feb 28 in a non-leap year."""
    assert _advance_date(date(2028, 2, 29), "yearly") == date(2029, 2, 28)
