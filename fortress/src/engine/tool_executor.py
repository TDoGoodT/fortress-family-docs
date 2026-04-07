"""Fortress Agent — tool executor.

Maps LLM tool calls to existing skill handlers via executor.execute().
All permissions, verification, state updates, and audit logging are preserved.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from src.engine.executor import execute
from src.engine.tool_registry import get_tool_map
from src.models.schema import FamilyMember
from src.skills.base_skill import Command

logger = logging.getLogger(__name__)


def execute_tool(
    db: Session,
    member: FamilyMember,
    tool_name: str,
    tool_args: dict,
    original_message: str = "",
) -> str:
    """Execute a tool call and return a result string for the LLM.

    Maps tool_name to (skill, action), builds a Command, dispatches
    through executor.execute(), and converts the Result to a string.
    Returns an error string if tool_name is unknown.
    """
    tool_map = get_tool_map()
    if tool_name not in tool_map:
        logger.warning("tool_executor: unknown tool=%s", tool_name)
        return f"כלי לא מוכר: {tool_name}"

    # Special-case: bedrock_cost bypasses skill dispatch
    if tool_name == "bedrock_cost":
        from src.services.cost_tool import query_bedrock_cost
        try:
            return query_bedrock_cost()
        except Exception as exc:
            logger.error("tool_executor: bedrock_cost failed error=%s", exc)
            return "שגיאה בשליפת נתוני עלויות"

    skill_name, action_name = tool_map[tool_name]

    # Build params from tool args, inject audit metadata
    params = dict(tool_args)
    params["_original_message"] = original_message
    params["_pii_stripped"] = False

    # raw_text helps skills that use it for fallback parsing
    if "question" in params:
        params["raw_text"] = params["question"]
    elif "feature_request" in params:
        params["raw_text"] = params["feature_request"]
    elif original_message:
        params["raw_text"] = original_message

    command = Command(
        skill=skill_name,
        action=action_name,
        params=params,
        raw_text=original_message,
    )

    logger.info(
        "tool_executor: dispatching tool=%s skill=%s action=%s member=%s",
        tool_name, skill_name, action_name, member.name,
    )

    try:
        result = execute(db, member, command)
        return result.message or "הפעולה הושלמה"
    except Exception as exc:
        logger.error(
            "tool_executor: execution failed tool=%s error=%s: %s",
            tool_name, type(exc).__name__, exc,
        )
        return f"שגיאה בביצוע הפעולה: {type(exc).__name__}"
