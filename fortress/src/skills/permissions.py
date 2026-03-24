"""Fortress Skills Engine — shared permission check helper."""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.models.schema import FamilyMember
from src.prompts.personality import TEMPLATES
from src.services.auth import check_permission
from src.skills.base_skill import Result


def check_perm(
    db: Session, member: FamilyMember, resource: str, action: str
) -> Result | None:
    """Return a denial Result if the member lacks permission, else None."""
    if not check_permission(db, member.phone, resource, action):
        return Result(success=False, message=TEMPLATES["permission_denied"])
    return None
