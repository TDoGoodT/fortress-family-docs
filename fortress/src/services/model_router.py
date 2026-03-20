"""Fortress 2.0 model router — intent-based message routing with LLM responses."""

import json
import logging

from sqlalchemy.orm import Session

from src.models.schema import Conversation, FamilyMember
from src.prompts.system_prompts import (
    FORTRESS_BASE,
    TASK_EXTRACTOR,
    TASK_RESPONDER,
)
from src.services.audit import log_action
from src.services.auth import check_permission
from src.services.documents import process_document
from src.services.intent_detector import INTENTS, detect_intent
from src.services.llm_client import HEBREW_FALLBACK, OllamaClient
from src.services.tasks import complete_task, create_task, list_tasks

logger = logging.getLogger(__name__)

# Permission requirements per intent: (resource_type, action) or None
_PERMISSION_MAP: dict[str, tuple[str, str] | None] = {
    "list_tasks": ("tasks", "read"),
    "create_task": ("tasks", "write"),
    "complete_task": ("tasks", "write"),
    "greeting": None,
    "upload_document": ("documents", "write"),
    "list_documents": ("documents", "read"),
    "ask_question": None,
    "unknown": None,
}


async def route_message(
    db: Session,
    member: FamilyMember,
    phone: str,
    message_text: str,
    has_media: bool = False,
    media_file_path: str | None = None,
) -> str:
    """Route a message through intent detection, permission check, handler, and save conversation."""
    llm = OllamaClient()
    intent = await detect_intent(message_text, has_media, llm)
    logger.info("Route: intent=%s | member=%s", intent, member.name)

    # Permission check
    perm = _PERMISSION_MAP.get(intent)
    if perm is not None:
        resource_type, action = perm
        if not check_permission(db, phone, resource_type, action):
            logger.info("Permission: %s/%s = denied | member=%s", resource_type, action, member.name)
            log_action(
                db,
                actor_id=member.id,
                action="permission_denied",
                resource_type=resource_type,
                details={"attempted_action": action, "intent": intent},
            )
            response = f"אין לך הרשאה לביצוע פעולה זו 🔒"
            _save_conversation(db, member.id, message_text, response, intent)
            return response

    # Dispatch to handler
    handler = _HANDLERS.get(intent, _handle_unknown)
    logger.info("Dispatch: intent=%s | handler=%s", intent, handler.__name__)
    response = await handler(db, member, message_text, llm, media_file_path)

    _save_conversation(db, member.id, message_text, response, intent)
    return response


async def _handle_list_tasks(
    db: Session,
    member: FamilyMember,
    message_text: str,
    llm: OllamaClient,
    media_file_path: str | None,
) -> str:
    """Fetch open tasks and format via LLM."""
    tasks = list_tasks(db, status="open", assigned_to=member.id)
    if not tasks:
        prompt = "אין משימות פתוחות. צור תשובה קצרה ושמחה בעברית."
        return await llm.generate(prompt=prompt, system_prompt=FORTRESS_BASE)

    task_lines = []
    for i, task in enumerate(tasks, 1):
        due = f" (עד {task.due_date})" if task.due_date else ""
        priority = task.priority if hasattr(task, "priority") else "normal"
        task_lines.append(f"{i}. [{priority}] {task.title}{due}")

    task_data = "\n".join(task_lines)
    prompt = f"הנה רשימת המשימות:\n{task_data}\n\nפרמט את זה יפה לוואטסאפ."
    return await llm.generate(prompt=prompt, system_prompt=TASK_RESPONDER)


async def _handle_create_task(
    db: Session,
    member: FamilyMember,
    message_text: str,
    llm: OllamaClient,
    media_file_path: str | None,
) -> str:
    """Extract task details via LLM and create the task."""
    extraction = await llm.generate(
        prompt=message_text,
        system_prompt=TASK_EXTRACTOR,
    )
    try:
        details = json.loads(extraction)
        title = details.get("title", "").strip()
    except (json.JSONDecodeError, AttributeError):
        # Fallback: extract title from keyword format
        text = message_text.strip()
        if text.startswith("משימה חדשה:"):
            title = text.split("משימה חדשה:", 1)[1].strip()
        elif text.lower().startswith("new task:"):
            title = text.split(":", 1)[1].strip()
        else:
            title = text
        details = {}

    if not title:
        return "לא הצלחתי להבין את פרטי המשימה. נסה לכתוב: משימה חדשה: [שם המשימה]"

    due_date = details.get("due_date")
    category = details.get("category")
    priority = details.get("priority", "normal")

    create_task(
        db,
        title,
        member.id,
        assigned_to=member.id,
        due_date=due_date,
        category=category,
        priority=priority,
    )

    prompt = f"משימה חדשה נוצרה: {title}. צור אישור קצר בעברית."
    return await llm.generate(prompt=prompt, system_prompt=FORTRESS_BASE)


async def _handle_complete_task(
    db: Session,
    member: FamilyMember,
    message_text: str,
    llm: OllamaClient,
    media_file_path: str | None,
) -> str:
    """Identify and complete a task."""
    text = message_text.strip()
    parts = text.split()
    number_str = parts[-1] if parts else ""

    if not number_str.isdigit():
        return "שלח 'סיום משימה' ואחריו מספר המשימה."

    index = int(number_str)
    tasks = list_tasks(db, status="open", assigned_to=member.id)
    if index < 1 or index > len(tasks):
        return f"מספר משימה לא תקין. יש {len(tasks)} משימות פתוחות."

    task = tasks[index - 1]
    complete_task(db, task.id)

    prompt = f"המשימה '{task.title}' הושלמה. צור אישור קצר ושמח בעברית."
    return await llm.generate(prompt=prompt, system_prompt=FORTRESS_BASE)


async def _handle_greeting(
    db: Session,
    member: FamilyMember,
    message_text: str,
    llm: OllamaClient,
    media_file_path: str | None,
) -> str:
    """Generate a personalized greeting."""
    prompt = f"ברך את {member.name} בברכה חמה וקצרה בעברית."
    return await llm.generate(prompt=prompt, system_prompt=FORTRESS_BASE)


async def _handle_upload_document(
    db: Session,
    member: FamilyMember,
    message_text: str,
    llm: OllamaClient,
    media_file_path: str | None,
) -> str:
    """Save document and acknowledge."""
    if not media_file_path:
        return "לא התקבל קובץ. נסה לשלוח שוב."
    try:
        await process_document(db, media_file_path, member.id, "whatsapp")
        log_action(
            db,
            actor_id=member.id,
            action="document_received_whatsapp",
            resource_type="document",
            details={"file_path": media_file_path},
        )
        prompt = "קובץ התקבל ונשמר בהצלחה. צור אישור קצר בעברית."
        return await llm.generate(prompt=prompt, system_prompt=FORTRESS_BASE)
    except Exception:
        logger.exception("Error processing media from %s", member.phone)
        return "שגיאה בשמירת הקובץ. נסה שוב."


async def _handle_list_documents(
    db: Session,
    member: FamilyMember,
    message_text: str,
    llm: OllamaClient,
    media_file_path: str | None,
) -> str:
    """Return a summary of recent documents."""
    from src.models.schema import Document

    docs = (
        db.query(Document)
        .filter(Document.uploaded_by == member.id)
        .order_by(Document.created_at.desc())
        .limit(10)
        .all()
    )
    if not docs:
        prompt = "אין מסמכים. צור תשובה קצרה בעברית."
        return await llm.generate(prompt=prompt, system_prompt=FORTRESS_BASE)

    doc_lines = []
    for i, doc in enumerate(docs, 1):
        name = doc.original_filename or doc.file_path.split("/")[-1]
        doc_lines.append(f"{i}. {name}")

    prompt = f"הנה רשימת המסמכים האחרונים:\n" + "\n".join(doc_lines)
    return await llm.generate(prompt=prompt, system_prompt=FORTRESS_BASE)


async def _handle_ask_question(
    db: Session,
    member: FamilyMember,
    message_text: str,
    llm: OllamaClient,
    media_file_path: str | None,
) -> str:
    """Answer a question using LLM."""
    return await llm.generate(prompt=message_text, system_prompt=FORTRESS_BASE)


async def _handle_unknown(
    db: Session,
    member: FamilyMember,
    message_text: str,
    llm: OllamaClient,
    media_file_path: str | None,
) -> str:
    """Return a helpful message for unrecognized intents."""
    return (
        "לא הבנתי את הבקשה 🤔\n"
        "אפשר לנסות:\n"
        "• משימות — לצפות במשימות\n"
        "• משימה חדשה: [שם] — ליצור משימה\n"
        "• סיום משימה [מספר] — לסיים משימה\n"
        "• מסמכים — לצפות במסמכים\n"
        "• או לשלוח קובץ"
    )


# Handler dispatch table
_HANDLERS: dict = {
    "list_tasks": _handle_list_tasks,
    "create_task": _handle_create_task,
    "complete_task": _handle_complete_task,
    "greeting": _handle_greeting,
    "upload_document": _handle_upload_document,
    "list_documents": _handle_list_documents,
    "ask_question": _handle_ask_question,
    "unknown": _handle_unknown,
}


def _save_conversation(
    db: Session,
    member_id,
    message_in: str,
    message_out: str,
    intent: str,
) -> None:
    """Save the conversation exchange to the database."""
    try:
        conv = Conversation(
            family_member_id=member_id,
            message_in=message_in,
            message_out=message_out,
            intent=intent,
        )
        db.add(conv)
        db.commit()
    except Exception:
        logger.exception("Failed to save conversation")
