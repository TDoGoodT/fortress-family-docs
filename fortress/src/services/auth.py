"""Fortress 2.0 auth service — phone-based lookup and permission checks."""

from sqlalchemy.orm import Session

from src.models.schema import FamilyMember, Permission
from src.utils.phone import phone_lookup_candidates


def get_family_member_by_phone(db: Session, phone: str) -> FamilyMember | None:
    """Return the family member matching *phone*, or None."""
    candidates = phone_lookup_candidates(phone)
    if not candidates:
        return None
    return db.query(FamilyMember).filter(FamilyMember.phone.in_(candidates)).first()


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
