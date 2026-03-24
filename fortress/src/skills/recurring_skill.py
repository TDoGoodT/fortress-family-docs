"""Fortress Skills Engine — RecurringSkill: create, list, delete recurring patterns."""

from __future__ import annotations

import re
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from src.models.schema import FamilyMember, RecurringPattern
from src.prompts.personality import TEMPLATES, format_recurring_list
from src.services import recurring
from src.services.conversation_state import (
    get_state,
    set_pending_confirmation,
    update_state,
)
from src.skills.base_skill import BaseSkill, Command, Result
from src.skills.permissions import check_perm

# Hebrew frequency → English mapping
FREQUENCY_MAP: dict[str, str] = {
    "יומי": "daily",
    "שבועי": "weekly",
    "חודשי": "monthly",
    "שנתי": "yearly",
}


def _next_due_date(frequency: str, today: date | None = None) -> date:
    """Calculate the next due date from *today* based on frequency."""
    today = today or date.today()
    if frequency == "daily":
        return today + timedelta(days=1)
    if frequency == "weekly":
        return today + timedelta(days=7)
    if frequency == "monthly":
        month = today.month % 12 + 1
        year = today.year + (1 if today.month == 12 else 0)
        day = min(today.day, _days_in_month(year, month))
        return date(year, month, day)
    if frequency == "yearly":
        year = today.year + 1
        day = min(today.day, _days_in_month(year, today.month))
        return date(year, today.month, day)
    # Default: monthly
    month = today.month % 12 + 1
    year = today.year + (1 if today.month == 12 else 0)
    day = min(today.day, _days_in_month(year, month))
    return date(year, month, day)


def _days_in_month(year: int, month: int) -> int:
    """Return the number of days in a given month."""
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - date(year, month, 1)).days


class RecurringSkill(BaseSkill):
    """Skill for recurring reminder management — create, list, delete."""

    @property
    def name(self) -> str:
        return "recurring"

    @property
    def description(self) -> str:
        return "ניהול תזכורות חוזרות — יצירה, רשימה, ביטול"

    @property
    def commands(self) -> list[tuple[re.Pattern, str]]:
        return [
            (re.compile(r'^תזכורת חדשה[:\s]+(?P<title>.+)$', re.IGNORECASE), 'create'),
            (re.compile(r'^recurring[:\s]+(?P<title>.+)$', re.IGNORECASE), 'create'),
            (re.compile(r'^(תזכורות|חוזרות|recurring)$', re.IGNORECASE), 'list'),
            (re.compile(r'^(מחק|בטל) תזכורת\s*(?P<index>\d+)?$', re.IGNORECASE), 'delete'),
        ]

    def execute(self, db: Session, member: FamilyMember, command: Command) -> Result:
        dispatch = {
            "create": self._create,
            "list": self._list,
            "delete": self._delete,
        }
        handler = dispatch.get(command.action)
        if handler is None:
            return Result(success=False, message=TEMPLATES["error_fallback"])
        return handler(db, member, command.params)

    def get_help(self) -> str:
        return (
            "תזכורת חדשה <כותרת>, <תדירות> — יצירת תזכורת חוזרת\n"
            "תזכורות — רשימת תזכורות חוזרות\n"
            "מחק תזכורת <מספר> — ביטול תזכורת חוזרת"
        )

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

    def _create(self, db: Session, member: FamilyMember, params: dict) -> Result:
        denied = check_perm(db, member, "tasks", "write")
        if denied:
            return denied

        details = params.get("title", "").strip()

        # Parse "title, frequency" — e.g. "ארנונה, חודשי"
        if "," in details:
            parts = details.rsplit(",", 1)
            title = parts[0].strip()
            freq_text = parts[1].strip()
        else:
            title = details
            freq_text = ""

        frequency = FREQUENCY_MAP.get(freq_text, "monthly")
        next_due = _next_due_date(frequency)

        pattern = recurring.create_pattern(
            db, title, frequency, next_due, assigned_to=member.id
        )

        return Result(
            success=True,
            message=TEMPLATES["recurring_created"].format(
                title=title, frequency=frequency, next_due_date=next_due,
            ),
            entity_type="recurring_pattern",
            entity_id=pattern.id,
            action="created",
        )

    def _list(self, db: Session, member: FamilyMember, params: dict) -> Result:
        denied = check_perm(db, member, "tasks", "read")
        if denied:
            return denied

        patterns = recurring.list_patterns(db, is_active=True)

        # Store ordered IDs for index resolution (like TaskSkill)
        update_state(
            db,
            member.id,
            context={"pattern_list_order": [str(p.id) for p in patterns]},
        )

        if not patterns:
            return Result(success=True, message=TEMPLATES["recurring_list_empty"])

        return Result(
            success=True,
            message=format_recurring_list(patterns),
        )

    def _delete(self, db: Session, member: FamilyMember, params: dict) -> Result:
        denied = check_perm(db, member, "tasks", "write")
        if denied:
            return denied

        # Confirmed re-dispatch from Executor: params contain pattern_id
        if "pattern_id" in params:
            pattern_id = UUID(params["pattern_id"])
            pattern = recurring.deactivate_pattern(db, pattern_id)
            if pattern is None:
                return Result(success=False, message=TEMPLATES["recurring_not_found"])
            return Result(
                success=True,
                message=TEMPLATES["recurring_deleted"].format(title=pattern.title),
                entity_type="recurring_pattern",
                entity_id=pattern.id,
                action="deleted",
            )

        # First-time request: resolve index from pattern_list_order
        state = get_state(db, member.id)
        context = state.context or {}
        pattern_list_order = context.get("pattern_list_order")

        if not pattern_list_order:
            return Result(success=False, message=TEMPLATES["need_list_first"])

        index = int(params.get("index", 0))
        if index < 1 or index > len(pattern_list_order):
            return Result(success=False, message=TEMPLATES["recurring_not_found"])

        pattern_id = UUID(pattern_list_order[index - 1])
        pattern = (
            db.query(RecurringPattern)
            .filter(RecurringPattern.id == pattern_id)
            .first()
        )
        if pattern is None:
            return Result(success=False, message=TEMPLATES["recurring_not_found"])

        set_pending_confirmation(
            db, member.id, "recurring.delete", {"pattern_id": str(pattern_id)}
        )
        return Result(
            success=True,
            message=TEMPLATES["confirm_delete"].format(title=pattern.title),
        )

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def verify(self, db: Session, result: Result) -> bool:
        if result.entity_id is None:
            return True

        pattern = (
            db.query(RecurringPattern)
            .filter(RecurringPattern.id == result.entity_id)
            .first()
        )
        if pattern is None:
            return False

        action = result.action
        if action == "created":
            return pattern.is_active is True
        if action == "deleted":
            return pattern.is_active is False

        return True
