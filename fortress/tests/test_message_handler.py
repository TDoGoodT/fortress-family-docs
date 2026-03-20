"""Unit tests for the message handler service."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.schema import FamilyMember
from src.services.message_handler import handle_incoming_message


def _make_member(
    *,
    phone: str = "972501234567",
    is_active: bool = True,
) -> MagicMock:
    m = MagicMock(spec=FamilyMember)
    m.id = uuid.uuid4()
    m.name = "Test User"
    m.phone = phone
    m.role = "parent"
    m.is_active = is_active
    return m


# ── Auth layer tests ─────────────────────────────────────────────


@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.get_family_member_by_phone", return_value=None)
async def test_unknown_phone_rejected(mock_auth, mock_conv, mock_db) -> None:
    """Unknown phone number should return rejection message."""
    result = await handle_incoming_message(mock_db, "000000000", "hello", "msg1")
    assert "מספר לא מזוהה" in result


@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_inactive_member(mock_auth, mock_conv, mock_db) -> None:
    """Inactive member should return inactive message."""
    mock_auth.return_value = _make_member(is_active=False)
    result = await handle_incoming_message(mock_db, "972501234567", "hello", "msg1")
    assert "לא פעיל" in result


@pytest.mark.asyncio
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_conversation_saved(mock_auth, mock_db) -> None:
    """Every interaction should save a conversation record."""
    mock_auth.return_value = None
    await handle_incoming_message(mock_db, "000000000", "hello", "msg1")
    assert mock_db.add.called
    assert mock_db.commit.called


# ── Delegation to workflow engine ─────────────────────────────────


@pytest.mark.asyncio
@patch("src.services.message_handler.run_workflow", new_callable=AsyncMock)
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_active_member_delegates_to_router(mock_auth, mock_route, mock_db) -> None:
    """Active member messages should be delegated to run_workflow."""
    member = _make_member()
    mock_auth.return_value = member
    mock_route.return_value = "router response"
    result = await handle_incoming_message(mock_db, "972501234567", "משימות", "msg1")
    assert result == "router response"
    mock_route.assert_called_once_with(
        mock_db,
        member,
        "972501234567",
        "משימות",
        has_media=False,
        media_file_path=None,
    )


@pytest.mark.asyncio
@patch("src.services.message_handler.run_workflow", new_callable=AsyncMock)
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_media_message_delegates_to_router(mock_auth, mock_route, mock_db) -> None:
    """Media messages should be delegated to run_workflow with has_media=True."""
    member = _make_member()
    mock_auth.return_value = member
    mock_route.return_value = "document saved"
    result = await handle_incoming_message(
        mock_db,
        "972501234567",
        "",
        "msg1",
        has_media=True,
        media_file_path="/data/documents/2026/03/file.pdf",
    )
    assert result == "document saved"
    mock_route.assert_called_once_with(
        mock_db,
        member,
        "972501234567",
        "",
        has_media=True,
        media_file_path="/data/documents/2026/03/file.pdf",
    )


@pytest.mark.asyncio
@patch("src.services.message_handler.run_workflow", new_callable=AsyncMock)
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_router_receives_correct_text(mock_auth, mock_route, mock_db) -> None:
    """Workflow engine should receive the exact message text."""
    member = _make_member()
    mock_auth.return_value = member
    mock_route.return_value = "ok"
    await handle_incoming_message(mock_db, "972501234567", "משימה חדשה: קניות", "msg1")
    call_args = mock_route.call_args
    assert call_args[0][3] == "משימה חדשה: קניות"


@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.get_family_member_by_phone", return_value=None)
async def test_unknown_phone_saves_conversation(mock_auth, mock_conv, mock_db) -> None:
    """Unknown phone should save conversation with unknown_sender intent."""
    await handle_incoming_message(mock_db, "000000000", "hello", "msg1")
    mock_conv.assert_called_once()
    call_args = mock_conv.call_args
    assert call_args[0][4] == "unknown_sender"


@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_inactive_member_saves_conversation(mock_auth, mock_conv, mock_db) -> None:
    """Inactive member should save conversation with inactive_member intent."""
    mock_auth.return_value = _make_member(is_active=False)
    await handle_incoming_message(mock_db, "972501234567", "hello", "msg1")
    mock_conv.assert_called_once()
    call_args = mock_conv.call_args
    assert call_args[0][4] == "inactive_member"
