"""Fortress Skills Engine — DocumentSkill: save, list, search, query, recent."""

from __future__ import annotations

import asyncio
import re
from typing import Union

from sqlalchemy.orm import Session

from src.models.schema import Document, FamilyMember
from src.prompts.personality import TEMPLATES, format_document_list, format_search_results
from src.services import documents
from src.services.conversation_state import update_state
from src.services.document_query_service import (
    QAResult,
    answer_document_question,
    resolve_document_reference,
    search_documents,
)
from src.skills.base_skill import BaseSkill, Command, Result
from src.skills.permissions import check_perm


class DocumentSkill(BaseSkill):
    """Skill for document management — save, list, search, query, recent."""

    @property
    def name(self) -> str:
        return "document"

    @property
    def description(self) -> str:
        return "שמירת מסמכים ותמונות"

    @property
    def commands(self) -> list[tuple[re.Pattern, str]]:
        return [
            # Existing: list all documents
            (re.compile(r'^(מסמכים|documents)$', re.IGNORECASE), 'list'),
            # New: recent document
            (re.compile(r'^(מסמך אחרון|latest document|last document|המסמך האחרון)$', re.IGNORECASE), 'recent'),
            # New: search by type (Hebrew + English)
            (re.compile(r'^(?:הראה|show|חפש|find)\s+(?P<doc_type>חוזים|contracts|חשבוניות|invoices|קבלות|receipts|ביטוח|insurance|אחריות|warranty|דפי חשבון|bank statements|כרטיס אשראי|credit card)', re.IGNORECASE), 'search'),
            # New: search by vendor/keyword
            (re.compile(r'^(?:חפש|find)\s+(?:מסמך|document|קבלה|receipt)?\s*(?:מ|from|של|by)?\s+(?P<keyword>.+)', re.IGNORECASE), 'search'),
            # New: document questions (deterministic, owned by DocumentSkill)
            (re.compile(r'^(?P<question>(?:מה סוג|what type|כמה עולה|what.+amount|מי ה|who.+counterparty|תן לי סיכום|give me a summary|מה הסכום|what is the amount|מה התאריך|what is the date).+)', re.IGNORECASE), 'query'),
        ]

    def execute(self, db: Session, member: FamilyMember, command: Command) -> Result:
        dispatch = {
            "save": self._save,
            "list": self._list,
            "search": self._search,
            "recent": self._recent,
            "query": self._query,
        }
        handler = dispatch.get(command.action)
        if handler is None:
            return Result(success=False, message=TEMPLATES["error_fallback"])
        return handler(db, member, command.params)

    def get_help(self) -> str:
        return (
            "שלח מסמך או תמונה — שמירה אוטומטית\n"
            "מסמכים — רשימת מסמכים אחרונים\n"
            "מסמך אחרון — המסמך האחרון\n"
            "הראה חוזים / חשבוניות / ביטוח — חיפוש לפי סוג\n"
            "חפש מסמך מ-[ספק] — חיפוש לפי ספק"
        )

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

    def _save(self, db: Session, member: FamilyMember, params: dict) -> Result:
        denied = check_perm(db, member, "documents", "write")
        if denied:
            return denied

        file_path = params.get("file_path") or params.get("media_file_path", "")

        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
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

        return Result(success=True, message=format_document_list(doc_list))

    def _search(self, db: Session, member: FamilyMember, params: dict) -> Result:
        denied = check_perm(db, member, "documents", "read")
        if denied:
            return denied

        filters: dict = {}

        # Map Hebrew/English type keywords to physical doc_type values
        doc_type_raw = params.get("doc_type", "")
        keyword = params.get("keyword", "")

        _TYPE_MAP = {
            "חוזים": "contract", "contracts": "contract",
            "חשבוניות": "invoice", "invoices": "invoice",
            "קבלות": "receipt", "receipts": "receipt",
            "ביטוח": "insurance", "insurance": "insurance",
            "אחריות": "warranty", "warranty": "warranty",
            "דפי חשבון": "bank_statement", "bank statements": "bank_statement",
            "כרטיס אשראי": "credit_card_statement", "credit card": "credit_card_statement",
        }

        if doc_type_raw:
            filters["doc_type"] = _TYPE_MAP.get(doc_type_raw.lower(), doc_type_raw.lower())
        elif keyword:
            filters["keyword"] = keyword.strip()

        results = search_documents(db, member.id, filters)

        if not results:
            return Result(success=True, message=TEMPLATES["document_search_empty"])

        return Result(success=True, message=format_search_results(results))

    def _recent(self, db: Session, member: FamilyMember, params: dict) -> Result:
        denied = check_perm(db, member, "documents", "read")
        if denied:
            return denied

        doc = (
            db.query(Document)
            .filter(Document.uploaded_by == member.id)
            .order_by(Document.created_at.desc())
            .first()
        )

        if not doc:
            return Result(success=True, message=TEMPLATES["document_list_empty"])

        return Result(
            success=True,
            message=format_document_list([doc]),
            entity_type="document",
            entity_id=doc.id,
            action="viewed",
        )

    def _query(self, db: Session, member: FamilyMember, params: dict) -> Result:
        denied = check_perm(db, member, "documents", "read")
        if denied:
            return denied

        question = params.get("question", params.get("raw_text", ""))

        # Resolve which document the user is asking about
        resolved = resolve_document_reference(db, member, question)

        if resolved is None:
            return Result(success=True, message=TEMPLATES["document_list_empty"])

        # Multiple candidates — ask for clarification
        if isinstance(resolved, list):
            options = []
            for i, doc in enumerate(resolved[:5], 1):
                from src.prompts.personality import _DOC_TYPE_EMOJI
                emoji = _DOC_TYPE_EMOJI.get(doc.doc_type or "other", "📎")
                date_text = str(doc.created_at)[:10] if doc.created_at else ""
                options.append(f"{i}. {emoji} {doc.original_filename} ({doc.doc_type}) — {date_text}")
            clarify_msg = TEMPLATES["document_clarify"].format(options="\n".join(options))
            return Result(success=True, message=clarify_msg)

        doc = resolved

        # Update conversation state with resolved document
        update_state(db, member.id, entity_type="document", entity_id=doc.id, intent="document.query")

        # Answer the question
        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                qa_result: QAResult = pool.submit(
                    asyncio.run,
                    answer_document_question(db, member, question, doc),
                ).result()
        else:
            qa_result = asyncio.run(answer_document_question(db, member, question, doc))

        return Result(
            success=True,
            message=qa_result.answer_text,
            entity_type="document",
            entity_id=doc.id,
            action="queried",
        )

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def verify(self, db: Session, result: Result) -> bool:
        if result.entity_id is None:
            return True
        doc = db.query(Document).filter(Document.id == result.entity_id).first()
        return doc is not None
