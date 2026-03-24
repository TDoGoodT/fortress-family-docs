"""Fortress Skills Engine — MemorySkill: store, recall, and list memories."""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from src.models.schema import FamilyMember, Memory
from src.prompts.personality import TEMPLATES
from src.services import memory_service
from src.skills.base_skill import BaseSkill, Command, Result


class MemorySkill(BaseSkill):
    """Skill for memory management — store, recall, list.

    store and recall are programmatic interfaces (no user-facing regex).
    Only list is triggered by user commands.
    """

    @property
    def name(self) -> str:
        return "memory"

    @property
    def description(self) -> str:
        return "ניהול זיכרונות — שמירה, שליפה, רשימה"

    @property
    def commands(self) -> list[tuple[re.Pattern, str]]:
        return [
            (re.compile(r"^(זכרונות|memories)$", re.IGNORECASE), "list"),
        ]

    def execute(self, db: Session, member: FamilyMember, command: Command) -> Result:
        dispatch = {
            "list": self._list,
        }
        handler = dispatch.get(command.action)
        if handler is None:
            return Result(success=False, message=TEMPLATES["error_fallback"])
        return handler(db, member, command.params)

    def get_help(self) -> str:
        return "זכרונות — רשימת הזיכרונות השמורים שלך"

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

    async def _store(
        self,
        db: Session,
        member: FamilyMember,
        content: str,
        category: str,
        memory_type: str,
    ) -> Result:
        """Programmatic: save a memory after exclusion check."""
        if memory_service.check_exclusion(db, content, member.id):
            return Result(success=False, message=TEMPLATES["memory_excluded"])

        memory = await memory_service.save_memory(
            db, member.id, content, category, memory_type,
        )

        if memory is None:
            # save_memory returned None (excluded by service-level check)
            return Result(success=False, message=TEMPLATES["memory_excluded"])

        return Result(
            success=True,
            message=TEMPLATES["info_stored"].format(content=content),
            entity_type="memory",
            entity_id=memory.id,
            action="stored",
        )

    def _recall(self, db: Session, member: FamilyMember) -> Result:
        """Programmatic: load memories for ChatSkill context."""
        memories = memory_service.load_memories(db, member.id)
        return Result(
            success=True,
            message="",
            data={"memories": memories},
        )

    def _list(self, db: Session, member: FamilyMember, params: dict) -> Result:
        """User-facing: show numbered memory list."""
        memories = memory_service.load_memories(db, member.id)

        if not memories:
            return Result(success=True, message=TEMPLATES["memory_list_empty"])

        lines: list[str] = [TEMPLATES["memory_list_header"]]
        for i, mem in enumerate(memories, 1):
            lines.append(f"{i}. [{mem.category}] {mem.content}")

        return Result(success=True, message="\n".join(lines))

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def verify(self, db: Session, result: Result) -> bool:
        if result.action == "stored" and result.entity_id is not None:
            memory = (
                db.query(Memory).filter(Memory.id == result.entity_id).first()
            )
            return memory is not None
        return True
