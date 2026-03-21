"""Fortress 2.0 Workflow Engine — LangGraph StateGraph replacing model_router."""

import json
import logging
from typing import TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from src.models.schema import Conversation, FamilyMember, Memory
from src.prompts.system_prompts import (
    FORTRESS_BASE,
    TASK_EXTRACTOR_BEDROCK,
    TASK_RESPONDER,
)
from src.services.audit import log_action
from src.services.auth import check_permission
from src.services.bedrock_client import HEBREW_FALLBACK, BedrockClient
from src.services.documents import process_document
from src.services.intent_detector import detect_intent
from src.services.model_dispatch import ModelDispatcher
from src.services.memory_service import (
    extract_memories_from_message,
    load_memories,
    save_memory,
)
from src.services.unified_handler import handle_with_llm
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
    """Create a task from task_data stored in state."""
    task_data = state.get("task_data") or {}
    title = task_data.get("title", "").strip()
    if title:
        create_task(
            state["db"],
            title,
            state["member"].id,
            assigned_to=state["member"].id,
            due_date=task_data.get("due_date"),
            category=task_data.get("category"),
            priority=task_data.get("priority", "normal"),
        )
        logger.info("task_create_node: created task '%s' for %s", title, state["member"].name)
    return {}


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
            "response": "אין לך הרשאה לביצוע פעולה זו 🔒",
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
    return {"response": response}


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
    """Fetch open tasks and format via dispatcher."""
    tasks = list_tasks(db, status="open", assigned_to=member.id)
    if not tasks:
        prompt = "אין משימות פתוחות. צור תשובה קצרה ושמחה בעברית."
        return await dispatcher.dispatch(prompt=prompt, system_prompt=FORTRESS_BASE, intent=intent)

    task_lines = []
    for i, task in enumerate(tasks, 1):
        due = f" (עד {task.due_date})" if task.due_date else ""
        priority = task.priority if hasattr(task, "priority") else "normal"
        task_lines.append(f"{i}. [{priority}] {task.title}{due}")

    task_data = "\n".join(task_lines)
    prompt = f"הנה רשימת המשימות:\n{task_data}\n\nפרמט את זה יפה לוואטסאפ."
    return await dispatcher.dispatch(prompt=prompt, system_prompt=TASK_RESPONDER, intent=intent)


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

    prompt = f"משימה חדשה נוצרה: {title}. צור אישור קצר בעברית."
    return await dispatcher.dispatch(prompt=prompt, system_prompt=FORTRESS_BASE, intent=intent)


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
    return f"שלום, {member.name}! 👋"


async def _handle_upload_document(
    db: Session,
    member: FamilyMember,
    message_text: str,
    dispatcher: ModelDispatcher,
    media_file_path: str | None,
    intent: str,
) -> str:
    """Save document and acknowledge via dispatcher."""
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
        return await dispatcher.dispatch(prompt=prompt, system_prompt=FORTRESS_BASE, intent=intent)
    except Exception:
        logger.exception("Error processing media from %s", member.phone)
        return "שגיאה בשמירת הקובץ. נסה שוב."


async def _handle_list_documents(
    db: Session,
    member: FamilyMember,
    message_text: str,
    dispatcher: ModelDispatcher,
    media_file_path: str | None,
    intent: str,
) -> str:
    """Return a summary of recent documents via dispatcher."""
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
        return await dispatcher.dispatch(prompt=prompt, system_prompt=FORTRESS_BASE, intent=intent)

    doc_lines = []
    for i, doc in enumerate(docs, 1):
        name = doc.original_filename or doc.file_path.split("/")[-1]
        doc_lines.append(f"{i}. {name}")

    prompt = f"הנה רשימת המסמכים האחרונים:\n" + "\n".join(doc_lines)
    return await dispatcher.dispatch(prompt=prompt, system_prompt=FORTRESS_BASE, intent=intent)


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


async def _handle_unknown(
    db: Session,
    member: FamilyMember,
    message_text: str,
    dispatcher: ModelDispatcher,
    media_file_path: str | None,
    intent: str,
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
_ACTION_HANDLERS: dict = {
    "list_tasks": _handle_list_tasks,
    "create_task": _handle_create_task,
    "complete_task": _handle_complete_task,
    "greeting": _handle_greeting,
    "upload_document": _handle_upload_document,
    "list_documents": _handle_list_documents,
    "ask_question": _handle_ask_question,
    "unknown": _handle_unknown,
}


# ---------------------------------------------------------------------------
# Remaining nodes
# ---------------------------------------------------------------------------


async def response_node(state: WorkflowState) -> dict:
    """Pass through — response is already set by action_node or permission_node."""
    return {}


async def memory_save_node(state: WorkflowState) -> dict:
    """Extract and save memories from the conversation exchange."""
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
    return {}


async def conversation_save_node(state: WorkflowState) -> dict:
    """Save the conversation record to the database."""
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
    return {}


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


def _intent_router(state: WorkflowState) -> str:
    """Conditional edge: needs_llm → unified_llm_node, otherwise → permission_node."""
    if state.get("intent") == "needs_llm":
        return "unified_llm_node"
    return "permission_node"


def _permission_router(state: WorkflowState) -> str:
    """Conditional edge after permission_node.

    - denied → response_node
    - granted + from_unified + task_data → task_create_node
    - granted + from_unified (no task_data) → response_node (skip action_node)
    - granted + keyword origin → memory_load_node (existing behavior)
    """
    if not state.get("permission_granted", False):
        return "response_node"

    if state.get("from_unified", False):
        if state.get("task_data"):
            return "task_create_node"
        return "response_node"

    return "memory_load_node"


def _build_graph() -> StateGraph:
    """Build and compile the LangGraph StateGraph."""
    graph = StateGraph(WorkflowState)

    # Add nodes
    graph.add_node("intent_node", intent_node)
    graph.add_node("permission_node", permission_node)
    graph.add_node("memory_load_node", memory_load_node)
    graph.add_node("action_node", action_node)
    graph.add_node("response_node", response_node)
    graph.add_node("memory_save_node", memory_save_node)
    graph.add_node("conversation_save_node", conversation_save_node)
    graph.add_node("unified_llm_node", unified_llm_node)
    graph.add_node("task_create_node", task_create_node)

    # Set entry point
    graph.set_entry_point("intent_node")

    # Add edges
    graph.add_conditional_edges(
        "intent_node",
        _intent_router,
        {
            "unified_llm_node": "unified_llm_node",
            "permission_node": "permission_node",
        },
    )
    graph.add_edge("unified_llm_node", "permission_node")
    graph.add_conditional_edges(
        "permission_node",
        _permission_router,
        {
            "memory_load_node": "memory_load_node",
            "response_node": "response_node",
            "task_create_node": "task_create_node",
        },
    )
    graph.add_edge("memory_load_node", "action_node")
    graph.add_edge("action_node", "response_node")
    graph.add_edge("task_create_node", "response_node")
    graph.add_edge("response_node", "memory_save_node")
    graph.add_edge("memory_save_node", "conversation_save_node")
    graph.add_edge("conversation_save_node", END)

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

    Catches all exceptions and returns HEBREW_FALLBACK on any error.
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
        }
        result = await _compiled_graph.ainvoke(initial_state)
        return result["response"]
    except Exception:
        logger.exception("Workflow failed")
        return HEBREW_FALLBACK
