"""Fortress Skills Engine — executor: dispatch → verify → state → audit."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from src.models.schema import FamilyMember
from src.prompts.personality import TEMPLATES as PERSONALITY_TEMPLATES
from src.services.audit import log_action
from src.services.conversation_state import (
    clear_state,
    resolve_pending,
    update_state,
)
from src.skills.base_skill import Command, Result
from src.skills.registry import registry

logger = logging.getLogger(__name__)


def execute(db: Session, member: FamilyMember, command: Command) -> Result:
    """Execute a parsed command through the skill pipeline."""
    try:
        # 1. Look up skill
        skill = registry.get(command.skill)
        if skill is None:
            return Result(
                success=False,
                message=PERSONALITY_TEMPLATES["error_fallback"],
            )

        # 2. Handle confirmation re-dispatch
        if command.action == "confirm":
            return _handle_confirm(db, member, skill, command)

        # 3. Execute
        result = skill.execute(db, member, command)

        # 4. Cancel → clear state
        if command.action == "cancel":
            clear_state(db, member.id)
            return result

        # 5. Verify (if successful with entity_id)
        if result.success and result.entity_id is not None:
            verified = skill.verify(db, result)
            if not verified:
                return Result(
                    success=False,
                    message=PERSONALITY_TEMPLATES["verification_failed"],
                    entity_type=result.entity_type,
                    entity_id=result.entity_id,
                    action=result.action,
                )

        # 6. Update state
        if result.success:
            update_state(
                db,
                member.id,
                intent=command.skill,
                entity_type=result.entity_type,
                entity_id=result.entity_id,
                action=result.action,
            )

        # 7. Audit (if entity_id)
        if result.success and result.entity_id is not None:
            log_action(
                db,
                actor_id=member.id,
                action=result.action or command.action,
                resource_type=result.entity_type,
                resource_id=result.entity_id,
            )

        return result

    except Exception:
        logger.exception(
            "Executor error: skill=%s action=%s member=%s",
            command.skill,
            command.action,
            member.name,
        )
        db.rollback()
        return Result(
            success=False,
            message=PERSONALITY_TEMPLATES["error_fallback"],
        )


def _handle_confirm(
    db: Session, member: FamilyMember, skill, command: Command
) -> Result:
    """Handle confirmation by resolving pending action and re-dispatching."""
    pending = resolve_pending(db, member.id)
    if pending is None:
        return Result(success=False, message="אין פעולה ממתינה לאישור 🤷")

    # Re-dispatch the pending action through the appropriate skill
    pending_type = pending.get("type", "")
    pending_data = pending.get("data", {})

    # Find the target skill from the pending action type
    parts = pending_type.split(".", 1)
    target_skill_name = parts[0] if parts else pending_type
    target_action = parts[1] if len(parts) > 1 else pending_type

    target_skill = registry.get(target_skill_name)
    if target_skill is None:
        return Result(
            success=False,
            message=PERSONALITY_TEMPLATES["error_fallback"],
        )

    redispatch = Command(
        skill=target_skill_name,
        action=target_action,
        params=pending_data,
    )
    return execute(db, member, redispatch)
