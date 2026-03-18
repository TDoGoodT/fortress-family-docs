"""Shared pytest fixtures for Fortress 2.0 tests."""

import sys
import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

# Inject a fake psycopg2 module so that src.database can import without
# a real PostgreSQL client library installed.
if "psycopg2" not in sys.modules:
    _fake_psycopg2 = MagicMock()
    sys.modules["psycopg2"] = _fake_psycopg2
    sys.modules["psycopg2.extensions"] = _fake_psycopg2.extensions
    sys.modules["psycopg2.extras"] = _fake_psycopg2.extras

from fastapi.testclient import TestClient  # noqa: E402

from src.database import get_db  # noqa: E402
from src.main import app  # noqa: E402
from src.models.schema import FamilyMember, Permission  # noqa: E402


@pytest.fixture()
def mock_db() -> MagicMock:
    """Return a mocked SQLAlchemy Session."""
    return MagicMock(spec=Session)


@pytest.fixture()
def client(mock_db: MagicMock) -> TestClient:
    """FastAPI TestClient with the DB dependency overridden."""
    def _override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _make_family_member(
    *,
    name: str = "Test Parent",
    phone: str = "+972501234567",
    role: str = "parent",
    is_active: bool = True,
) -> MagicMock:
    """Build a mock that quacks like a FamilyMember."""
    m = MagicMock(spec=FamilyMember)
    m.id = uuid.uuid4()
    m.name = name
    m.phone = phone
    m.role = role
    m.is_active = is_active
    return m


def _make_permission(
    *,
    role: str = "parent",
    resource_type: str = "finance",
    can_read: bool = True,
    can_write: bool = True,
) -> MagicMock:
    """Build a mock that quacks like a Permission."""
    p = MagicMock(spec=Permission)
    p.id = uuid.uuid4()
    p.role = role
    p.resource_type = resource_type
    p.can_read = can_read
    p.can_write = can_write
    return p


@pytest.fixture()
def sample_family_member() -> MagicMock:
    """A sample active parent FamilyMember for use in tests."""
    return _make_family_member()


@pytest.fixture()
def sample_permission() -> MagicMock:
    """A sample Permission granting read+write on finance for the parent role."""
    return _make_permission()
