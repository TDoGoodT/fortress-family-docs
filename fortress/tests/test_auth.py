"""Unit tests for the auth service (phone lookup and permission checks)."""

import uuid
from unittest.mock import MagicMock

from src.models.schema import FamilyMember, Permission
from src.services.auth import check_permission, get_family_member_by_phone


def test_get_family_member_by_phone_found(
    mock_db: MagicMock,
    sample_family_member: FamilyMember,
) -> None:
    """Known phone should return the matching FamilyMember."""
    mock_db.query.return_value.filter.return_value.first.return_value = (
        sample_family_member
    )
    result = get_family_member_by_phone(mock_db, sample_family_member.phone)
    assert result is sample_family_member


def test_get_family_member_by_phone_not_found(mock_db: MagicMock) -> None:
    """Unknown phone should return None."""
    mock_db.query.return_value.filter.return_value.first.return_value = None
    result = get_family_member_by_phone(mock_db, "+000000000")
    assert result is None


def _setup_check_permission(mock_db, member, permission):
    """Wire mock_db for check_permission calls."""
    mock_db.query.return_value.filter.return_value.first.side_effect = [
        member,
        permission,
    ]


def test_check_permission_active_parent_finance_read(
    mock_db: MagicMock,
    sample_family_member: FamilyMember,
    sample_permission: Permission,
) -> None:
    """Active parent with finance read permission should return True."""
    _setup_check_permission(mock_db, sample_family_member, sample_permission)
    assert check_permission(mock_db, sample_family_member.phone, "finance", "read") is True


def test_check_permission_child_finance_read(mock_db: MagicMock) -> None:
    """Child with no finance read permission should return False."""
    child = MagicMock(spec=FamilyMember)
    child.id = uuid.uuid4()
    child.name = "Test Child"
    child.phone = "+972509999999"
    child.role = "child"
    child.is_active = True

    perm = MagicMock(spec=Permission)
    perm.id = uuid.uuid4()
    perm.role = "child"
    perm.resource_type = "finance"
    perm.can_read = False
    perm.can_write = False

    _setup_check_permission(mock_db, child, perm)
    assert check_permission(mock_db, child.phone, "finance", "read") is False


def test_check_permission_inactive_member(mock_db: MagicMock) -> None:
    """Inactive member should return False regardless of permissions."""
    inactive = MagicMock(spec=FamilyMember)
    inactive.id = uuid.uuid4()
    inactive.name = "Inactive"
    inactive.phone = "+972508888888"
    inactive.role = "parent"
    inactive.is_active = False

    _setup_check_permission(mock_db, inactive, None)
    assert check_permission(mock_db, inactive.phone, "finance", "read") is False


def test_check_permission_unknown_phone(mock_db: MagicMock) -> None:
    """Unknown phone, no member found, should return False."""
    _setup_check_permission(mock_db, None, None)
    assert check_permission(mock_db, "+000000000", "finance", "read") is False
