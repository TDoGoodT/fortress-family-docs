"""Fortress Skills Engine — BugSkill: report and list bugs."""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from src.models.schema import BugReport, FamilyMember
from src.prompts.personality import TEMPLATES, format_bug_list
from src.skills.base_skill import BaseSkill, Command, Result
from src.skills.permissions import check_perm


class BugSkill(BaseSkill):
    """Skill for bug reporting and tracking — report, list."""

    @property
    def name(self) -> str:
        return "bug"

    @property
    def description(self) -> str:
        return "דיווח ומעקב באגים"

    @property
    def commands(self) -> list[tuple[re.Pattern, str]]:
        return [
            (re.compile(r'^באג[:\s]+(?P<description>.+)$', re.IGNORECASE), 'report'),
            (re.compile(r'^bug[:\s]+(?P<description>.+)$', re.IGNORECASE), 'report'),
            (re.compile(r'^(באגים|bugs|רשימת באגים)$', re.IGNORECASE), 'list'),
        ]

    def execute(self, db: Session, member: FamilyMember, command: Command) -> Result:
        dispatch = {
            "report": self._report,
            "list": self._list,
        }
        handler = dispatch.get(command.action)
        if handler is None:
            return Result(success=False, message=TEMPLATES["error_fallback"])
        return handler(db, member, command.params)

    def get_help(self) -> str:
        return (
            "באג <תיאור> — דיווח על באג\n"
            "באגים — רשימת באגים פתוחים"
        )

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

    def _report(self, db: Session, member: FamilyMember, params: dict) -> Result:
        denied = check_perm(db, member, "tasks", "write")
        if denied:
            return denied

        description = params.get("description", "").strip()

        bug = BugReport(
            reported_by=member.id,
            description=description,
        )
        db.add(bug)
        db.flush()

        return Result(
            success=True,
            message=TEMPLATES["bug_reported"].format(description=description),
            entity_type="bug_report",
            entity_id=bug.id,
            action="reported",
        )

    def _list(self, db: Session, member: FamilyMember, params: dict) -> Result:
        denied = check_perm(db, member, "tasks", "read")
        if denied:
            return denied

        bugs = (
            db.query(BugReport)
            .filter(BugReport.status == "open")
            .all()
        )

        if not bugs:
            return Result(success=True, message=TEMPLATES["bug_list_empty"])

        return Result(
            success=True,
            message=format_bug_list(bugs),
        )

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def verify(self, db: Session, result: Result) -> bool:
        if result.entity_id is None:
            return True

        bug = db.query(BugReport).filter(BugReport.id == result.entity_id).first()
        if bug is None:
            return False

        action = result.action
        if action == "reported":
            return bug.status == "open"

        return True
