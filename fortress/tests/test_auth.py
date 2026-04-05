"""Unit tests for the auth service (phone lookup and permission checks)."""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.models.schema import FamilyMember, Permission
from src.services.auth import check_permission, get_family_member_by_phone


def test_get_family_member_by_phone_found(
    mock_db: MagicMock,
    sample_family_member: FamilyMember,
) -> None:
    """Known phone should return the matching FamilyMember."""
    mock_db.query.return_value.filter.return_value.all.return_value = [
        sample_family_member
    ]
    result = get_family_member_by_phone(mock_db, sample_family_member.phone)
    assert result is sample_family_member


def test_get_family_member_by_phone_not_found(mock_db: MagicMock) -> None:
    """Unknown phone should return None."""
    mock_db.query.return_value.filter.return_value.all.return_value = []
    result = get_family_member_by_phone(mock_db, "+000000000")
    assert result is None


def test_get_family_member_by_phone_matches_local_record_from_lid_sender(mock_db: MagicMock) -> None:
    """LID sender should resolve to the same member even if DB stores local 05X format."""
    member = MagicMock(spec=FamilyMember)
    member.id = uuid.uuid4()
    member.name = "Chen"
    member.phone = "0541234567"
    member.created_at = datetime(2026, 4, 1, tzinfo=timezone.utc)
    mock_db.query.return_value.filter.return_value.all.return_value = [member]

    result = get_family_member_by_phone(mock_db, "972541234567@lid")

    assert result is member


def test_get_family_member_by_phone_prefers_stable_oldest_duplicate(mock_db: MagicMock) -> None:
    """If both 05X and 972 rows exist for one canonical phone, pick a stable row."""
    older = MagicMock(spec=FamilyMember)
    older.id = uuid.uuid4()
    older.name = "Segev"
    older.phone = "0501234567"
    older.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    newer = MagicMock(spec=FamilyMember)
    newer.id = uuid.uuid4()
    newer.name = "Segev Duplicate"
    newer.phone = "972501234567"
    newer.created_at = datetime(2026, 2, 1, tzinfo=timezone.utc)

    mock_db.query.return_value.filter.return_value.all.return_value = [newer, older]

    result = get_family_member_by_phone(mock_db, "972501234567@c.us")

    assert result is older


def _setup_check_permission(mock_db, member, permission):
    """Wire mock_db for check_permission calls."""
    query_obj = mock_db.query.return_value
    filter_obj = query_obj.filter.return_value
    filter_obj.all.return_value = [member] if member is not None else []
    filter_obj.first.return_value = permission


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
