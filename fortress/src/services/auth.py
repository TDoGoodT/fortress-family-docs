from __future__ import annotations
"""Fortress 2.0 auth service — phone-based lookup and permission checks."""

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.models.schema import FamilyMember, Permission
from src.utils.phone import canonicalize_phone, phone_lookup_candidates


def get_family_member_by_phone(db: Session, phone: str) -> FamilyMember | None:
    """Return the family member matching *phone*, or None.

    If multiple rows match different phone representations for the same
    canonical number, prefer the oldest row to keep identity resolution stable.
    """
    candidates = phone_lookup_candidates(phone)
    if not candidates:
        return None
    matches = (
        db.query(FamilyMember)
        .filter(FamilyMember.phone.in_(candidates))
        .all()
    )
    if not matches:
        return None

    canonical = canonicalize_phone(phone)
    canonical_matches = [
        member
        for member in matches
        if canonicalize_phone(member.phone) == canonical
    ]
    if canonical_matches:
        matches = canonical_matches

    matches.sort(
        key=lambda member: (
            member.created_at is None,
            member.created_at,
            str(member.id),
        )
    )
    return matches[0]


def get_family_member_by_name(db: Session, name: str) -> FamilyMember | None:
    """Return an active family member matching *name* case-insensitively."""
    cleaned = (name or "").strip()
    if not cleaned:
        return None
    return (
        db.query(FamilyMember)
        .filter(
            func.lower(FamilyMember.name) == cleaned.lower(),
            FamilyMember.is_active == True,
        )
        .first()
    )


def get_permissions_for_role(db: Session, role: str) -> list[Permission]:
    """Return all permission records for the given role."""
    return db.query(Permission).filter(Permission.role == role).all()


def check_permission(
    db: Session,
    phone: str,
    resource_type: str,
    action: str,
) -> bool:
    """Check whether the member identified by *phone* may perform *action* on *resource_type*.

    *action* must be ``"read"`` or ``"write"``.
    Returns ``False`` if the member is not found, not active, or lacks the permission.
    """
    member = get_family_member_by_phone(db, phone)
    if member is None or not member.is_active:
        return False

    permission = (
        db.query(Permission)
        .filter(
            Permission.role == member.role,
            Permission.resource_type == resource_type,
        )
        .first()
    )
    if permission is None:
        return False

    if action == "read":
        return permission.can_read
    if action == "write":
        return permission.can_write

    return False
