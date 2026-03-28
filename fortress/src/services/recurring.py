from __future__ import annotations
"""Fortress 2.0 recurring service — recurring task pattern management."""

from datetime import date, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from src.models.schema import RecurringPattern, Task
from src.services.audit import log_action
from src.services.tasks import create_task


def create_pattern(
    db: Session,
    title: str,
    frequency: str,
    next_due_date: date,
    *,
    assigned_to: UUID | None = None,
    category: str | None = None,
    description: str | None = None,
    day_of_month: int | None = None,
    month_of_year: int | None = None,
    auto_create_days_before: int = 7,
) -> RecurringPattern:
    """Create a new recurring pattern."""
    pattern = RecurringPattern(
        title=title,
        frequency=frequency,
        next_due_date=next_due_date,
        assigned_to=assigned_to,
        category=category,
        description=description,
        day_of_month=day_of_month,
        month_of_year=month_of_year,
        auto_create_days_before=auto_create_days_before,
    )
    db.add(pattern)
    db.flush()
    return pattern


def list_patterns(
    db: Session,
    is_active: bool = True,
) -> list[RecurringPattern]:
    """List recurring patterns, filtered by active status."""
    return (
        db.query(RecurringPattern)
        .filter(RecurringPattern.is_active == is_active)
        .all()
    )


def get_due_patterns(db: Session) -> list[RecurringPattern]:
    """Return active patterns whose task should be created now.

    A pattern is due when: next_due_date - auto_create_days_before <= today.
    """
    today = date.today()
    return (
        db.query(RecurringPattern)
        .filter(
            RecurringPattern.is_active.is_(True),
            (
                RecurringPattern.next_due_date
                - RecurringPattern.auto_create_days_before * timedelta(days=1)
            )
            <= today,
        )
        .all()
    )


def _advance_date(current: date, frequency: str) -> date:
    """Compute the next due date based on frequency."""
    if frequency == "daily":
        return current + timedelta(days=1)
    if frequency == "weekly":
        return current + timedelta(days=7)
    if frequency == "monthly":
        month = current.month % 12 + 1
        year = current.year + (1 if current.month == 12 else 0)
        day = min(current.day, _days_in_month(year, month))
        return date(year, month, day)
    if frequency == "yearly":
        year = current.year + 1
        day = min(current.day, _days_in_month(year, current.month))
        return date(year, current.month, day)
    return current


def _days_in_month(year: int, month: int) -> int:
    """Return the number of days in a given month."""
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - date(year, month, 1)).days


def generate_tasks_from_due_patterns(db: Session) -> list[Task]:
    """Create tasks for all due patterns and advance their next_due_date."""
    due = get_due_patterns(db)
    created_tasks: list[Task] = []

    for pattern in due:
        task = create_task(
            db,
            title=pattern.title,
            created_by=pattern.assigned_to,
            assigned_to=pattern.assigned_to,
            due_date=pattern.next_due_date,
            category=pattern.category,
            description=pattern.description,
            recurring_pattern_id=pattern.id,
        )
        pattern.next_due_date = _advance_date(pattern.next_due_date, pattern.frequency)
        db.flush()

        log_action(
            db,
            actor_id=pattern.assigned_to,
            action="recurring_task_generated",
            resource_type="recurring_pattern",
            resource_id=pattern.id,
            details={"task_title": pattern.title, "task_id": str(task.id)},
        )
        created_tasks.append(task)

    return created_tasks


def deactivate_pattern(db: Session, pattern_id: UUID) -> RecurringPattern | None:
    """Set a pattern's is_active to False."""
    pattern = (
        db.query(RecurringPattern)
        .filter(RecurringPattern.id == pattern_id)
        .first()
    )
    if pattern is None:
        return None
    pattern.is_active = False
    db.flush()
    return pattern
