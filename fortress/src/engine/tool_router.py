"""Fortress Agent — Tool Router.

Pure keyword/regex classifier that selects 5–8 relevant tools per intent group
before any Bedrock call. No I/O, no async, no LLM calls.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from src.engine.tool_registry import get_tool_schemas

logger = logging.getLogger(__name__)

ToolSchema = dict[str, Any]

# ---------------------------------------------------------------------------
# Intent patterns — priority order matters (first match wins)
# ---------------------------------------------------------------------------

_INTENT_PRIORITY = [
    "documents", "tasks", "recipes", "memory", "recurring", "bugs", "dev", "system",
]

_INTENT_PATTERNS: dict[str, list[str]] = {
    "documents": [
        r"סכום|חשבונית|מסמך|קובץ|תשלום|ביטוח|חוזה|קבלה|ספק",
        r"מה כתוב|מה רואים|מה המספר|כמה שילמ",
        r"document|invoice|receipt|contract",
    ],
    "tasks": [r"משימה|לעשות|צור משימה|הוסף משימה|סמן|מחק משימה|task"],
    "recipes": [r"מתכון|בישול|מרכיב|להכין|recipe"],
    "memory": [r"זכור|זיכרון|שמור לזכרון|memory"],
    "recurring": [r"חוזר|כל שבוע|כל חודש|תזכורת קבועה|recurring"],
    "bugs": [r"תקלה|באג|שגיאה|לא עובד|bug"],
    "system": [r"עזרה|פקודות|מה אתה יכול|help|בטל|cancel"],
    "dev": [
        r"תנתח את הקוד|אנדקס|מבנה הקוד|codebase|dev index|dev query|dev plan",
        r"תכנן פיצ׳ר|plan feature|תכנן תכונה|gap analysis",
        r"מה ה.?skills|איזה skills|what skills|מה ה.?services|איזה services",
        r"מה יש לך ב.?skills|הראה לי את המבנה|ארכיטקטורה",
    ],
}

# ---------------------------------------------------------------------------
# Intent → tool name mappings (5–8 tools per group)
# ---------------------------------------------------------------------------

_INTENT_TOOLS: dict[str, list[str]] = {
    "documents": [
        "document_query", "document_search", "document_list",
        "document_fetch", "document_recent", "document_tag_search", "save_text",
    ],
    "tasks": [
        "task_create", "task_list", "task_complete",
        "task_delete", "task_update", "system_cancel",
    ],
    "recipes": [
        "document_recipe_list", "document_recipe_search",
        "document_recipe_howto", "save_text", "document_search",
    ],
    "memory": [
        "memory_list", "save_text", "document_search",
        "system_help", "task_list",
    ],
    "recurring": [
        "recurring_create", "recurring_list", "recurring_delete",
        "system_cancel", "task_list",
    ],
    "bugs": [
        "bug_report", "bug_list", "system_help",
        "task_create", "document_search",
    ],
    "system": [
        "system_help", "system_cancel", "task_list",
        "document_list", "memory_list",
    ],
    "dev": [
        "dev_index", "dev_query", "dev_plan", "system_help",
    ],
    "chat": [
        "document_query", "task_list", "system_help",
        "save_text", "memory_list",
    ],
}

# Max tools to return
_MAX_TOOLS = 8


def _resolve_tool_schemas(tool_names: list[str]) -> list[ToolSchema]:
    """Filter full tool schemas by name, preserving order of tool_names."""
    all_schemas = get_tool_schemas()
    schema_by_name: dict[str, ToolSchema] = {
        s["toolSpec"]["name"]: s for s in all_schemas
    }
    return [schema_by_name[name] for name in tool_names if name in schema_by_name]


def classify(
    message_text: str,
    last_entity_type: str | None = None,
) -> tuple[str, list[ToolSchema]]:
    """Classify message intent and return relevant tool schemas.

    Returns:
        (intent_group, tools) where len(tools) is between 5 and 8.
    """
    text_lower = message_text.lower() if message_text else ""

    # Check patterns in priority order
    for group in _INTENT_PRIORITY:
        patterns = _INTENT_PATTERNS[group]
        for pattern in patterns:
            if re.search(pattern, text_lower):
                tool_names = _INTENT_TOOLS[group][:_MAX_TOOLS]
                return group, _resolve_tool_schemas(tool_names)

    # Context boost: if last entity was a document and no keyword matched
    if last_entity_type == "document":
        tool_names = _INTENT_TOOLS["documents"][:_MAX_TOOLS]
        return "documents", _resolve_tool_schemas(tool_names)

    # Default: chat group
    tool_names = _INTENT_TOOLS["chat"][:_MAX_TOOLS]
    return "chat", _resolve_tool_schemas(tool_names)
