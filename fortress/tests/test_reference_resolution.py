"""Unit tests for the resolve_reference helper in the workflow engine."""

from unittest.mock import MagicMock
from uuid import uuid4

from src.services.workflow_engine import resolve_reference


def _make_conv_state(
    last_entity_id=None,
    context=None,
):
    """Build a mock ConversationState."""
    cs = MagicMock()
    cs.last_entity_id = last_entity_id
    cs.context = context or {}
    return cs


# ── Pronoun resolution: "אותה" ───────────────────────────────────


def test_pronoun_resolves_to_last_entity_id() -> None:
    """'אותה' should resolve to last_entity_id from conv_state."""
    entity_id = uuid4()
    conv_state = _make_conv_state(last_entity_id=entity_id)
    db = MagicMock()

    result = resolve_reference(db, uuid4(), "מחק אותה", conv_state)

    assert result == entity_id


def test_pronoun_oto_resolves() -> None:
    """'אותו' should also resolve to last_entity_id."""
    entity_id = uuid4()
    conv_state = _make_conv_state(last_entity_id=entity_id)
    db = MagicMock()

    result = resolve_reference(db, uuid4(), "עדכן אותו", conv_state)

    assert result == entity_id


# ── Index resolution: "משימה 3" ──────────────────────────────────


def test_task_index_resolves() -> None:
    """'משימה 3' should resolve to the 3rd task in context task_ids."""
    task_ids = [str(uuid4()), str(uuid4()), str(uuid4())]
    conv_state = _make_conv_state(context={"task_ids": task_ids})
    db = MagicMock()

    result = resolve_reference(db, uuid4(), "משימה 3", conv_state)

    from uuid import UUID
    assert result == UUID(task_ids[2])


def test_task_index_insufficient_returns_none() -> None:
    """'משימה 3' with only 2 task_ids should return None."""
    task_ids = [str(uuid4()), str(uuid4())]
    conv_state = _make_conv_state(context={"task_ids": task_ids})
    db = MagicMock()

    result = resolve_reference(db, uuid4(), "משימה 3", conv_state)

    assert result is None


# ── Name resolution ──────────────────────────────────────────────


def test_person_name_resolves_to_family_member() -> None:
    """A person name should resolve to the matching family member ID."""
    member_id = uuid4()
    mock_member = MagicMock()
    mock_member.id = member_id

    db = MagicMock()
    mock_query = MagicMock()
    db.query.return_value = mock_query
    mock_query.filter.return_value = mock_query
    mock_query.all.return_value = [mock_member]

    conv_state = _make_conv_state()

    result = resolve_reference(db, uuid4(), "שגב", conv_state)

    assert result == member_id


def test_ambiguous_name_returns_none() -> None:
    """Multiple name matches should return None (ambiguous)."""
    member1 = MagicMock()
    member1.id = uuid4()
    member2 = MagicMock()
    member2.id = uuid4()

    db = MagicMock()
    mock_query = MagicMock()
    db.query.return_value = mock_query
    mock_query.filter.return_value = mock_query
    mock_query.all.return_value = [member1, member2]

    conv_state = _make_conv_state()

    result = resolve_reference(db, uuid4(), "שגב", conv_state)

    assert result is None


# ── No reference found ───────────────────────────────────────────


def test_no_reference_returns_none() -> None:
    """No matching reference should return None."""
    db = MagicMock()
    mock_query = MagicMock()
    db.query.return_value = mock_query
    mock_query.filter.return_value = mock_query
    mock_query.all.return_value = []

    conv_state = _make_conv_state()

    result = resolve_reference(db, uuid4(), "x", conv_state)

    assert result is None


def test_none_conv_state_returns_none() -> None:
    """None conv_state should return None."""
    db = MagicMock()
    result = resolve_reference(db, uuid4(), "אותה", None)
    assert result is None
