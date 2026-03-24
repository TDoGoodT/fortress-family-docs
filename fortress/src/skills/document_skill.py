"""Fortress Skills Engine — DocumentSkill: save and list documents."""

from __future__ import annotations

import asyncio
import re

from sqlalchemy.orm import Session

from src.models.schema import Document, FamilyMember
from src.prompts.personality import TEMPLATES, format_document_list
from src.services import documents
from src.skills.base_skill import BaseSkill, Command, Result
from src.skills.permissions import check_perm


class DocumentSkill(BaseSkill):
    """Skill for document and image management — save, list."""

    @property
    def name(self) -> str:
        return "document"

    @property
    def description(self) -> str:
        return "שמירת מסמכים ותמונות"

    @property
    def commands(self) -> list[tuple[re.Pattern, str]]:
        return [
            (re.compile(r'^(מסמכים|documents)$', re.IGNORECASE), 'list'),
        ]

    def execute(self, db: Session, member: FamilyMember, command: Command) -> Result:
        dispatch = {
            "save": self._save,
            "list": self._list,
        }
        handler = dispatch.get(command.action)
        if handler is None:
            return Result(success=False, message=TEMPLATES["error_fallback"])
        return handler(db, member, command.params)

    def get_help(self) -> str:
        return (
            "שלח מסמך או תמונה — שמירה אוטומטית\n"
            "מסמכים — רשימת מסמכים אחרונים"
        )

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

    def _save(self, db: Session, member: FamilyMember, params: dict) -> Result:
        denied = check_perm(db, member, "documents", "write")
        if denied:
            return denied

        file_path = params.get("file_path", "")

        # process_document is async; run it synchronously
        loop: asyncio.AbstractEventLoop | None = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Already inside an event loop — create a new one in a thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                doc = pool.submit(
                    asyncio.run,
                    documents.process_document(db, file_path, member.id, "whatsapp"),
                ).result()
        else:
            doc = asyncio.run(
                documents.process_document(db, file_path, member.id, "whatsapp")
            )

        return Result(
            success=True,
            message=TEMPLATES["document_saved"].format(filename=doc.original_filename),
            entity_type="document",
            entity_id=doc.id,
            action="saved",
        )

    def _list(self, db: Session, member: FamilyMember, params: dict) -> Result:
        denied = check_perm(db, member, "documents", "read")
        if denied:
            return denied

        doc_list = (
            db.query(Document)
            .filter(Document.uploaded_by == member.id)
            .order_by(Document.created_at.desc())
            .limit(20)
            .all()
        )

        if not doc_list:
            return Result(success=True, message=TEMPLATES["document_list_empty"])

        return Result(
            success=True,
            message=format_document_list(doc_list),
        )

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def verify(self, db: Session, result: Result) -> bool:
        if result.entity_id is None:
            return True

        doc = db.query(Document).filter(Document.id == result.entity_id).first()
        if doc is None:
            return False

        # saved → document exists in DB (already confirmed above)
        return True
