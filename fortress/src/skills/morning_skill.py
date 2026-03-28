"""Fortress Skills Engine — MorningSkill: morning briefing and summary reports."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from src.models.schema import (
    BugReport,
    Document,
    FamilyMember,
    RecurringPattern,
    Task,
)
from src.prompts.personality import TEMPLATES
from src.skills.base_skill import BaseSkill, Command, Result
from src.skills.permissions import check_perm


class MorningSkill(BaseSkill):
    """Skill for morning briefing and summary reports — briefing, summary."""

    @property
    def name(self) -> str:
        return "morning"

    @property
    def description(self) -> str:
        return "סיכום בוקר ודוחות"

    @property
    def commands(self) -> list[tuple[re.Pattern, str]]:
        return [
            (re.compile(r"^(בוקר|morning|סיכום בוקר)$", re.IGNORECASE), "briefing"),
            (re.compile(r"^(סטטוס|status)$", re.IGNORECASE), "status"),
            (re.compile(r"^(דוח|report|סיכום)$", re.IGNORECASE), "summary"),
        ]

    def execute(self, db: Session, member: FamilyMember, command: Command) -> Result:
        dispatch = {
            "briefing": self._briefing,
            "summary": self._summary,
        }
        handler = dispatch.get(command.action)
        if handler is None:
            return Result(success=False, message=TEMPLATES["error_fallback"])
        return handler(db, member, command.params)

    def get_help(self) -> str:
        return (
            "בוקר — סיכום בוקר עם משימות, תזכורות ומסמכים\n"
            "דוח — דוח סיכום"
        )

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

    def _briefing(self, db: Session, member: FamilyMember, params: dict) -> Result:
        # Open tasks assigned to this member
        task_count = (
            db.query(Task)
            .filter(Task.status == "open", Task.assigned_to == member.id)
            .count()
        )

        # Active recurring patterns
        active_recurring = (
            db.query(RecurringPattern)
            .filter(RecurringPattern.is_active == True)  # noqa: E712
            .count()
        )

        # Recent documents (last 7 days)
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        doc_count = (
            db.query(Document)
            .filter(
                Document.uploaded_by == member.id,
                Document.created_at >= cutoff,
            )
            .count()
        )

        # Open bugs
        bug_count = (
            db.query(BugReport)
            .filter(BugReport.status == "open")
            .count()
        )

        # Build sections
        sections: list[str] = []
        sections.append(TEMPLATES["briefing_tasks"].format(count=task_count))

        # Recurring: find next upcoming pattern for the template
        next_pattern = (
            db.query(RecurringPattern)
            .filter(RecurringPattern.is_active == True)  # noqa: E712
            .order_by(RecurringPattern.next_due_date.asc())
            .first()
        )
        if next_pattern is not None:
            today = datetime.now(timezone.utc).date()
            days_until = (next_pattern.next_due_date - today).days
            sections.append(
                TEMPLATES["briefing_recurring"].format(
                    next_title=next_pattern.title,
                    days=days_until,
                )
            )
        # B3 fix: hide recurring line entirely when there are no active patterns

        sections.append(TEMPLATES["briefing_docs"].format(count=doc_count))

        # Only show bugs for parent role
        if member.role == "parent":
            sections.append(TEMPLATES["briefing_bugs"].format(count=bug_count))

        message = TEMPLATES["morning_briefing"].format(
            name=member.name,
            items="\n".join(sections),
        )

        return Result(success=True, message=message)

    def _summary(self, db: Session, member: FamilyMember, params: dict) -> Result:
        denied = check_perm(db, member, "finance", "read")
        if denied:
            return denied

        return Result(success=True, message=TEMPLATES["no_report_yet"])

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def verify(self, db: Session, result: Result) -> bool:
        # Read-only operations — always True
        return True
