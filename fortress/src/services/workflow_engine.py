"""Fortress 2.0 Workflow Engine — LangGraph StateGraph replacing model_router."""

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import TypedDict
from uuid import UUID

from langgraph.graph import END, StateGraph
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.models.schema import (
    Conversation,
    ConversationState,
    FamilyMember,
    Memory,
    RecurringPattern,
    Task,
    BugReport,
)
from src.prompts.system_prompts import (
    FORTRESS_BASE,
    TASK_EXTRACTOR_BEDROCK,
    TASK_RESPONDER,
)
from src.prompts.personality import (
    TEMPLATES as PERSONALITY_TEMPLATES,
    format_bug_list,
    format_document_list,
    format_recurring_list,
    format_task_created,
    format_task_list,
    get_greeting,
)
from src.services.audit import log_action
from src.services.auth import check_permission
from src.services.bedrock_client import BedrockClient
from src.services.conversation_state import (
    get_state,
    update_state,
    clear_state,
    set_pending_confirmation,
    resolve_pending,
)
from src.services.documents import process_document
from src.services.intent_detector import detect_intent
from src.services.model_dispatch import ModelDispatcher
from src.services.memory_service import (
    extract_memories_from_message,
    load_memories,
    save_memory,
)
from src.services.unified_handler import handle_with_llm
from src.services import recurring
from src.services.tasks import archive_task, complete_task, create_task, get_task, list_tasks
from src.utils.time_context import format_time_for_prompt

logger = logging.getLogger(__name__)

# Permission requirements per intent: (resource_type, action) or None
_PERMISSION_MAP: dict[str, tuple[str, str] | None] = {
    "list_tasks": ("tasks", "read"),
    "create_task": ("tasks", "write"),
    "complete_task": ("tasks", "write"),
    "delete_task": ("tasks", "write"),
    "greeting": None,
    "upload_document": ("documents", "write"),
    "list_documents": ("documents", "read"),
    "ask_question": None,
    "unknown": None,
    "list_recurring": ("tasks", "read"),
    "create_recurring": ("tasks", "write"),
    "delete_recurring": ("tasks", "write"),
    "report_bug": ("tasks", "write"),
    "list_bugs": ("tasks", "read"),
    "update_task": ("tasks", "write"),
}


def _resolve_member_by_name(db: Session, name: str) -> UUID | None:
    """Case-insensitive partial match on family_members.name. Returns member ID or None."""
    member = (
        db.query(FamilyMember)
        .filter(func.lower(FamilyMember.name).contains(name.lower()))
        .first()
    )
    if member:
        return member.id
    return None


# ---------------------------------------------------------------------------
# Task 8.1: WorkflowState TypedDict with new keys
# ---------------------------------------------------------------------------


class WorkflowState(TypedDict):
    """State object passed through all LangGraph nodes."""

    db: Session
    member: FamilyMember
    phone: str
    message_text: str
    has_media: bool
    media_file_path: str | None
    intent: str
    permission_granted: bool
    memories: list[Memory]
    response: str
    error: str | None
    task_data: dict | None
    from_unified: bool
    delete_target: str | None
    # New keys for Sprint 1
    conv_state: ConversationState | None
    time_context: str
    state_context: str
    created_task_id: UUID | None
    deleted_task_id: UUID | None
    listed_tasks: list
    created_recurring_id: UUID | None


# ---------------------------------------------------------------------------
# Task 8.4: resolve_reference helper
# ---------------------------------------------------------------------------


def resolve_reference(
    db: Session, member_id: UUID, message: str, conv_state: ConversationState | None
) -> UUID | None:
    """Resolve a reference in the message to an entity ID.

    1. Pronoun check: "אותה", "אותו", "את זה", "the same" → last_entity_id
    2. Index check: "משימה N" → task_ids from conv_state.context
    3. Name check: query family_members by name → member.id or None
    """
    if conv_state is None:
        return None

    # 1. Pronoun check
    pronouns = ["אותה", "אותו", "את זה", "the same"]
    for pronoun in pronouns:
        if pronoun in message:
            if conv_state.last_entity_id:
                return conv_state.last_entity_id
            break

    # 2. Index check: "משימה N"
    index_match = re.search(r"משימה\s+(\d+)", message)
    if index_match:
        index = int(index_match.group(1))
        context = conv_state.context or {}
        task_ids = context.get("task_ids", [])
        if 1 <= index <= len(task_ids):
            try:
                return UUID(task_ids[index - 1])
            except (ValueError, TypeError):
                pass

    # 3. Name check
    words = message.strip().split()
    for word in words:
        if len(word) < 2:
            continue
        members = (
            db.query(FamilyMember)
            .filter(func.lower(FamilyMember.name).contains(word.lower()))
            .all()
        )
        if len(members) == 1:
            return members[0].id
        # Ambiguous — return None (caller should ask for clarification)

    return None


# ---------------------------------------------------------------------------
# Task 8.2: confirmation_check_node
# ---------------------------------------------------------------------------

_CONFIRM_YES = {"כן", "yes", "אישור"}
_CONFIRM_NO = {"לא", "no", "ביטול", "עזוב"}


async def confirmation_check_node(state: WorkflowState) -> dict:
    """Check for pending confirmations before intent detection.

    - If pending + user confirms → execute pending action, return result
    - If pending + user cancels → discard pending, return cancelled
    - If pending + other message → clear pending, fall through to intent_node
    - If no pending → fall through to intent_node
    """
    db = state["db"]
    member = state["member"]
    message = state["message_text"].strip().lower()

    conv_state = get_state(db, member.id)
    time_ctx = format_time_for_prompt()
    state_ctx = ""
    if conv_state.last_intent:
        state_ctx = f"הקשר שיחה: כוונה אחרונה={conv_state.last_intent}"
        if conv_state.last_entity_type:
            state_ctx += f", סוג={conv_state.last_entity_type}"
        if conv_state.last_action:
            state_ctx += f", פעולה={conv_state.last_action}"

    result = {
        "conv_state": conv_state,
        "time_context": time_ctx,
        "state_context": state_ctx,
    }

    if not conv_state.pending_confirmation:
        return result

    # Pending confirmation exists
    if message in _CONFIRM_YES:
        pending = resolve_pending(db, member.id)
        if pending:
            action_type = pending.get("type")
            action_data = pending.get("data", {})
            if action_type == "delete_task":
                task_id_str = action_data.get("task_id")
                if task_id_str:
                    try:
                        task_id = UUID(task_id_str)
                        archived = archive_task(db, task_id)
                        if archived:
                            result["response"] = PERSONALITY_TEMPLATES["task_deleted"].format(
                                title=action_data.get("title", "")
                            )
                            result["deleted_task_id"] = task_id
                            result["intent"] = "delete_task"
                        else:
                            result["response"] = PERSONALITY_TEMPLATES["task_not_found"]
                    except (ValueError, TypeError):
                        result["response"] = PERSONALITY_TEMPLATES["error_fallback"]
                else:
                    result["response"] = PERSONALITY_TEMPLATES["error_fallback"]
            else:
                result["response"] = PERSONALITY_TEMPLATES["error_fallback"]
        else:
            result["response"] = PERSONALITY_TEMPLATES["error_fallback"]
        return result

    if message in _CONFIRM_NO:
        resolve_pending(db, member.id)
        clear_state(db, member.id)
        result["response"] = PERSONALITY_TEMPLATES["action_cancelled"]
        return result

    # Other message — clear pending, fall through to intent_node
    conv_state.pending_confirmation = False
    conv_state.pending_action = None
    db.flush()
    return result


# ---------------------------------------------------------------------------
# Task 8.3: cancel_action_node
# ---------------------------------------------------------------------------


async def cancel_action_node(state: WorkflowState) -> dict:
    """Clear conversation state and return cancelled template."""
    db = state["db"]
    member = state["member"]
    clear_state(db, member.id)
    return {"response": PERSONALITY_TEMPLATES["cancelled"]}


# ---------------------------------------------------------------------------
# Node implementations
# ---------------------------------------------------------------------------


async def intent_node(state: WorkflowState) -> dict:
    """Detect intent using synchronous keyword matching."""
    intent = detect_intent(state["message_text"], state["has_media"])
    logger.info("intent_node: intent=%s | member=%s", intent, state["member"].name)
    return {"intent": intent}


async def unified_llm_node(state: WorkflowState) -> dict:
    """Single LLM call: classify intent + generate response."""
    memories = load_memories(state["db"], state["member"].id)
    dispatcher = ModelDispatcher()
    intent, response, task_data = await handle_with_llm(
        state["message_text"], state["member"].name, memories, dispatcher,
    )
    return {
        "intent": intent,
        "response": response,
        "task_data": task_data,
        "from_unified": True,
        "memories": memories,
    }


async def task_create_node(state: WorkflowState) -> dict:
    """Create a task from task_data stored in state, with duplicate check and owner resolution."""
    task_data = state.get("task_data") or {}
    title = task_data.get("title", "").strip()
    if not title:
        return {}

    db = state["db"]
    member = state["member"]

    # Resolve assigned_to from name string
    assigned_to_name = task_data.get("assigned_to")
    assigned_to_id = member.id  # default: sender
    if assigned_to_name and isinstance(assigned_to_name, str):
        resolved = _resolve_member_by_name(db, assigned_to_name)
        if resolved:
            assigned_to_id = resolved
        else:
            logger.warning("task_create_node: name '%s' not found, falling back to sender", assigned_to_name)

    # Duplicate check: same title (case-insensitive), same assigned_to, open, within 5 min
    try:
        five_min_ago = datetime.now(timezone.utc) - timedelta(minutes=5)
        existing = (
            db.query(Task)
            .filter(
                func.lower(Task.title) == title.lower(),
                Task.assigned_to == assigned_to_id,
                Task.status == "open",
                Task.created_at > five_min_ago,
            )
            .first()
        )
        if existing:
            logger.info("task_create_node: duplicate detected for '%s'", title)
            return {"response": PERSONALITY_TEMPLATES["task_duplicate"]}
    except Exception:
        logger.exception("task_create_node: duplicate check failed, proceeding with creation")

    task = create_task(
        db,
        title,
        member.id,
        assigned_to=assigned_to_id,
        due_date=task_data.get("due_date"),
        category=task_data.get("category"),
        priority=task_data.get("priority", "normal"),
    )
    logger.info("task_create_node: created task '%s' for %s", title, member.name)
    return {"created_task_id": task.id}


# ---------------------------------------------------------------------------
# Task 8.8: Modified delete_task flow for confirmation
# ---------------------------------------------------------------------------


async def delete_task_node(state: WorkflowState) -> dict:
    """Identify a task and set pending confirmation instead of immediate delete."""
    db = state["db"]
    member = state["member"]
    message = state["message_text"].strip()
    delete_target = state.get("delete_target")

    tasks = list_tasks(db, status="open", assigned_to=member.id)

    # Try to extract task number from message or delete_target
    number = None
    if delete_target:
        num_match = re.search(r"\d+", str(delete_target))
        if num_match:
            number = int(num_match.group())

    if number is None:
        num_match = re.search(r"\d+", message)
        if num_match:
            number = int(num_match.group())

    task = None
    if number is not None:
        if 1 <= number <= len(tasks):
            task = tasks[number - 1]
        else:
            return {"response": PERSONALITY_TEMPLATES["task_not_found"]}

    if task is None:
        # Try title match
        title_candidate = message
        for kw in ["מחק משימה", "הסר משימה", "בטל משימה", "מחק", "delete task"]:
            title_candidate = title_candidate.replace(kw, "").strip()

        if title_candidate:
            for t in tasks:
                if t.title.lower() == title_candidate.lower():
                    task = t
                    break

    if task is None:
        if not tasks:
            return {"response": PERSONALITY_TEMPLATES["task_not_found"]}
        task_lines = "\n".join(f"{i}. {t.title}" for i, t in enumerate(tasks, 1))
        return {"response": PERSONALITY_TEMPLATES["task_delete_which"].format(task_list=task_lines)}

    # Set pending confirmation instead of immediate delete
    set_pending_confirmation(db, member.id, "delete_task", {"task_id": str(task.id), "title": task.title})
    return {"response": PERSONALITY_TEMPLATES["confirm_delete"].format(title=task.title)}


# ---------------------------------------------------------------------------
# Task 8.7: update_task_node
# ---------------------------------------------------------------------------


async def update_task_node(state: WorkflowState) -> dict:
    """Resolve target task and apply updates."""
    db = state["db"]
    member = state["member"]
    message = state["message_text"].strip()
    conv_state = state.get("conv_state")

    # Try to resolve target task from conversation state or message
    target_id = resolve_reference(db, member.id, message, conv_state)

    if target_id:
        task = get_task(db, target_id)
    else:
        task = None

    if task is None:
        # Show task list for user to pick
        tasks = list_tasks(db, status="open", assigned_to=member.id)
        if not tasks:
            return {"response": PERSONALITY_TEMPLATES["task_not_found"]}
        task_lines = "\n".join(f"{i}. {t.title}" for i, t in enumerate(tasks, 1))
        return {"response": PERSONALITY_TEMPLATES["task_update_which"].format(task_list=task_lines)}

    # Apply updates — for now, extract a new title from the message
    changes = []
    # Strip update keywords to find the new value
    new_value = message
    for kw in ["תשנה", "תעדכן", "עדכן", "שנה", "update"]:
        new_value = new_value.replace(kw, "").strip()

    # Remove reference words
    for ref in ["אותה", "אותו", "את זה", "the same"]:
        new_value = new_value.replace(ref, "").strip()

    if new_value and new_value != message:
        task.title = new_value
        changes.append(f"שם: {new_value}")
        db.flush()

    changes_text = f"\n{', '.join(changes)}" if changes else ""
    return {
        "response": PERSONALITY_TEMPLATES["task_updated"].format(title=task.title, changes=changes_text),
    }


async def permission_node(state: WorkflowState) -> dict:
    """Check permissions; set denial message if denied."""
    intent = state["intent"]
    perm = _PERMISSION_MAP.get(intent)

    if perm is None:
        return {"permission_granted": True}

    resource_type, action = perm
    granted = check_permission(state["db"], state["phone"], resource_type, action)

    if not granted:
        logger.info(
            "permission_node: %s/%s denied | member=%s",
            resource_type,
            action,
            state["member"].name,
        )
        log_action(
            state["db"],
            actor_id=state["member"].id,
            action="permission_denied",
            resource_type=resource_type,
            details={"attempted_action": action, "intent": intent},
        )
        return {
            "permission_granted": False,
            "response": PERSONALITY_TEMPLATES["permission_denied"],
        }

    return {"permission_granted": True}


async def memory_load_node(state: WorkflowState) -> dict:
    """Load relevant memories for the current family member."""
    memories = load_memories(state["db"], state["member"].id)
    return {"memories": memories}


async def action_node(state: WorkflowState) -> dict:
    """Dispatch to the appropriate handler based on intent, using ModelDispatcher."""
    intent = state["intent"]
    db = state["db"]
    member = state["member"]
    message_text = state["message_text"]
    media_file_path = state["media_file_path"]
    dispatcher = ModelDispatcher()

    handler = _ACTION_HANDLERS.get(intent, _handle_unknown)
    response = await handler(db, member, message_text, dispatcher, media_file_path, intent)

    result = {"response": response}

    # Track listed_tasks for state update
    if intent == "list_tasks":
        tasks = list_tasks(db, status="open", assigned_to=member.id)
        result["listed_tasks"] = tasks

    return result


# ---------------------------------------------------------------------------
# Action handlers (ported from model_router.py, using BedrockClient)
# ---------------------------------------------------------------------------


async def _handle_list_tasks(
    db: Session,
    member: FamilyMember,
    message_text: str,
    dispatcher: ModelDispatcher,
    media_file_path: str | None,
    intent: str,
) -> str:
    """Fetch open tasks and format using personality templates."""
    tasks = list_tasks(db, status="open", assigned_to=member.id)
    return format_task_list(tasks)


async def _handle_create_task(
    db: Session,
    member: FamilyMember,
    message_text: str,
    dispatcher: ModelDispatcher,
    media_file_path: str | None,
    intent: str,
) -> str:
    """Extract task details via dispatcher and create the task."""
    extraction = await dispatcher.dispatch(
        prompt=message_text,
        system_prompt=TASK_EXTRACTOR_BEDROCK,
        intent=intent,
    )
    try:
        details = json.loads(extraction)
        title = details.get("title", "").strip()
    except (json.JSONDecodeError, AttributeError):
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

    return format_task_created(title, due_date)


async def _handle_complete_task(
    db: Session,
    member: FamilyMember,
    message_text: str,
    dispatcher: ModelDispatcher,
    media_file_path: str | None,
    intent: str,
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
    return await dispatcher.dispatch(prompt=prompt, system_prompt=FORTRESS_BASE, intent=intent)


async def _handle_greeting(
    db: Session,
    member: FamilyMember,
    message_text: str,
    dispatcher: ModelDispatcher,
    media_file_path: str | None,
    intent: str,
) -> str:
    """Return a local greeting without LLM dispatch."""
    from datetime import datetime
    return get_greeting(member.name, datetime.now().hour)


async def _handle_upload_document(
    db: Session,
    member: FamilyMember,
    message_text: str,
    dispatcher: ModelDispatcher,
    media_file_path: str | None,
    intent: str,
) -> str:
    """Save document and return personality template confirmation."""
    logger.info(
        "upload_document: has_media=%s media_file_path=%s member=%s",
        bool(media_file_path), media_file_path, member.name,
    )
    if not media_file_path:
        return "לא התקבל קובץ. נסה לשלוח שוב."
    try:
        doc = await process_document(db, media_file_path, member.id, "whatsapp")
        log_action(
            db,
            actor_id=member.id,
            action="document_received_whatsapp",
            resource_type="document",
            details={"file_path": media_file_path},
        )
        return PERSONALITY_TEMPLATES["document_saved"].format(filename=doc.original_filename)
    except Exception:
        logger.exception("Error processing media from %s", member.phone)
        return PERSONALITY_TEMPLATES["error_fallback"]


async def _handle_list_documents(
    db: Session,
    member: FamilyMember,
    message_text: str,
    dispatcher: ModelDispatcher,
    media_file_path: str | None,
    intent: str,
) -> str:
    """Return a formatted list of recent documents using personality templates."""
    from src.models.schema import Document

    docs = (
        db.query(Document)
        .filter(Document.uploaded_by == member.id)
        .order_by(Document.created_at.desc())
        .limit(20)
        .all()
    )
    return format_document_list(docs)


async def _handle_ask_question(
    db: Session,
    member: FamilyMember,
    message_text: str,
    dispatcher: ModelDispatcher,
    media_file_path: str | None,
    intent: str,
) -> str:
    """Answer a question using dispatcher (routes to Bedrock Sonnet for high sensitivity)."""
    return await dispatcher.dispatch(
        prompt=message_text, system_prompt=FORTRESS_BASE, intent=intent
    )


async def _handle_list_recurring(
    db: Session,
    member: FamilyMember,
    message_text: str,
    dispatcher: ModelDispatcher,
    media_file_path: str | None,
    intent: str,
) -> str:
    """Fetch active recurring patterns for the member and format them."""
    patterns = (
        db.query(RecurringPattern)
        .filter(
            RecurringPattern.is_active.is_(True),
            RecurringPattern.assigned_to == member.id,
        )
        .all()
    )
    return format_recurring_list(patterns)


async def _handle_create_recurring(
    db: Session,
    member: FamilyMember,
    message_text: str,
    dispatcher: ModelDispatcher,
    media_file_path: str | None,
    intent: str,
) -> str:
    """Parse title + frequency from message and create a recurring pattern."""
    from datetime import date, timedelta

    text = message_text.strip()

    # Strip prefix
    if "תזכורת חדשה:" in text:
        title_part = text.split("תזכורת חדשה:", 1)[1].strip()
    elif text.lower().startswith("recurring:"):
        title_part = text.split(":", 1)[1].strip()
    else:
        title_part = text

    # Parse frequency from Hebrew keywords
    freq_map = {
        "יומי": "daily",
        "שבועי": "weekly",
        "חודשי": "monthly",
        "כל חודש": "monthly",
        "שנתי": "yearly",
    }
    frequency = "monthly"  # default
    for heb_kw, eng_freq in freq_map.items():
        if heb_kw in title_part:
            frequency = eng_freq
            title_part = title_part.replace(heb_kw, "").strip()
            break

    title = title_part.strip()
    if not title:
        title = message_text.strip()

    # Calculate next_due_date as today + one frequency period
    today = date.today()
    if frequency == "daily":
        next_due = today + timedelta(days=1)
    elif frequency == "weekly":
        next_due = today + timedelta(days=7)
    elif frequency == "yearly":
        next_due = date(today.year + 1, today.month, today.day)
    else:  # monthly
        month = today.month % 12 + 1
        year = today.year + (1 if today.month == 12 else 0)
        day = min(today.day, 28)  # safe day for all months
        next_due = date(year, month, day)

    pattern = recurring.create_pattern(
        db,
        title=title,
        frequency=frequency,
        next_due_date=next_due,
        assigned_to=member.id,
    )

    return PERSONALITY_TEMPLATES["recurring_created"].format(
        title=title,
        frequency=frequency,
        next_due_date=str(next_due),
    )


async def _handle_delete_recurring(
    db: Session,
    member: FamilyMember,
    message_text: str,
    dispatcher: ModelDispatcher,
    media_file_path: str | None,
    intent: str,
) -> str:
    """Identify a recurring pattern by number or title and deactivate it."""
    text = message_text.strip()

    # Get active patterns for this member
    patterns = (
        db.query(RecurringPattern)
        .filter(
            RecurringPattern.is_active.is_(True),
            RecurringPattern.assigned_to == member.id,
        )
        .all()
    )

    if not patterns:
        return PERSONALITY_TEMPLATES["recurring_not_found"]

    # Try to find by number
    num_match = re.search(r"\d+", text)
    if num_match:
        index = int(num_match.group())
        if 1 <= index <= len(patterns):
            pattern = patterns[index - 1]
            recurring.deactivate_pattern(db, pattern.id)
            return PERSONALITY_TEMPLATES["recurring_deleted"].format(title=pattern.title)
        return PERSONALITY_TEMPLATES["recurring_not_found"]

    # Try title match: strip delete keywords, use remainder
    title_candidate = text
    for kw in ["מחק תזכורת", "בטל תזכורת", "מחק", "בטל", "delete recurring"]:
        title_candidate = title_candidate.replace(kw, "").strip()

    if title_candidate:
        for pattern in patterns:
            if pattern.title.lower() == title_candidate.lower():
                recurring.deactivate_pattern(db, pattern.id)
                return PERSONALITY_TEMPLATES["recurring_deleted"].format(title=pattern.title)

    return PERSONALITY_TEMPLATES["recurring_not_found"]


async def _handle_unknown(
    db: Session,
    member: FamilyMember,
    message_text: str,
    dispatcher: ModelDispatcher,
    media_file_path: str | None,
    intent: str,
) -> str:
    """Return a helpful message for unrecognized intents."""
    return PERSONALITY_TEMPLATES["cant_understand"].format(name=member.name)


async def _handle_report_bug(
    db: Session,
    member: FamilyMember,
    message_text: str,
    dispatcher: ModelDispatcher,
    media_file_path: str | None,
    intent: str,
) -> str:
    """Create a bug report from the message."""
    text = message_text.strip()
    for prefix in ("באג:", "bug:", "באג", "bug"):
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
            break
    description = text or message_text.strip()

    bug = BugReport(reported_by=member.id, description=description)
    db.add(bug)
    db.flush()
    return PERSONALITY_TEMPLATES["bug_reported"].format(description=description)


async def _handle_list_bugs(
    db: Session,
    member: FamilyMember,
    message_text: str,
    dispatcher: ModelDispatcher,
    media_file_path: str | None,
    intent: str,
) -> str:
    """Return a formatted list of open bug reports."""
    bugs = (
        db.query(BugReport)
        .filter(BugReport.status == "open")
        .order_by(BugReport.created_at.desc())
        .all()
    )
    return format_bug_list(bugs)


# ---------------------------------------------------------------------------
# Task 8.9: Handler dispatch table with update_task and cancel_action
# ---------------------------------------------------------------------------

_ACTION_HANDLERS: dict = {
    "list_tasks": _handle_list_tasks,
    "create_task": _handle_create_task,
    "complete_task": _handle_complete_task,
    "greeting": _handle_greeting,
    "upload_document": _handle_upload_document,
    "list_documents": _handle_list_documents,
    "ask_question": _handle_ask_question,
    "unknown": _handle_unknown,
    "list_recurring": _handle_list_recurring,
    "create_recurring": _handle_create_recurring,
    "delete_recurring": _handle_delete_recurring,
    "report_bug": _handle_report_bug,
    "list_bugs": _handle_list_bugs,
}


# ---------------------------------------------------------------------------
# Task 8.5: verification_node
# ---------------------------------------------------------------------------


async def verification_node(state: WorkflowState) -> dict:
    """Verify that the action actually persisted in the database."""
    intent = state.get("intent", "")
    db = state["db"]

    if intent == "create_task":
        created_id = state.get("created_task_id")
        if created_id:
            task = get_task(db, created_id)
            if not task:
                return {"response": PERSONALITY_TEMPLATES["verification_failed"]}

    elif intent == "delete_task":
        deleted_id = state.get("deleted_task_id")
        if deleted_id:
            task = get_task(db, deleted_id)
            if not task or task.status != "archived":
                return {"response": PERSONALITY_TEMPLATES["verification_failed"]}

    elif intent == "create_recurring":
        recurring_id = state.get("created_recurring_id")
        if recurring_id:
            pattern = (
                db.query(RecurringPattern)
                .filter(RecurringPattern.id == recurring_id)
                .first()
            )
            if not pattern:
                return {"response": PERSONALITY_TEMPLATES["verification_failed"]}

    return {}


# ---------------------------------------------------------------------------
# Task 8.6: update_state_node
# ---------------------------------------------------------------------------


async def update_state_node(state: WorkflowState) -> dict:
    """Update conversation state based on the action that was just performed."""
    intent = state.get("intent", "")
    member = state["member"]
    db = state["db"]

    try:
        if intent == "create_task":
            update_state(
                db, member.id,
                intent="create_task",
                entity_type="task",
                entity_id=state.get("created_task_id"),
                action="created",
            )
        elif intent == "delete_task":
            update_state(
                db, member.id,
                intent="delete_task",
                entity_type="task",
                entity_id=state.get("deleted_task_id"),
                action="deleted",
            )
        elif intent == "list_tasks":
            listed = state.get("listed_tasks", [])
            task_ids = [str(t.id) for t in listed]
            update_state(
                db, member.id,
                intent="list_tasks",
                action="listed",
                context={"task_ids": task_ids},
            )
        elif intent == "cancel_action":
            clear_state(db, member.id)
        elif intent == "update_task":
            update_state(
                db, member.id,
                intent="update_task",
                entity_type="task",
                action="updated",
            )
        elif intent == "create_recurring":
            update_state(
                db, member.id,
                intent="create_recurring",
                entity_type="recurring",
                entity_id=state.get("created_recurring_id"),
                action="created",
            )
    except Exception:
        logger.exception("update_state_node failed (best-effort)")

    return {}


# ---------------------------------------------------------------------------
# Remaining nodes
# ---------------------------------------------------------------------------


def _safe_node_return(result: dict, node_name: str) -> dict:
    """Strip 'response' key from node return dicts to prevent state overwrites."""
    if "response" in result:
        logger.warning("%s: stripped 'response' key from return dict to protect state", node_name)
        result.pop("response")
    return result


async def response_node(state: WorkflowState) -> dict:
    """Pass through — response is already set by action_node or permission_node."""
    return {}


async def memory_save_node(state: WorkflowState) -> dict:
    """Extract and save memories from the conversation exchange. Never affects response."""
    # Skip memory extraction for simple intents like greeting
    if state.get("intent") == "greeting":
        return {}
    try:
        bedrock = BedrockClient()
        await extract_memories_from_message(
            state["db"],
            state["member"].id,
            state["message_text"],
            state["response"],
            bedrock,
        )
    except Exception:
        logger.exception("memory_save_node failed")
        try:
            state["db"].rollback()
            logger.info("Session rolled back after memory save failure")
        except Exception:
            logger.exception("memory_save_node: rollback also failed")
    # NEVER return a "response" key — protect LLM response in state
    return {}


async def conversation_save_node(state: WorkflowState) -> dict:
    """Save the conversation record to the database. Never affects response."""
    try:
        conv = Conversation(
            family_member_id=state["member"].id,
            message_in=state["message_text"],
            message_out=state["response"],
            intent=state["intent"],
        )
        state["db"].add(conv)
        state["db"].commit()
    except Exception:
        logger.exception("conversation_save_node failed")
        try:
            state["db"].rollback()
            logger.info("Session rolled back after conversation save failure")
        except Exception:
            logger.exception("conversation_save_node: rollback also failed")
    # NEVER return a "response" key — protect LLM response in state
    return {}


# ---------------------------------------------------------------------------
# Task 8.10: Graph construction — rebuilt with all new nodes
# ---------------------------------------------------------------------------


def _confirmation_router(state: WorkflowState) -> str:
    """Conditional edge after confirmation_check_node.

    - If response is set (confirmation handled) → response_node
    - Otherwise → intent_node (no pending or cleared)
    """
    if state.get("response"):
        return "response_node"
    return "intent_node"


def _intent_router(state: WorkflowState) -> str:
    """Conditional edge: needs_llm → unified_llm_node, cancel_action → cancel_action_node, otherwise → permission_node."""
    intent = state.get("intent", "")
    if intent == "needs_llm":
        return "unified_llm_node"
    if intent == "cancel_action":
        return "cancel_action_node"
    return "permission_node"


def _permission_router(state: WorkflowState) -> str:
    """Conditional edge after permission_node.

    - denied → response_node
    - granted + delete_task → delete_task_node
    - granted + update_task → update_task_node
    - granted + from_unified + task_data → task_create_node
    - granted + from_unified (no task_data) → response_node (skip action_node)
    - granted + keyword origin → memory_load_node (existing behavior)
    """
    if not state.get("permission_granted", False):
        return "response_node"

    intent = state.get("intent", "")

    if intent == "delete_task":
        return "delete_task_node"

    if intent == "update_task":
        return "update_task_node"

    if state.get("from_unified", False):
        if state.get("task_data"):
            return "task_create_node"
        return "response_node"

    return "memory_load_node"


def _build_graph() -> StateGraph:
    """Build and compile the LangGraph StateGraph."""
    graph = StateGraph(WorkflowState)

    # Add all nodes
    graph.add_node("confirmation_check_node", confirmation_check_node)
    graph.add_node("intent_node", intent_node)
    graph.add_node("permission_node", permission_node)
    graph.add_node("memory_load_node", memory_load_node)
    graph.add_node("action_node", action_node)
    graph.add_node("response_node", response_node)
    graph.add_node("memory_save_node", memory_save_node)
    graph.add_node("conversation_save_node", conversation_save_node)
    graph.add_node("unified_llm_node", unified_llm_node)
    graph.add_node("task_create_node", task_create_node)
    graph.add_node("delete_task_node", delete_task_node)
    graph.add_node("cancel_action_node", cancel_action_node)
    graph.add_node("update_task_node", update_task_node)
    graph.add_node("verification_node", verification_node)
    graph.add_node("update_state_node", update_state_node)

    # Set entry point — confirmation_check_node runs first
    graph.set_entry_point("confirmation_check_node")

    # Confirmation check → intent_node or response_node
    graph.add_conditional_edges(
        "confirmation_check_node",
        _confirmation_router,
        {
            "intent_node": "intent_node",
            "response_node": "response_node",
        },
    )

    # Intent routing
    graph.add_conditional_edges(
        "intent_node",
        _intent_router,
        {
            "unified_llm_node": "unified_llm_node",
            "permission_node": "permission_node",
            "cancel_action_node": "cancel_action_node",
        },
    )
    graph.add_edge("unified_llm_node", "permission_node")

    # Permission routing
    graph.add_conditional_edges(
        "permission_node",
        _permission_router,
        {
            "memory_load_node": "memory_load_node",
            "response_node": "response_node",
            "task_create_node": "task_create_node",
            "delete_task_node": "delete_task_node",
            "update_task_node": "update_task_node",
        },
    )

    # Action paths → verification → response
    graph.add_edge("memory_load_node", "action_node")
    graph.add_edge("action_node", "verification_node")
    graph.add_edge("task_create_node", "verification_node")
    graph.add_edge("delete_task_node", "response_node")
    graph.add_edge("update_task_node", "verification_node")
    graph.add_edge("cancel_action_node", "response_node")
    graph.add_edge("verification_node", "response_node")

    # Response → memory_save → conversation_save → update_state → END
    graph.add_edge("response_node", "memory_save_node")
    graph.add_edge("memory_save_node", "conversation_save_node")
    graph.add_edge("conversation_save_node", "update_state_node")
    graph.add_edge("update_state_node", END)

    return graph


# Compile the graph once at module level
_compiled_graph = _build_graph().compile()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def run_workflow(
    db: Session,
    member: FamilyMember,
    phone: str,
    message_text: str,
    has_media: bool = False,
    media_file_path: str | None = None,
) -> str:
    """Run the LangGraph workflow and return the response string.

    Catches all exceptions and returns personality error_fallback on any error.
    """
    try:
        initial_state: WorkflowState = {
            "db": db,
            "member": member,
            "phone": phone,
            "message_text": message_text,
            "has_media": has_media,
            "media_file_path": media_file_path,
            "intent": "",
            "permission_granted": False,
            "memories": [],
            "response": "",
            "error": None,
            "task_data": None,
            "from_unified": False,
            "delete_target": None,
            # New Sprint 1 fields
            "conv_state": None,
            "time_context": "",
            "state_context": "",
            "created_task_id": None,
            "deleted_task_id": None,
            "listed_tasks": [],
            "created_recurring_id": None,
        }
        result = await _compiled_graph.ainvoke(initial_state)
        return result["response"]
    except Exception:
        logger.exception("Workflow failed")
        return PERSONALITY_TEMPLATES["error_fallback"]
