"""Fortress Skills Engine — system skill: cancel, confirm, help."""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from src.models.schema import FamilyMember
from src.prompts.personality import TEMPLATES as PERSONALITY_TEMPLATES
from src.services.conversation_state import clear_state, get_state, resolve_pending
from src.skills.base_skill import BaseSkill, Command, Result


class SystemSkill(BaseSkill):
    """Built-in skill for cancel, confirm, and help commands."""

    @property
    def name(self) -> str:
        return "system"

    @property
    def description(self) -> str:
        return "פקודות מערכת: ביטול, אישור, עזרה"

    @property
    def commands(self) -> list[tuple[re.Pattern, str]]:
        return [
            (re.compile(r"^(עזרה|help|פקודות)$", re.IGNORECASE), "help"),
        ]

    def execute(self, db: Session, member: FamilyMember, command: Command) -> Result:
        if command.action == "cancel":
            return self._cancel(db, member)
        if command.action == "confirm":
            return self._confirm(db, member)
        if command.action == "help":
            return self._help()
        return Result(success=False, message=PERSONALITY_TEMPLATES["error_fallback"])

    def verify(self, db: Session, result: Result) -> bool:
        return True

    def get_help(self) -> str:
        return "ביטול — ביטול פעולה\nאישור — אישור פעולה\nעזרה — הצגת פקודות"

    def _cancel(self, db: Session, member: FamilyMember) -> Result:
        clear_state(db, member.id)
        return Result(
            success=True,
            message=PERSONALITY_TEMPLATES["cancelled"],
            action="cancel",
        )

    def _confirm(self, db: Session, member: FamilyMember) -> Result:
        state = get_state(db, member.id)
        if not state.pending_confirmation:
            return Result(success=False, message="אין פעולה ממתינה לאישור 🤷")
        pending = resolve_pending(db, member.id)
        return Result(
            success=True,
            message="",
            action="confirm",
            data={"pending_action": pending},
        )

    def _help(self) -> Result:
        from src.skills.registry import registry as _reg

        lines = ["📋 פקודות זמינות:\n"]
        for skill in _reg.list_skills():
            lines.append(f"▸ {skill.description}")
            lines.append(f"  {skill.get_help()}\n")
        return Result(success=True, message="\n".join(lines), action="help")
