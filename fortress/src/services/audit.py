from __future__ import annotations
"""Fortress 2.0 audit service — append-only action logging."""

from uuid import UUID

from sqlalchemy.orm import Session

from src.models.schema import AuditLog


def log_action(
    db: Session,
    actor_id: UUID,
    action: str,
    resource_type: str | None = None,
    resource_id: UUID | None = None,
    details: dict | None = None,
) -> None:
    """Insert a row into the audit_log table and commit."""
    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details or {},
    )
    db.add(entry)
    db.commit()
