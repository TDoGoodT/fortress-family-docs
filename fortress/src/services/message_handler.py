"""Fortress 2.0 message handler — core WhatsApp message processing logic."""

import logging

from sqlalchemy.orm import Session

from src.models.schema import Conversation
from src.services.audit import log_action
from src.services.auth import check_permission, get_family_member_by_phone
from src.services.documents import process_document
from src.services.tasks import complete_task, create_task, list_tasks

logger = logging.getLogger(__name__)


async def handle_incoming_message(
    db: Session,
    phone: str,
    message_text: str,
    message_id: str,
    *,
    has_media: bool = False,
    media_file_path: str | None = None,
) -> str:
    """Process an incoming WhatsApp message and return the response text."""
    member = get_family_member_by_phone(db, phone)

    if member is None:
        response = "מספר לא מזוהה. פנה למנהל המשפחה."
        _save_conversation(db, None, message_text, response, "unknown_sender")
        return response

    if not member.is_active:
        response = "החשבון שלך לא פעיל."
        _save_conversation(db, member.id, message_text, response, "inactive_member")
        return response

    if has_media and media_file_path:
        if not check_permission(db, phone, "documents", "write"):
            response = "אין לך הרשאה להעלות מסמכים 🔒"
            log_action(
                db,
                actor_id=member.id,
                action="permission_denied",
                resource_type="documents",
                details={"attempted_action": "write"},
            )
            _save_conversation(db, member.id, message_text, response, "permission_denied")
            return response
        response = await _handle_media(db, member, media_file_path)
        _save_conversation(db, member.id, message_text, response, "media_received")
        return response

    response = _handle_text(db, member, phone, message_text)
    _save_conversation(db, member.id, message_text, response, "text_message")
    return response


async def _handle_media(db: Session, member, file_path: str) -> str:
    """Store a received media file as a document."""
    try:
        await process_document(db, file_path, member.id, "whatsapp")
        log_action(
            db,
            actor_id=member.id,
            action="document_received_whatsapp",
            resource_type="document",
            details={"file_path": file_path},
        )
        return "קיבלתי את הקובץ ✅ נשמר בהצלחה."
    except Exception:
        logger.exception("Error processing media from %s", member.phone)
        return "שגיאה בשמירת הקובץ. נסה שוב."


def _handle_text(db: Session, member, phone: str, message_text: str) -> str:
    """Route a text message to the appropriate handler based on keywords."""
    text = message_text.strip()
    text_lower = text.lower()

    # List tasks
    if text in ("משימות",) or text_lower == "tasks":
        if not check_permission(db, phone, "tasks", "read"):
            log_action(
                db,
                actor_id=member.id,
                action="permission_denied",
                resource_type="tasks",
                details={"attempted_action": "read"},
            )
            return "אין לך הרשאה לצפות במשימות 🔒"
        return _handle_list_tasks(db, member)

    # Create task
    if text.startswith("משימה חדשה:") or text_lower.startswith("new task:"):
        if not check_permission(db, phone, "tasks", "write"):
            log_action(
                db,
                actor_id=member.id,
                action="permission_denied",
                resource_type="tasks",
                details={"attempted_action": "write"},
            )
            return "אין לך הרשאה ליצור משימות 🔒"
        separator = "משימה חדשה:" if text.startswith("משימה חדשה:") else "new task:"
        title = text.split(separator, 1)[1].strip()
        if title:
            return _handle_create_task(db, member, title)

    # Complete task
    if text.startswith("סיום משימה") or text_lower.startswith("done"):
        if not check_permission(db, phone, "tasks", "write"):
            log_action(
                db,
                actor_id=member.id,
                action="permission_denied",
                resource_type="tasks",
                details={"attempted_action": "write"},
            )
            return "אין לך הרשאה לעדכן משימות 🔒"
        return _handle_complete_task(db, member, text)

    # Default acknowledgment
    preview = text[:50]
    suffix = "..." if len(text) > 50 else ""
    return f"קיבלתי: {preview}{suffix} (בקרוב אוכל לעזור יותר 🤖)"


def _handle_list_tasks(db: Session, member) -> str:
    """List open tasks assigned to the member."""
    tasks = list_tasks(db, status="open", assigned_to=member.id)
    if not tasks:
        return "אין משימות פתוחות 🎉"
    lines = []
    for i, task in enumerate(tasks, 1):
        due = f" (עד {task.due_date})" if task.due_date else ""
        lines.append(f"{i}. {task.title}{due}")
    return "\n".join(lines)


def _handle_create_task(db: Session, member, title: str) -> str:
    """Create a new task assigned to the sender."""
    create_task(db, title, member.id, assigned_to=member.id)
    return f"משימה נוצרה: {title} ✅"


def _handle_complete_task(db: Session, member, text: str) -> str:
    """Complete a task by index from the member's open task list."""
    # Extract number from text like "סיום משימה 2" or "done 2"
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
    return "משימה הושלמה ✅"


def _save_conversation(
    db: Session,
    member_id,
    message_in: str,
    message_out: str,
    intent: str,
) -> None:
    """Save the conversation exchange to the database."""
    conv = Conversation(
        family_member_id=member_id,
        message_in=message_in,
        message_out=message_out,
        intent=intent,
    )
    db.add(conv)
    db.commit()
