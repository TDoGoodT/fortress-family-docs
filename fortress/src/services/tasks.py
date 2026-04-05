from __future__ import annotations
"""Fortress 2.0 task service — household task management."""

from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import case
from sqlalchemy.orm import Session

from src.models.schema import Task
from src.services.audit import log_action


_PRIORITY_ORDER = {"urgent": 0, "high": 1, "normal": 2, "low": 3}


def create_task(
    db: Session,
    title: str,
    created_by: UUID,
    *,
    assigned_to: UUID | None = None,
    due_date: date | None = None,
    category: str | None = None,
    priority: str = "normal",
    description: str | None = None,
    source_document_id: UUID | None = None,
    recurring_pattern_id: UUID | None = None,
) -> Task:
    """Create a new task and log the action."""
    task = Task(
        title=title,
        created_by=created_by,
        assigned_to=assigned_to,
        due_date=due_date,
        category=category,
        priority=priority,
        description=description,
        source_document_id=source_document_id,
        recurring_pattern_id=recurring_pattern_id,
    )
    db.add(task)
    db.flush()
    log_action(
        db,
        actor_id=created_by,
        action="task_created",
        resource_type="task",
        resource_id=task.id,
        details={"title": title},
    )
    return task


def list_tasks(
    db: Session,
    status: str = "open",
    assigned_to: UUID | None = None,
    category: str | None = None,
) -> list[Task]:
    """List tasks filtered by status, optionally by assigned_to and category.

    Results are ordered by priority (urgent first) then due_date (earliest first,
    NULLs last).
    """
    priority_sort = case(
        _PRIORITY_ORDER,
        value=Task.priority,
        else_=99,
    )

    query = db.query(Task).filter(Task.status == status)

    if assigned_to is not None:
        query = query.filter(Task.assigned_to == assigned_to)
    if category is not None:
        query = query.filter(Task.category == category)

    return query.order_by(priority_sort, Task.due_date.asc().nulls_last()).all()


def get_task(db: Session, task_id: UUID) -> Task | None:
    """Return a single task by ID, or None."""
    return db.query(Task).filter(Task.id == task_id).first()


def update_task_status(
    db: Session,
    task_id: UUID,
    new_status: str,
    completed_at: datetime | None = None,
) -> Task | None:
    """Update a task's status. Sets completed_at automatically when status is 'done'."""
    task = get_task(db, task_id)
    if task is None:
        return None

    task.status = new_status
    if new_status == "done" and completed_at is None and task.completed_at is None:
        task.completed_at = datetime.now(timezone.utc)
    elif completed_at is not None:
        task.completed_at = completed_at

    db.flush()
    log_action(
        db,
        actor_id=task.created_by,
        action="task_status_updated",
        resource_type="task",
        resource_id=task.id,
        details={"new_status": new_status},
    )
    return task


def complete_task(db: Session, task_id: UUID) -> Task | None:
    """Convenience: mark a task as done with completed_at=now()."""
    return update_task_status(db, task_id, "done")


def archive_task(db: Session, task_id: UUID) -> Task | None:
    """Set a task's status to archived."""
    return update_task_status(db, task_id, "archived")


def reassign_task(
    db: Session,
    task_id: UUID,
    assigned_to: UUID,
    *,
    actor_id: UUID,
) -> Task | None:
    """Update a task assignee and log the reassignment."""
    task = get_task(db, task_id)
    if task is None:
        return None

    previous_assignee = task.assigned_to
    task.assigned_to = assigned_to
    db.flush()

    log_action(
        db,
        actor_id=actor_id,
        action="task_reassigned",
        resource_type="task",
        resource_id=task.id,
        details={
            "previous_assignee": str(previous_assignee) if previous_assignee else None,
            "new_assignee": str(assigned_to),
        },
    )
    return task
