"""Fortress Skills Engine — TaskSkill: create, list, delete, delete_all, complete, update."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from src.models.schema import FamilyMember, Task
from src.prompts.personality import TEMPLATES, format_task_created, format_task_list
from src.services import tasks
from src.services.conversation_state import (
    get_state,
    set_pending_confirmation,
    update_state,
)
from src.skills.base_skill import BaseSkill, Command, Result
from src.skills.permissions import check_perm

logger = logging.getLogger(__name__)


class TaskSkill(BaseSkill):
    """Skill for household task management — create, list, delete, complete, update."""

    @property
    def name(self) -> str:
        return "task"

    @property
    def description(self) -> str:
        return "ניהול משימות — יצירה, רשימה, מחיקה, השלמה, עדכון"

    @property
    def commands(self) -> list[tuple[re.Pattern, str]]:
        return [
            (re.compile(r"^משימה חדשה[:\s]+(?P<title>.+)$", re.IGNORECASE), "create"),
            (re.compile(r"^משימה[:\s\-]+(?P<title>.+)$", re.IGNORECASE), "create"),
            (re.compile(r"^new task[:\s]+(?P<title>.+)$", re.IGNORECASE), "create"),
            (re.compile(r"^מחק משימה\s+(?P<index>\d+)$", re.IGNORECASE), "delete"),
            (re.compile(r"^מחק משימה[:\s]+(?P<title_query>.+)$", re.IGNORECASE), "delete"),
            (re.compile(r"^מחק\s+(?P<index>\d+)$", re.IGNORECASE), "delete"),
            (re.compile(r"^(מחק הכל|נקה הכל|delete all)$", re.IGNORECASE), "delete_all"),
            (re.compile(r"^(סיים|סיום|בוצע|סיימתי)\s*(משימה)?\s*(?P<index>\d+)?$", re.IGNORECASE), "complete"),
            (re.compile(r"^(סיים|סיום|בוצע|סיימתי)[:\s]+(?P<title_query>.+)$", re.IGNORECASE), "complete"),
            (re.compile(r"^done\s*(?P<index>\d+)?$", re.IGNORECASE), "complete"),
            (re.compile(r"^(עדכן|שנה|תעדכן|תשנה)\s*(משימה)?\s*(?P<index>\d+)?\s*(?P<changes>.*)$", re.IGNORECASE), "update"),
            (re.compile(r"^משימות$", re.IGNORECASE), "list"),
            (re.compile(r"^tasks$", re.IGNORECASE), "list"),
        ]

    def execute(self, db: Session, member: FamilyMember, command: Command) -> Result:
        dispatch = {
            "create": self._create,
            "list": self._list,
            "delete": self._delete,
            "delete_all": self._delete_all,
            "complete": self._complete,
            "update": self._update,
        }
        handler = dispatch.get(command.action)
        if handler is None:
            return Result(success=False, message=TEMPLATES["error_fallback"])
        return handler(db, member, command.params)

    def get_help(self) -> str:
        return (
            "משימה חדשה <כותרת> — יצירת משימה\n"
            "משימות — רשימת משימות\n"
            "מחק <מספר> — מחיקת משימה\n"
            "מחק הכל — מחיקת כל המשימות\n"
            "סיים <מספר> — סימון כבוצע\n"
            "עדכן <מספר> <שינויים> — עדכון משימה"
        )

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

    def _create(self, db: Session, member: FamilyMember, params: dict) -> Result:
        denied = check_perm(db, member, "tasks", "write")
        if denied:
            return denied

        title = params.get("title", "").strip()

        # Duplicate detection: same title, same member, open, last 5 minutes
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
        duplicate = (
            db.query(Task)
            .filter(
                Task.title == title,
                Task.created_by == member.id,
                Task.status == "open",
                Task.created_at >= cutoff,
            )
            .first()
        )

        if duplicate:
            set_pending_confirmation(
                db, member.id, "task.create", {"title": title}
            )
            return Result(
                success=True,
                message=TEMPLATES["task_similar_exists"].format(
                    similar_title=duplicate.title, title=title
                ),
            )

        task = tasks.create_task(db, title, member.id, assigned_to=member.id)
        return Result(
            success=True,
            message=format_task_created(title),
            entity_type="task",
            entity_id=task.id,
            action="created",
        )

    def _list(self, db: Session, member: FamilyMember, params: dict) -> Result:
        denied = check_perm(db, member, "tasks", "read")
        if denied:
            return denied

        task_list = tasks.list_tasks(db, status="open", assigned_to=member.id)

        # Store ordered IDs in conversation state for index resolution
        update_state(
            db,
            member.id,
            context={"task_list_order": [str(t.id) for t in task_list]},
        )

        if not task_list:
            return Result(success=True, message=TEMPLATES["task_list_empty"])

        return Result(
            success=True,
            message=format_task_list(task_list),
        )

    def _delete(self, db: Session, member: FamilyMember, params: dict) -> Result:
        denied = check_perm(db, member, "tasks", "write")
        if denied:
            return denied

        # Confirmed re-dispatch from Executor: params contain task_id
        if "task_id" in params:
            task_id = UUID(params["task_id"])
            task = tasks.archive_task(db, task_id)
            if task is None:
                return Result(success=False, message=TEMPLATES["task_not_found"])
            return Result(
                success=True,
                message=TEMPLATES["task_deleted"].format(title=task.title),
                entity_type="task",
                entity_id=task.id,
                action="deleted",
            )

        # First-time request: resolve index from task_list_order
        state = get_state(db, member.id)
        context = state.context or {}
        task_list_order = context.get("task_list_order")

        if not task_list_order and "title_query" not in params:
            return Result(success=False, message=TEMPLATES["need_list_first"])

        # Resolve by title_query if provided
        if "title_query" in params:
            resolved = self._resolve_task_id(db, member, params)
            if isinstance(resolved, Result):
                return resolved
            task_id = resolved
        else:
            index = int(params.get("index", 0))
            if index < 1 or index > len(task_list_order):
                return Result(success=False, message=TEMPLATES["task_not_found"])
            task_id = UUID(task_list_order[index - 1])
        task = tasks.get_task(db, task_id)
        if task is None:
            return Result(success=False, message=TEMPLATES["task_not_found"])

        set_pending_confirmation(
            db, member.id, "task.delete", {"task_id": str(task_id)}
        )
        return Result(
            success=True,
            message=TEMPLATES["confirm_delete"].format(title=task.title),
        )

    def _delete_all(self, db: Session, member: FamilyMember, params: dict) -> Result:
        denied = check_perm(db, member, "tasks", "write")
        if denied:
            return denied

        # Confirmed re-dispatch: params contain task_ids — skip re-query
        if "task_ids" in params:
            archived = 0
            for tid in params["task_ids"]:
                task = tasks.get_task(db, UUID(tid))
                if task and task.status == "open":
                    tasks.archive_task(db, UUID(tid))
                    archived += 1
            logger.info("Delete all confirmed: archived %d tasks", archived)
            return Result(
                success=True,
                message=TEMPLATES["bulk_deleted"].format(count=archived),
            )

        # First-time request: query open tasks and ask for confirmation
        open_tasks = tasks.list_tasks(db, status="open", assigned_to=member.id)

        if not open_tasks:
            return Result(success=True, message=TEMPLATES["task_list_empty"])

        task_list_text = format_task_list(open_tasks)
        set_pending_confirmation(
            db,
            member.id,
            "task.delete_all",
            {"task_ids": [str(t.id) for t in open_tasks]},
        )
        return Result(
            success=True,
            message=TEMPLATES["bulk_delete_confirm"].format(
                count=len(open_tasks), task_list=task_list_text
            ),
        )

    def _complete(self, db: Session, member: FamilyMember, params: dict) -> Result:
        denied = check_perm(db, member, "tasks", "write")
        if denied:
            return denied

        task_id = self._resolve_task_id(db, member, params)
        if isinstance(task_id, Result):
            return task_id  # error result

        task = tasks.complete_task(db, task_id)
        if task is None:
            return Result(success=False, message=TEMPLATES["task_not_found"])

        logger.info("Task completed: %s (%s)", task.title, task.id)
        return Result(
            success=True,
            message=TEMPLATES["task_completed"].format(title=task.title),
            entity_type="task",
            entity_id=task.id,
            action="completed",
        )

    def _update(self, db: Session, member: FamilyMember, params: dict) -> Result:
        denied = check_perm(db, member, "tasks", "write")
        if denied:
            return denied

        task_id = self._resolve_task_id(db, member, params)
        if isinstance(task_id, Result):
            return task_id  # error result

        task = tasks.get_task(db, task_id)
        if task is None:
            return Result(success=False, message=TEMPLATES["task_not_found"])

        changes_text = params.get("changes", "").strip()
        changes_summary = self._parse_and_apply_changes(task, changes_text)
        db.flush()

        return Result(
            success=True,
            message=TEMPLATES["task_updated"].format(
                title=task.title, changes=changes_summary
            ),
            entity_type="task",
            entity_id=task.id,
            action="updated",
        )

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def verify(self, db: Session, result: Result) -> bool:
        if result.entity_id is None:
            return True

        task = tasks.get_task(db, result.entity_id)
        if task is None:
            return False

        action = result.action
        if action == "created":
            return task.status == "open"
        if action == "deleted":
            return task.status == "archived"
        if action == "completed":
            return task.status == "done"
        if action == "updated":
            return True  # task exists

        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_task_id(
        self, db: Session, member: FamilyMember, params: dict
    ) -> UUID | Result:
        """Resolve a task UUID from index, title_query, or last_entity_id fallback."""
        index_str = params.get("index")

        if index_str is not None:
            state = get_state(db, member.id)
            context = state.context or {}
            task_list_order = context.get("task_list_order")

            if not task_list_order:
                return Result(success=False, message=TEMPLATES["need_list_first"])

            index = int(index_str)
            if index < 1 or index > len(task_list_order):
                return Result(success=False, message=TEMPLATES["task_not_found"])

            task_id = UUID(task_list_order[index - 1])
            task = tasks.get_task(db, task_id)
            if task is None or task.status != "open":
                logger.warning("Stale index %d → task %s not open", index, task_id)
                return Result(success=False, message=TEMPLATES["task_not_found"])

            logger.info("Index %d resolved to task %s: %s", index, task.id, task.title)
            return task_id

        # Title search
        title_query = params.get("title_query")
        if title_query:
            open_tasks = tasks.list_tasks(db, status="open", assigned_to=member.id)
            query_lower = title_query.strip().lower()
            matches = [t for t in open_tasks if query_lower in t.title.lower()]
            if len(matches) == 1:
                logger.info("Title query '%s' resolved to task %s", title_query, matches[0].id)
                return matches[0].id
            if len(matches) > 1:
                titles = ", ".join(f"'{t.title}'" for t in matches[:3])
                return Result(success=False, message=f"מצאתי כמה משימות דומות: {titles}. אפשר להיות יותר מדויק?")
            return Result(success=False, message=TEMPLATES["task_not_found"])

        # Fallback: last_entity_id
        state = get_state(db, member.id)
        if state.last_entity_type == "task" and state.last_entity_id is not None:
            return state.last_entity_id

        return Result(success=False, message=TEMPLATES["task_not_found"])

    @staticmethod
    def _parse_and_apply_changes(task: Task, changes_text: str) -> str:
        """Parse free-text changes and apply them to the task object.

        Returns a summary string of applied changes.
        """
        applied: list[str] = []

        # Due date: look for date patterns like "עד 2024-01-15" or "due 2024-01-15"
        date_match = re.search(
            r"(?:עד|due|תאריך)\s*(\d{4}-\d{2}-\d{2})", changes_text
        )
        if date_match:
            from datetime import date

            task.due_date = date.fromisoformat(date_match.group(1))
            applied.append(f"תאריך: {task.due_date}")

        # Priority: look for priority keywords
        priority_map = {
            "דחוף": "urgent",
            "urgent": "urgent",
            "גבוה": "high",
            "high": "high",
            "רגיל": "normal",
            "normal": "normal",
            "נמוך": "low",
            "low": "low",
        }
        for keyword, priority_val in priority_map.items():
            if keyword in changes_text.lower():
                task.priority = priority_val
                applied.append(f"עדיפות: {priority_val}")
                break

        # Title: look for "כותרת <new title>" or "title <new title>"
        title_match = re.search(
            r"(?:כותרת|title)\s+(.+?)(?:\s+(?:עד|due|עדיפות|priority)|$)",
            changes_text,
        )
        if title_match:
            task.title = title_match.group(1).strip()
            applied.append(f"כותרת: {task.title}")

        if applied:
            return "\n" + "\n".join(applied)
        return ""
