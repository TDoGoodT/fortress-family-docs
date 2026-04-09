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
from src.services.conversation_state import set_pending_confirmation, update_state
from src.utils.async_bridge import run_async
from src.services.document_query_service import (
    QAResult,
    answer_document_question,
    get_document_recipes,
    get_recipe_details,
    get_recent_documents,
    get_view_filters,
    list_member_recipes,
    merge_tags,
    normalize_tag,
    resolve_document_reference,
    search_by_name,
    search_documents,
    search_recipes,
)
from src.skills.base_skill import BaseSkill, Command, Result
from src.skills.permissions import check_perm

logger = logging.getLogger(__name__)


def _build_document_saved_message(doc: Document) -> str:
    filename = doc.display_name or doc.original_filename
    if doc.doc_type != "salary_slip":
        return TEMPLATES["document_saved"].format(filename=filename)

    metadata = getattr(doc, "doc_metadata", {}) or {}
    structured = metadata.get("structured_payload", {}) if isinstance(metadata, dict) else {}
    pay_month = structured.get("pay_month") if isinstance(structured, dict) else None

    parts = [f"שמרתי תלוש שכר ✅ {filename}"]
    if pay_month:
        parts.append(f"חודש: {pay_month}")
    if getattr(doc, "review_state", None) == "needs_review":
        parts.append("מסומן לבדיקה")
    return "\n".join(parts)


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
            # Recipe commands: list
            (re.compile(r'^(מתכונים|מתכונים שלי|הראה מתכונים)$', re.IGNORECASE), 'recipe_list'),
            # Recipe knowledge queries: "יש לי מתכונים?", "איזה מתכונים יש לי?"
            (re.compile(r'^(?:יש לי|איזה)\s+(?:מתכונים)', re.IGNORECASE), 'recipe_list'),
            (re.compile(r'^(?:מה יש לי|מה יש)\s+(?:מתכונים)', re.IGNORECASE), 'recipe_list'),
            # Recipe commands: search
            (re.compile(r'^(?:חפש מתכון|יש מתכון ל)\s*(?P<recipe_query>.+)', re.IGNORECASE), 'recipe_search'),
            # Recipe commands: how-to / preparation
            (re.compile(r'^(?:איך מכינים|מה המתכון ל)\s*(?P<recipe_name>.+)', re.IGNORECASE), 'recipe_howto'),
            # Recipe commands: recipes in a document
            (re.compile(r'^(?:מה יש ב|מתכונים של|מתכונים ב)\s*(?P<doc_query>.+)', re.IGNORECASE), 'recipe_in_doc'),
            # Generic free-text search: "חפש X" / "search X" (MUST be after specific search patterns)
            (re.compile(r'^(?:חפש|search)\s+(?P<keyword>.+)', re.IGNORECASE), 'search'),
            # Recipe catch-all: any message mentioning מתכון/מתכונים that wasn't caught above
            (re.compile(r'(?:מתכון|מתכונים|recipe)', re.IGNORECASE), 'recipe_fallback'),
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
            "recipe_list": self._recipe_list,
            "recipe_search": self._recipe_search,
            "recipe_howto": self._recipe_howto,
            "recipe_in_doc": self._recipe_in_doc,
            "recipe_fallback": self._recipe_fallback,
            "doc_search_fallback": self._doc_search_fallback,
            "delete_documents": self._delete_documents,
            "save_text": self._save_text,
            "summary": self._summary,
            "contextual_query": self._contextual_query,
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

            # Track last saved document in conversation state for follow-up queries
            update_state(db, member.id, entity_type="document", entity_id=doc.id, intent="document.save")

            # Check if this was a duplicate
            if getattr(doc, "_is_duplicate", False):
                dn = getattr(doc, "display_name", None) or doc.original_filename or "מסמך"
                return Result(
                    success=True,
                    message=f"המסמך הזה כבר קיים במערכת 📋 {dn}",
                    entity_type="document",
                    entity_id=doc.id,
                    action="duplicate",
                )

            return Result(
                success=True,
                message=_build_document_saved_message(doc),
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

    def _save_text(self, db: Session, member: FamilyMember, params: dict) -> Result:
        """Save pasted text as a document through the enrichment pipeline."""
        denied = check_perm(db, member, "documents", "write")
        if denied:
            return denied

        text = (params.get("text") or "").strip()
        if not text:
            return Result(success=False, message="לא ניתן לשמור טקסט ריק 📝")

        title = params.get("title") or None

        try:
            import threading

            result_holder: list = []
            exc_holder: list = []

            def run_in_thread():
                import asyncio as _asyncio
                new_loop = _asyncio.new_event_loop()
                _asyncio.set_event_loop(new_loop)
                try:
                    doc = new_loop.run_until_complete(
                        documents.process_text(db, text, member.id, title)
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
                raise RuntimeError("process_text timed out after 120s")
            doc = result_holder[0]

            dn = getattr(doc, "display_name", None) or doc.original_filename or "מסמך"
            doc_type = doc.doc_type or "other"

            update_state(db, member.id, entity_type="document", entity_id=doc.id, intent="document.save_text")

            return Result(
                success=True,
                message=f"שמרתי: {dn} ({doc_type}) ✅",
                entity_type="document",
                entity_id=doc.id,
                action="saved",
            )
        except Exception as exc:
            logger.error(
                "DocumentSkill._save_text: failed error=%s: %s",
                type(exc).__name__, exc,
            )
            return Result(success=False, message=TEMPLATES["error_fallback"])

    def _list(self, db: Session, member: FamilyMember, params: dict) -> Result:
        """Waterfall browse — show document categories with counts."""
        denied = check_perm(db, member, "documents", "read")
        if denied:
            return denied

        from src.services.document_browse_queries import get_categories
        from src.services.browse_formatter import format_category_view
        from src.services.browsing_state import BrowsingState, set_browsing_state

        categories = get_categories(db, member.id)
        if not categories:
            return Result(success=True, message=TEMPLATES["document_list_empty"])

        items = [{"key": c.doc_type, "label": c.label} for c in categories]
        set_browsing_state(db, member.id, BrowsingState(level="categories", items=items))

        return Result(success=True, message=format_category_view(categories))

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
            # Store pending disambiguation so user can pick by number
            doc_ids = [str(d.id) for d in result[:5]]
            set_pending_confirmation(
                db, member.id, "document.disambiguate",
                {"doc_ids": doc_ids, "doc_name": doc_name},
            )
            return Result(success=True, message=self._build_disambiguation_message(result))

        doc = result
        # Store pending confirmation so "כן" resolves to summary
        set_pending_confirmation(
            db, member.id, "document.summary",
            {"doc_id": str(doc.id), "doc_name": doc_name},
        )
        # Update conversation state with the resolved document
        update_state(db, member.id, entity_type="document", entity_id=doc.id, intent="document.fetch")
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

        # Answer the question — no timeout (document QA can be slow)
        qa_result: QAResult = run_async(answer_document_question(db, member, question, doc))

        return Result(
            success=True,
            message=qa_result.answer_text,
            entity_type="document",
            entity_id=doc.id,
            action="queried",
        )

    # ------------------------------------------------------------------
    # Pending confirmation handlers
    # ------------------------------------------------------------------

    def _summary(self, db: Session, member: FamilyMember, params: dict) -> Result:
        """Return the AI summary for a document (used by confirm re-dispatch)."""
        denied = check_perm(db, member, "documents", "read")
        if denied:
            return denied

        doc_id = params.get("doc_id")
        if not doc_id:
            return Result(success=False, message=TEMPLATES["error_fallback"])

        from uuid import UUID
        try:
            doc = db.query(Document).filter(Document.id == UUID(doc_id)).first()
        except (ValueError, AttributeError):
            doc = None

        if not doc:
            return Result(success=True, message="לא נמצא מסמך 📂")

        summary = getattr(doc, "ai_summary", None)
        if summary and str(summary).strip():
            return Result(
                success=True,
                message=f"📄 סיכום המסמך:\n{summary}",
                entity_type="document",
                entity_id=doc.id,
                action="summarized",
            )
        return Result(success=True, message="אין סיכום זמין למסמך הזה")

    def _contextual_query(self, db: Session, member: FamilyMember, params: dict) -> Result:
        """Handle a short follow-up question about the last-viewed document."""
        denied = check_perm(db, member, "documents", "read")
        if denied:
            return denied

        question = params.get("question", params.get("raw_text", ""))
        doc_id = params.get("doc_id")
        if not doc_id:
            return Result(success=False, message=TEMPLATES["error_fallback"])

        from uuid import UUID
        try:
            doc = db.query(Document).filter(Document.id == UUID(str(doc_id))).first()
        except (ValueError, AttributeError):
            doc = None

        if not doc:
            return Result(success=True, message="לא נמצא מסמך 📂")

        update_state(db, member.id, entity_type="document", entity_id=doc.id, intent="document.query")

        # Answer the question — no timeout (document QA can be slow)
        qa_result: QAResult = run_async(answer_document_question(db, member, question, doc))

        return Result(
            success=True,
            message=qa_result.answer_text,
            entity_type="document",
            entity_id=doc.id,
            action="queried",
        )

    # ------------------------------------------------------------------
    # Recipe handlers
    # ------------------------------------------------------------------

    def _recipe_list(self, db: Session, member: FamilyMember, params: dict) -> Result:
        """List all recipes for the member."""
        denied = check_perm(db, member, "documents", "read")
        if denied:
            return denied

        recipes = list_member_recipes(db, member.id)
        if not recipes:
            return Result(success=True, message=TEMPLATES.get("recipe_list_empty", "אין מתכונים שמורים 📂"))

        lines = [TEMPLATES.get("recipe_list_header", "🍳 המתכונים שלך:\n")]
        for i, r in enumerate(recipes, 1):
            lines.append(f"🍳 {i}. {r['recipe_name']}\n   מתוך: {r['display_name']}")
        return Result(success=True, message="\n".join(lines))

    def _recipe_search(self, db: Session, member: FamilyMember, params: dict) -> Result:
        """Search recipes by name or ingredient."""
        denied = check_perm(db, member, "documents", "read")
        if denied:
            return denied

        query = (params.get("recipe_query") or "").strip()
        if not query:
            return Result(success=False, message=TEMPLATES["error_fallback"])

        results = search_recipes(db, member.id, query)
        if not results:
            return Result(success=True, message=TEMPLATES.get("recipe_search_empty", "לא נמצאו מתכונים תואמים 🍳"))

        lines = ["🔍 תוצאות חיפוש מתכונים:"]
        for i, r in enumerate(results, 1):
            lines.append(f"🍳 {i}. {r['recipe_name']} (מתוך {r['display_name']})")
        return Result(success=True, message="\n".join(lines))

    def _recipe_howto(self, db: Session, member: FamilyMember, params: dict) -> Result:
        """Return preparation instructions for a specific recipe."""
        denied = check_perm(db, member, "documents", "read")
        if denied:
            return denied

        recipe_name = (params.get("recipe_name") or "").strip()
        if not recipe_name:
            return Result(success=False, message=TEMPLATES["error_fallback"])

        details = get_recipe_details(db, member.id, recipe_name)
        if not details:
            return Result(success=True, message=TEMPLATES.get("recipe_not_found", "לא מצאתי את המתכון הזה 🤷"))

        lines = [f"🍳 {details['recipe_name']}"]
        if details.get("ingredients"):
            lines.append(f"\n📝 מצרכים:\n{details['ingredients']}")
        if details.get("instructions"):
            lines.append(f"\n👩‍🍳 הוראות הכנה:\n{details['instructions']}")
        if details.get("servings"):
            lines.append(f"\n🍽️ מנות: {details['servings']}")
        if details.get("prep_time"):
            lines.append(f"\n⏱️ זמן הכנה: {details['prep_time']}")
        if details.get("display_name"):
            lines.append(f"\nמתוך: {details['display_name']}")
        return Result(success=True, message="\n".join(lines))

    def _recipe_in_doc(self, db: Session, member: FamilyMember, params: dict) -> Result:
        """List recipes within a specific document."""
        denied = check_perm(db, member, "documents", "read")
        if denied:
            return denied

        doc_query = (params.get("doc_query") or "").strip()
        if not doc_query:
            return Result(success=False, message=TEMPLATES["error_fallback"])

        # Resolve the document by name
        result = search_by_name(db, member.id, doc_query)
        if result is None:
            return Result(success=True, message="לא נמצא מסמך בשם זה 📂")

        # If multiple matches, use the first one
        doc = result[0] if isinstance(result, list) else result

        recipes = get_document_recipes(db, member.id, doc.id)
        if not recipes:
            return Result(success=True, message=TEMPLATES.get("recipe_list_empty", "אין מתכונים שמורים 📂"))

        dn = getattr(doc, "display_name", None)
        doc_title = dn if isinstance(dn, str) and dn else doc.original_filename
        lines = [f"🍳 מתכונים ב{doc_title}:"]
        for i, r in enumerate(recipes, 1):
            lines.append(f"{i}. {r['recipe_name']}")
        return Result(success=True, message="\n".join(lines))

    def _recipe_fallback(self, db: Session, member: FamilyMember, params: dict) -> Result:
        """Catch-all for any message mentioning מתכון/מתכונים.

        Extracts a search term from the raw text. If found, searches recipes;
        otherwise lists all recipes for the member.
        """
        denied = check_perm(db, member, "documents", "read")
        if denied:
            return denied

        raw = params.get("raw_text", "")
        # Try to extract a meaningful search query by stripping common filler
        search_term = raw
        for noise in [
            "יש לך", "יש לי", "תחפש לי", "תחפש", "חפש לי", "חפש",
            "אני רוצה", "אני מחפש", "תבדוק אם יש", "תבדוק",
            "שתחפש ותבדוק אם יש לך", "שתחפש",
            "איזה", "איזו", "מתכון", "מתכונים", "recipe",
            "של", "בשבילי", "?", "!",
        ]:
            search_term = search_term.replace(noise, "")
        search_term = search_term.strip()

        # If there's a meaningful search term, search; otherwise list all
        if search_term and len(search_term) >= 2:
            results = search_recipes(db, member.id, search_term)
            if results:
                lines = ["🔍 תוצאות חיפוש מתכונים:"]
                for i, r in enumerate(results, 1):
                    lines.append(f"🍳 {i}. {r['recipe_name']} (מתוך {r['display_name']})")
                return Result(success=True, message="\n".join(lines))
            # No results for search — fall through to list all
            return Result(
                success=True,
                message=f"לא נמצאו מתכונים עבור \"{search_term}\" 🍳\nנסה לשלוח מסמך עם מתכונים ואשמור אותם עבורך.",
            )

        # No search term — list all recipes
        recipes = list_member_recipes(db, member.id)
        if not recipes:
            return Result(
                success=True,
                message="אין מתכונים שמורים עדיין 📂\nשלח לי מסמך או תמונה עם מתכונים ואני אשמור אותם עבורך.",
            )

        lines = [TEMPLATES.get("recipe_list_header", "🍳 המתכונים שלך:\n")]
        for i, r in enumerate(recipes, 1):
            lines.append(f"🍳 {i}. {r['recipe_name']}\n   מתוך: {r['display_name']}")
        return Result(success=True, message="\n".join(lines))

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

            # No timeout — document QA can be slow
            qa_result: QAResult = run_async(answer_document_question(db, member, raw_text, doc))

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
