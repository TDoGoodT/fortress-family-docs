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


# ── E2E helper fixtures (Sprint R3) ──────────────────────────────

from src.models.schema import (  # noqa: E402
    BugReport,
    ConversationState,
    Document,
    RecurringPattern,
    Task,
)


def _make_task(**overrides) -> MagicMock:
    """Build a mock Task with sensible defaults."""
    t = MagicMock(spec=Task)
    t.id = overrides.get("id", uuid.uuid4())
    t.title = overrides.get("title", "Test Task")
    t.status = overrides.get("status", "open")
    t.priority = overrides.get("priority", "normal")
    t.due_date = overrides.get("due_date", None)
    t.assigned_to = overrides.get("assigned_to", None)
    t.created_by = overrides.get("created_by", None)
    t.created_at = overrides.get("created_at", None)
    return t


def _make_recurring(**overrides) -> MagicMock:
    """Build a mock RecurringPattern with sensible defaults."""
    r = MagicMock(spec=RecurringPattern)
    r.id = overrides.get("id", uuid.uuid4())
    r.title = overrides.get("title", "Test Recurring")
    r.frequency = overrides.get("frequency", "monthly")
    r.next_due_date = overrides.get("next_due_date", None)
    r.is_active = overrides.get("is_active", True)
    return r


def _make_bug(**overrides) -> MagicMock:
    """Build a mock BugReport with sensible defaults."""
    b = MagicMock(spec=BugReport)
    b.id = overrides.get("id", uuid.uuid4())
    b.description = overrides.get("description", "Test Bug")
    b.status = overrides.get("status", "open")
    b.reported_by = overrides.get("reported_by", None)
    b.created_at = overrides.get("created_at", None)
    return b


def _make_document(**overrides) -> MagicMock:
    """Build a mock Document with sensible defaults."""
    d = MagicMock(spec=Document)
    d.id = overrides.get("id", uuid.uuid4())
    d.original_filename = overrides.get("original_filename", "test.pdf")
    d.doc_type = overrides.get("doc_type", "document")
    d.created_at = overrides.get("created_at", None)
    return d


def _make_conversation_state(**overrides) -> MagicMock:
    """Build a mock ConversationState with sensible defaults."""
    s = MagicMock(spec=ConversationState)
    s.family_member_id = overrides.get("family_member_id", uuid.uuid4())
    s.last_intent = overrides.get("last_intent", None)
    s.last_entity_type = overrides.get("last_entity_type", None)
    s.last_entity_id = overrides.get("last_entity_id", None)
    s.last_action = overrides.get("last_action", None)
    s.pending_confirmation = overrides.get("pending_confirmation", False)
    s.pending_action = overrides.get("pending_action", None)
    s.context = overrides.get("context", {})
    return s
