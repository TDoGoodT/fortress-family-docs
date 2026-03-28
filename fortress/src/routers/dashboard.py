from __future__ import annotations
"""Fortress 2.0 dashboard router — admin monitoring endpoint."""

import logging
import time
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.config import OPENROUTER_API_KEY, WAHA_API_KEY, WAHA_API_URL
from src.database import get_db, test_connection
from src.models.schema import BugReport, Conversation, FamilyMember, Task
from src.services.bedrock_client import BedrockClient
from src.services.llm_client import OllamaClient
from src.services.openrouter_client import OpenRouterClient

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dashboard"])

HEBREW_FALLBACK = "מצטער, לא הצלחתי לעבד את הבקשה. נסה שוב."


async def check_waha_health() -> str:
    """Check WAHA connectivity. Returns Health_Status string."""
    headers = {}
    if WAHA_API_KEY:
        headers["X-Api-Key"] = WAHA_API_KEY
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{WAHA_API_URL}/api/sessions",
                headers=headers,
            )
            if resp.status_code == 200:
                return "connected"
            return "disconnected"
    except Exception:
        return "disconnected"


@router.get("/dashboard")
async def dashboard_page():
    """Serve the dashboard HTML page."""
    return FileResponse("src/static/dashboard.html")


@router.get("/dashboard/data")
async def dashboard_data(db: Session = Depends(get_db)) -> dict:
    """Return all dashboard data as JSON."""
    # Lazy import to avoid circular imports
    from src.main import APP_START_TIME

    # --- Health checks ---
    db_ok = test_connection()

    llm = OllamaClient()
    ollama_ok, ollama_model_name = await llm.is_available()

    bedrock = BedrockClient()
    bedrock_ok, bedrock_model = await bedrock.is_available()

    if not OPENROUTER_API_KEY:
        openrouter_status = "no_key"
        openrouter_model = "not configured"
    else:
        openrouter = OpenRouterClient()
        or_ok, or_model = await openrouter.is_available()
        openrouter_status = "connected" if or_ok else "disconnected"
        openrouter_model = or_model or "not available"

    waha_status = await check_waha_health()

    # --- Today's counts ---
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    conversations_today = (
        db.query(func.count(Conversation.id))
        .filter(Conversation.created_at >= today_start)
        .scalar()
    )
    tasks_today = (
        db.query(func.count(Task.id))
        .filter(Task.created_at >= today_start)
        .scalar()
    )
    bugs_today = (
        db.query(func.count(BugReport.id))
        .filter(BugReport.created_at >= today_start)
        .scalar()
    )
    errors_today = (
        db.query(func.count(Conversation.id))
        .filter(
            Conversation.message_out.contains(HEBREW_FALLBACK),
            Conversation.created_at >= today_start,
        )
        .scalar()
    )

    # --- Open items ---
    open_tasks = (
        db.query(func.count(Task.id))
        .filter(Task.status == "open")
        .scalar()
    )
    open_bugs_count = (
        db.query(func.count(BugReport.id))
        .filter(BugReport.status == "open")
        .scalar()
    )

    # --- Recent conversations (last 20) ---
    recent_rows = (
        db.query(Conversation, FamilyMember.name)
        .outerjoin(FamilyMember, Conversation.family_member_id == FamilyMember.id)
        .order_by(Conversation.created_at.desc())
        .limit(20)
        .all()
    )
    recent_conversations = [
        {
            "id": str(conv.id),
            "member_name": member_name,
            "message_in": conv.message_in,
            "message_out": conv.message_out,
            "intent": conv.intent,
            "created_at": conv.created_at.isoformat() if conv.created_at else None,
        }
        for conv, member_name in recent_rows
    ]

    # --- Open bugs ---
    open_bug_rows = (
        db.query(BugReport, FamilyMember.name)
        .outerjoin(FamilyMember, BugReport.reported_by == FamilyMember.id)
        .filter(BugReport.status == "open")
        .order_by(BugReport.created_at.desc())
        .all()
    )
    open_bugs_list = [
        {
            "id": str(bug.id),
            "description": bug.description,
            "priority": bug.priority,
            "status": bug.status,
            "created_at": bug.created_at.isoformat() if bug.created_at else None,
            "reporter_name": reporter_name,
        }
        for bug, reporter_name in open_bug_rows
    ]

    # --- Family members (active only) ---
    active_members = (
        db.query(FamilyMember)
        .filter(FamilyMember.is_active == True)
        .all()
    )
    family_members = [
        {
            "id": str(m.id),
            "name": m.name,
            "role": m.role,
            "phone": m.phone,
            "is_active": m.is_active,
        }
        for m in active_members
    ]

    # --- System info ---
    uptime_seconds = int(time.time() - APP_START_TIME)
    app_start_time_iso = datetime.fromtimestamp(APP_START_TIME).isoformat()

    return {
        "health": {
            "database": "connected" if db_ok else "disconnected",
            "ollama": "connected" if ollama_ok else "disconnected",
            "ollama_model": ollama_model_name if ollama_model_name else "not loaded",
            "bedrock": "connected" if bedrock_ok else "disconnected",
            "bedrock_model": bedrock_model if bedrock_model else "not available",
            "openrouter": openrouter_status,
            "openrouter_model": openrouter_model,
            "waha": waha_status,
        },
        "today": {
            "conversations": conversations_today,
            "tasks_created": tasks_today,
            "bugs_reported": bugs_today,
            "errors": errors_today,
        },
        "open_items": {
            "open_tasks": open_tasks,
            "open_bugs": open_bugs_count,
        },
        "recent_conversations": recent_conversations,
        "open_bugs": open_bugs_list,
        "family_members": family_members,
        "system": {
            "version": "2.0.0",
            "uptime_seconds": uptime_seconds,
            "app_start_time": app_start_time_iso,
        },
    }
