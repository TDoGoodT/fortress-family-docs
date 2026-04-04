"""Fortress Skills Engine — DocumentSkill: save, list, search, query, recent."""

from __future__ import annotations

import asyncio
import logging
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
    get_recent_documents,
    get_view_filters,
    merge_tags,
    normalize_tag,
    resolve_document_reference,
    search_by_name,
    search_documents,
)
from src.skills.base_skill import BaseSkill, Command, Result
from src.skills.permissions import check_perm

logger = logging.getLogger(__name__)


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
            (re.compile(r'^(נקה מסמכים|מחק מסמכים|מחק את כל המסמכים)$', re.IGNORECASE), 'delete_documents'),
            # Natural Hebrew document-listing variants → list
            (re.compile(r'איזה מסמכים', re.IGNORECASE), 'list'),
            (re.compile(r'אילו מסמכים', re.IGNORECASE), 'list'),
            (re.compile(r'מה המסמכים', re.IGNORECASE), 'list'),
            (re.compile(r'רשימת מסמכים', re.IGNORECASE), 'list'),
            (re.compile(r'הצג מסמכים', re.IGNORECASE), 'list'),
            (re.compile(r'כל המסמכים', re.IGNORECASE), 'list'),
            (re.compile(r'הראה מסמכים', re.IGNORECASE), 'list'),
            # New: latest N / recent feed
            (re.compile(r'^(מסמכים אחרונים|recent documents)$', re.IGNORECASE), 'recent_feed'),
            (re.compile(r'^show latest (?P<limit>\d{1,2}) documents$', re.IGNORECASE), 'recent_feed'),
            # Existing: recent single document
            (re.compile(r'^(מסמך אחרון|latest document|last document|המסמך האחרון)$', re.IGNORECASE), 'recent'),
            # Tagging / retrieval by tag
            (re.compile(r'^תייג את המסמך הזה כ\s*#(?P<tag>[\w\-]+)$', re.IGNORECASE), 'tag_add'),
            (re.compile(r'^תוסיף תגית\s*#(?P<tag>[\w\-]+)$', re.IGNORECASE), 'tag_add'),
            (re.compile(r'^הסר תגית\s*#(?P<tag>[\w\-]+)$', re.IGNORECASE), 'tag_remove'),
            (re.compile(r'^(show tags for this document|הצג תגיות למסמך הזה)$', re.IGNORECASE), 'tag_show'),
            (re.compile(r'^(documents tagged|מסמכים עם תגית)\s*#(?P<tag>[\w\-]+)$', re.IGNORECASE), 'tag_search'),
            # Predefined lightweight views
            (re.compile(r'^(active contracts|חוזים פעילים)$', re.IGNORECASE), 'view_active_contracts'),
            (re.compile(r'^(insurance documents|מסמכי ביטוח)$', re.IGNORECASE), 'view_insurance_documents'),
            (re.compile(r'^(recent invoices|חשבוניות אחרונות)$', re.IGNORECASE), 'view_recent_invoices'),
            (re.compile(r'^(documents needing review|מסמכים לבדיקה)$', re.IGNORECASE), 'view_needs_review'),
            # New: search by type (Hebrew + English)
            (re.compile(r'^(?:הראה|show|חפש|find)\s+(?P<doc_type>חוזים|contracts|חשבוניות|invoices|קבלות|receipts|ביטוח|insurance|אחריות|warranty|דפי חשבון|bank statements|כרטיס אשראי|credit card)', re.IGNORECASE), 'search'),
            # New: search by vendor/keyword
            (re.compile(r'^(?:חפש|find)\s+(?:מסמך|document|קבלה|receipt)?\s*(?:מ|from|של|by)?\s+(?P<keyword>.+)', re.IGNORECASE), 'search'),
            # Fetch by name: "תביא לי X" / "תראה לי X" / "מצא לי X" / "תמצא לי X"
            (re.compile(r'^(?:תביא|תראה|מצא|תמצא)\s+לי\s+(?P<doc_name>.+)', re.IGNORECASE), 'fetch'),
            # New: document questions (deterministic, owned by DocumentSkill)
            (re.compile(r'^(?P<question>(?:מה סוג|what type|כמה עולה|what.+amount|מי ה|who.+counterparty|תן לי סיכום|give me a summary|מה הסכום|what is the amount|מה התאריך|what is the date).+)', re.IGNORECASE), 'query'),
            # Catch-all: document-oriented Hebrew keywords — MUST be LAST to avoid shadowing
            (re.compile(r'(?:מסמך|חשבונית|ביטוח|חוזה|קבלה|פוליסה|תשלום|הסכם|חשבון|אחריות|ערבות|שטר|תעודה)', re.IGNORECASE), 'doc_search_fallback'),
        ]

    def execute(self, db: Session, member: FamilyMember, command: Command) -> Result:
        dispatch = {
            "save": self._save,
            "list": self._list,
            "search": self._search,
            "recent": self._recent,
            "recent_feed": self._recent_feed,
            "fetch": self._fetch,
            "tag_add": self._tag_add,
            "tag_remove": self._tag_remove,
            "tag_show": self._tag_show,
            "tag_search": self._tag_search,
            "view_active_contracts": self._view_active_contracts,
            "view_insurance_documents": self._view_insurance_documents,
            "view_recent_invoices": self._view_recent_invoices,
            "view_needs_review": self._view_needs_review,
            "query": self._query,
            "doc_search_fallback": self._doc_search_fallback,
            "delete_documents": self._delete_documents,
        }
        handler = dispatch.get(command.action)
        if handler is None:
            return Result(success=False, message=TEMPLATES["error_fallback"])
        return handler(db, member, command.params)

    def get_help(self) -> str:
        return (
            "שלח מסמך או תמונה — שמירה אוטומטית\n"
            "מסמכים — רשימת מסמכים אחרונים\n"
            "מסמכים אחרונים — פיד 5 מסמכים אחרונים\n"
            "מסמך אחרון — המסמך האחרון\n"
            "תוסיף תגית #example — הוספת תגית למסמך שנבחר\n"
            "הסר תגית #example — הסרת תגית\n"
            "מסמכים עם תגית #example — סינון לפי תגית\n"
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

        file_path = params.get("file_path") or params.get("media_file_path") or ""
        logger.info(
            "DocumentSkill._save reached: member_id=%s file_path_present=%s param_keys=%s",
            member.id,
            bool(file_path),
            sorted(list(params.keys())),
        )

        if not file_path:
            logger.warning("DocumentSkill._save: no file_path in params=%s", list(params.keys()))
            return Result(success=False, message=TEMPLATES["error_fallback"])

        try:
            # process_document is async. We need to run it from a sync context.
            # Strategy: always run in a fresh thread with its own event loop.
            # This avoids conflicts with any running event loop (FastAPI, pytest-asyncio).
            import threading

            result_holder: list = []
            exc_holder: list = []

            def run_in_thread():
                import asyncio as _asyncio
                new_loop = _asyncio.new_event_loop()
                _asyncio.set_event_loop(new_loop)
                try:
                    doc = new_loop.run_until_complete(
                        documents.process_document(db, file_path, member.id, "whatsapp")
                    )
                    result_holder.append(doc)
                except Exception as e:
                    exc_holder.append(e)
                finally:
                    new_loop.close()

            t = threading.Thread(target=run_in_thread, daemon=True)
            t.start()
            t.join(timeout=120)

            if exc_holder:
                raise exc_holder[0]
            if not result_holder:
                raise RuntimeError("process_document timed out after 120s")
            doc = result_holder[0]
            logger.info(
                "DocumentSkill._save success: member_id=%s doc_id=%s filename=%s",
                member.id,
                doc.id,
                doc.original_filename,
            )

            return Result(
                success=True,
                message=TEMPLATES["document_saved"].format(filename=doc.original_filename),
                entity_type="document",
                entity_id=doc.id,
                action="saved",
            )
        except Exception as exc:
            logger.error(
                "DocumentSkill._save: failed file_path=%s error=%s: %s",
                file_path, type(exc).__name__, exc,
            )
            return Result(success=False, message=TEMPLATES["error_fallback"])

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

    def _fetch(self, db: Session, member: FamilyMember, params: dict) -> Result:
        denied = check_perm(db, member, "documents", "read")
        if denied:
            return denied

        doc_name = (params.get("doc_name") or "").strip()
        if not doc_name:
            return Result(success=False, message=TEMPLATES["error_fallback"])

        result = search_by_name(db, member.id, doc_name)

        if result is None:
            return Result(success=True, message="לא נמצא מסמך בשם זה 📂")

        if isinstance(result, list):
            logger.info("disambiguation_triggered context=fetch count=%d", len(result))
            return Result(success=True, message=self._build_disambiguation_message(result))

        doc = result
        return Result(
            success=True,
            message="מצאתי את המסמך, אבל עדיין לא ניתן לפתוח אותו ישירות. רוצה סיכום או פרטים ממנו?",
            entity_type="document",
            entity_id=doc.id,
            action="viewed",
        )

    def _format_recent_feed(self, docs: list[Document]) -> str:
        lines = ["🗂️ מסמכים אחרונים:"]
        for i, doc in enumerate(docs, 1):
            dn = getattr(doc, "display_name", None)
            display_name = dn if isinstance(dn, str) and dn else None
            filename = display_name if display_name else (doc.original_filename or "ללא שם")
            doc_type = doc.doc_type or "other"
            doc_date = str(doc.doc_date) if doc.doc_date else ""
            tags = ", ".join(f"#{t}" for t in (doc.tags or [])[:3])
            meta = " | ".join([v for v in [doc_type, doc_date, tags] if v])
            lines.append(f"{i}. {filename}" + (f"\n   {meta}" if meta else ""))
        return "\n".join(lines)

    def _recent_feed(self, db: Session, member: FamilyMember, params: dict) -> Result:
        denied = check_perm(db, member, "documents", "read")
        if denied:
            return denied
        limit = int(params.get("limit", 5))
        docs = get_recent_documents(db, member.id, limit=limit)
        if not docs:
            return Result(success=True, message=TEMPLATES["document_list_empty"])
        return Result(success=True, message=self._format_recent_feed(docs))

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

    def _resolve_target_document(self, db: Session, member: FamilyMember) -> Union[Document, None]:
        resolved = resolve_document_reference(db, member, "this document")
        if isinstance(resolved, list):
            return resolved[0] if resolved else None
        return resolved

    def _tag_add(self, db: Session, member: FamilyMember, params: dict) -> Result:
        denied = check_perm(db, member, "documents", "write")
        if denied:
            return denied
        tag = normalize_tag(params.get("tag", ""))
        if not tag:
            return Result(success=False, message=TEMPLATES["error_fallback"])
        doc = self._resolve_target_document(db, member)
        if not doc:
            return Result(success=True, message=TEMPLATES["document_list_empty"])
        doc.tags = merge_tags(doc.tags or [], [tag])
        db.commit()
        db.refresh(doc)
        update_state(db, member.id, entity_type="document", entity_id=doc.id, intent="document.tag")
        return Result(success=True, message=f"הוספתי תגית #{tag} למסמך ✅", entity_type="document", entity_id=doc.id)

    def _tag_remove(self, db: Session, member: FamilyMember, params: dict) -> Result:
        denied = check_perm(db, member, "documents", "write")
        if denied:
            return denied
        tag = normalize_tag(params.get("tag", ""))
        doc = self._resolve_target_document(db, member)
        if not doc:
            return Result(success=True, message=TEMPLATES["document_list_empty"])
        existing = merge_tags(doc.tags or [], [])
        doc.tags = [t for t in existing if t != tag]
        db.commit()
        db.refresh(doc)
        return Result(success=True, message=f"הסרתי תגית #{tag} מהמסמך ✅", entity_type="document", entity_id=doc.id)

    def _tag_show(self, db: Session, member: FamilyMember, params: dict) -> Result:
        denied = check_perm(db, member, "documents", "read")
        if denied:
            return denied
        doc = self._resolve_target_document(db, member)
        if not doc:
            return Result(success=True, message=TEMPLATES["document_list_empty"])
        tags = merge_tags(doc.tags or [], [])
        if not tags:
            return Result(success=True, message="אין תגיות למסמך הזה.")
        return Result(success=True, message="תגיות למסמך: " + ", ".join(f"#{t}" for t in tags))

    def _tag_search(self, db: Session, member: FamilyMember, params: dict) -> Result:
        denied = check_perm(db, member, "documents", "read")
        if denied:
            return denied
        tag = normalize_tag(params.get("tag", ""))
        results = search_documents(db, member.id, {"tag": tag, "limit": 20})
        if not results:
            return Result(success=True, message=TEMPLATES["document_search_empty"])
        return Result(success=True, message=format_search_results(results))

    def _view_by_name(self, db: Session, member: FamilyMember, view_name: str) -> Result:
        denied = check_perm(db, member, "documents", "read")
        if denied:
            return denied
        filters = get_view_filters(view_name)
        results = search_documents(db, member.id, filters)
        if not results:
            return Result(success=True, message=TEMPLATES["document_search_empty"])
        return Result(success=True, message=format_search_results(results))

    def _view_active_contracts(self, db: Session, member: FamilyMember, params: dict) -> Result:
        return self._view_by_name(db, member, "active_contracts")

    def _view_insurance_documents(self, db: Session, member: FamilyMember, params: dict) -> Result:
        return self._view_by_name(db, member, "insurance_documents")

    def _view_recent_invoices(self, db: Session, member: FamilyMember, params: dict) -> Result:
        return self._view_by_name(db, member, "recent_invoices")

    def _view_needs_review(self, db: Session, member: FamilyMember, params: dict) -> Result:
        return self._view_by_name(db, member, "needs_review")

    def _query(self, db: Session, member: FamilyMember, params: dict) -> Result:
        denied = check_perm(db, member, "documents", "read")
        if denied:
            return denied

        question = params.get("question", params.get("raw_text", ""))

        # Resolve which document the user is asking about
        resolved = resolve_document_reference(db, member, question)
        logger.info("document_match_count count=%d", len(resolved) if isinstance(resolved, list) else (1 if resolved else 0))

        if resolved is None:
            return Result(success=True, message=TEMPLATES["document_list_empty"])

        # Multiple candidates — ask for clarification
        if isinstance(resolved, list):
            logger.info("disambiguation_triggered context=query count=%d", len(resolved))
            return Result(success=True, message=self._build_disambiguation_message(resolved))

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
    # Catch-all fallback for document-oriented messages
    # ------------------------------------------------------------------

    # Hebrew question indicators (question mark or question words)
    _QUESTION_INDICATORS = re.compile(
        r'\?|מה |מי |כמה |איזה |למה |מתי |האם |איפה |איך '
    )

    # Document-related keywords for extraction from the message
    _DOC_KEYWORDS = [
        "מסמך", "חשבונית", "ביטוח", "חוזה", "קבלה", "פוליסה",
        "תשלום", "הסכם", "חשבון", "אחריות", "ערבות", "שטר", "תעודה",
    ]

    def _doc_search_fallback(self, db: Session, member: FamilyMember, params: dict) -> Result:
        """Catch-all handler for document-oriented messages that didn't match specific patterns.

        Extracts keywords from the message, searches documents, and either
        delegates to answer_document_question (single match + question) or
        returns search results.
        """
        denied = check_perm(db, member, "documents", "read")
        if denied:
            return denied

        raw_text = params.get("raw_text", "")

        # Extract document-related keywords from the message
        keywords = [kw for kw in self._DOC_KEYWORDS if kw in raw_text]

        # Search documents using extracted keywords
        results: list[Document] = []
        for kw in keywords:
            found = search_documents(db, member.id, {"keyword": kw})
            for doc in found:
                if doc not in results:
                    results.append(doc)
            if results:
                break  # Use first keyword that yields results

        # If no keyword search results, try a broad search with the full message
        if not results:
            # Strip common question words to get a cleaner search term
            search_text = raw_text.strip()
            for prefix in ["מה ", "כמה ", "איזה ", "מי ", "האם ", "איפה ", "מתי ", "איך ", "למה "]:
                if search_text.startswith(prefix):
                    search_text = search_text[len(prefix):]
                    break
            if search_text:
                results = search_documents(db, member.id, {"keyword": search_text.strip()})

        if not results:
            return Result(success=True, message="לא נמצאו מסמכים רלוונטיים 📂")

        # Single match + question → delegate to answer_document_question
        is_question = bool(self._QUESTION_INDICATORS.search(raw_text))
        if len(results) == 1 and is_question:
            doc = results[0]
            update_state(db, member.id, entity_type="document", entity_id=doc.id, intent="document.query")

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
                        answer_document_question(db, member, raw_text, doc),
                    ).result()
            else:
                qa_result = asyncio.run(answer_document_question(db, member, raw_text, doc))

            return Result(
                success=True,
                message=qa_result.answer_text,
                entity_type="document",
                entity_id=doc.id,
                action="queried",
            )

        # Multiple results + question → disambiguation
        if len(results) > 1 and is_question:
            logger.info("disambiguation_triggered context=doc_search_fallback count=%d", len(results))
            return Result(success=True, message=self._build_disambiguation_message(results))

        # Multiple results or non-question → return search results
        return Result(success=True, message=format_search_results(results))

    def _build_disambiguation_message(self, docs: list[Document]) -> str:
        from src.prompts.personality import _DOC_TYPE_EMOJI

        options = []
        for i, doc in enumerate(docs[:5], 1):
            emoji = _DOC_TYPE_EMOJI.get(doc.doc_type or "other", "📎")
            dn = getattr(doc, "display_name", None)
            title = dn if isinstance(dn, str) and dn else (doc.original_filename or "מסמך לא מזוהה")
            options.append(f"{i}. {emoji} {title}")
        return "מצאתי כמה מסמכים דומים:\n" + "\n".join(options) + "\n\nעל איזה מהם מדובר?"

    def _delete_documents(self, db: Session, member: FamilyMember, params: dict) -> Result:
        denied = check_perm(db, member, "documents", "write")
        if denied:
            return denied
        return Result(success=True, message="זיהיתי בקשה למחיקת מסמכים. הפעולה הזו עדיין לא זמינה במערכת.")

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def verify(self, db: Session, result: Result) -> bool:
        if result.entity_id is None:
            return True
        doc = db.query(Document).filter(Document.id == result.entity_id).first()
        return doc is not None
