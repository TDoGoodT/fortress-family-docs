from unittest.mock import MagicMock

from src.services.fact_policy import can_read_category


def _member(role: str):
    m = MagicMock()
    m.role = role
    return m


def test_basic_categories_allowed_for_all_identified_users() -> None:
    child = _member("child")
    assert can_read_category(child, "basic_personal") is True
    assert can_read_category(child, "household_access") is True


def test_future_sensitive_categories_parent_only() -> None:
    parent = _member("parent")
    child = _member("child")

    assert can_read_category(parent, "financial") is True
    assert can_read_category(parent, "health") is True
    assert can_read_category(child, "financial") is False
    assert can_read_category(child, "health") is False
