"""Fortress 2.0 scheduler service — daily recurring task generation + notifications."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.models.schema import FamilyMember
from src.services.recurring import get_due_patterns, generate_tasks_from_due_patterns
from src.services.whatsapp_client import send_text_message
from src.prompts.personality import TEMPLATES
from src.config import ADMIN_PHONE

logger = logging.getLogger(__name__)


@dataclass
class SchedulerResult:
    tasks_created: int = 0
    notifications_sent: int = 0
    task_details: list[dict] = field(default_factory=list)


# In-memory state for /scheduler/status
_last_run: datetime | None = None
_last_run_tasks: int = 0


def get_status() -> dict:
    """Return scheduler status with last run timestamp and task count."""
    return {
        "last_run": _last_run.isoformat() if _last_run else None,
        "tasks_created_last_run": _last_run_tasks,
    }


async def run_daily_schedule(db: Session) -> SchedulerResult:
    """Main entry point: generate tasks from due patterns, send notifications."""
    global _last_run, _last_run_tasks

    result = SchedulerResult()

    # 1. Get due patterns
    due_patterns = get_due_patterns(db)
    logger.info("Scheduler run: found %d due patterns", len(due_patterns))

    if not due_patterns:
        logger.info("No patterns due — nothing to do")
        _last_run = datetime.now(timezone.utc)
        _last_run_tasks = 0
        return result

    # 2. Generate tasks (handles all due patterns internally)
    created_tasks = []
    try:
        created_tasks = generate_tasks_from_due_patterns(db)
    except Exception:
        logger.exception("Error during task generation")

    result.tasks_created = len(created_tasks)
    logger.info("Created %d tasks from recurring patterns", len(created_tasks))

    # 3. Send per-task notifications
    for task in created_tasks:
        try:
            phone = None
            if task.assigned_to:
                member = db.query(FamilyMember).filter(
                    FamilyMember.id == task.assigned_to
                ).first()
                if member:
                    phone = member.phone

            due_date_str = str(task.due_date) if task.due_date else ""
            result.task_details.append({
                "id": str(task.id),
                "title": task.title,
                "due_date": due_date_str,
                "phone": phone or "",
            })

            if phone:
                message = TEMPLATES["reminder_new_task"].format(
                    title=task.title, due_date=due_date_str,
                )
                sent = await send_text_message(phone, message)
                if sent:
                    result.notifications_sent += 1
                    logger.info("Notification sent to %s for task '%s'", phone, task.title)
                else:
                    logger.error("Failed to send notification to %s for task '%s'", phone, task.title)
            else:
                logger.warning("No phone for task '%s' (assigned_to=%s)", task.title, task.assigned_to)
        except Exception:
            logger.exception("Error sending notification for task '%s'", task.title)

    # 4. Send admin summary
    try:
        summary = TEMPLATES["scheduler_summary"].format(count=result.tasks_created)
        await send_text_message(ADMIN_PHONE, summary)
        logger.info("Admin summary sent to %s", ADMIN_PHONE)
    except Exception:
        logger.exception("Error sending admin summary to %s", ADMIN_PHONE)

    # 5. Update module state
    _last_run = datetime.now(timezone.utc)
    _last_run_tasks = result.tasks_created

    logger.info(
        "Scheduler run complete: %d tasks created, %d notifications sent",
        result.tasks_created, result.notifications_sent,
    )
    return result
