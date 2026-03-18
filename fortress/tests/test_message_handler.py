"""Unit tests for the message handler service."""

import uuid
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from src.models.schema import FamilyMember, Task
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


def _make_task(title: str = "Buy milk", due_date=None) -> MagicMock:
    t = MagicMock(spec=Task)
    t.id = uuid.uuid4()
    t.title = title
    t.due_date = due_date
    t.status = "open"
    return t


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
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.list_tasks")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_list_tasks_keyword(mock_auth, mock_list, mock_conv, mock_db) -> None:
    """Sending 'משימות' should return task list."""
    member = _make_member()
    mock_auth.return_value = member
    mock_list.return_value = [_make_task("Buy milk"), _make_task("Pay rent")]
    result = await handle_incoming_message(mock_db, "972501234567", "משימות", "msg1")
    assert "Buy milk" in result
    assert "Pay rent" in result


@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.create_task")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_create_task_keyword(mock_auth, mock_create, mock_conv, mock_db) -> None:
    """Sending 'משימה חדשה: קניות' should create a task."""
    member = _make_member()
    mock_auth.return_value = member
    mock_create.return_value = _make_task("קניות")
    result = await handle_incoming_message(
        mock_db, "972501234567", "משימה חדשה: קניות", "msg1"
    )
    assert "משימה נוצרה" in result
    assert "קניות" in result
    mock_create.assert_called_once()


@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.process_document", new_callable=AsyncMock)
@patch("src.services.message_handler.log_action")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_media_stores_document(
    mock_auth, mock_log, mock_doc, mock_conv, mock_db
) -> None:
    """Media message should store document and return confirmation."""
    member = _make_member()
    mock_auth.return_value = member
    result = await handle_incoming_message(
        mock_db,
        "972501234567",
        "",
        "msg1",
        has_media=True,
        media_file_path="/data/documents/2026/03/file.pdf",
    )
    assert "קיבלתי את הקובץ" in result
    mock_doc.assert_called_once()


@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_generic_text_acknowledged(mock_auth, mock_conv, mock_db) -> None:
    """Generic text should return acknowledgment."""
    mock_auth.return_value = _make_member()
    result = await handle_incoming_message(
        mock_db, "972501234567", "מה שלומך?", "msg1"
    )
    assert "קיבלתי" in result
    assert "🤖" in result


@pytest.mark.asyncio
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_conversation_saved(mock_auth, mock_db) -> None:
    """Every interaction should save a conversation record."""
    mock_auth.return_value = _make_member()
    await handle_incoming_message(mock_db, "972501234567", "hello", "msg1")
    # Conversation is saved via db.add + db.commit
    assert mock_db.add.called
    assert mock_db.commit.called


# ── Permission check tests (Phase 3.5) ──────────────────────────


def _make_member_with_role(
    role: str,
    phone: str = "972501234567",
) -> MagicMock:
    m = MagicMock(spec=FamilyMember)
    m.id = uuid.uuid4()
    m.name = f"Test {role.title()}"
    m.phone = phone
    m.role = role
    m.is_active = True
    return m


@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.list_tasks")
@patch("src.services.message_handler.check_permission", return_value=True)
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_child_can_read_tasks(
    mock_auth, mock_perm, mock_list, mock_conv, mock_db
) -> None:
    """Child role with tasks read permission can list tasks."""
    member = _make_member_with_role("child")
    mock_auth.return_value = member
    mock_list.return_value = [_make_task("Buy milk")]
    result = await handle_incoming_message(mock_db, member.phone, "משימות", "msg1")
    assert "Buy milk" in result
    assert "🔒" not in result


@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.log_action")
@patch("src.services.message_handler.check_permission", return_value=False)
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_child_cannot_upload_document(
    mock_auth, mock_perm, mock_log, mock_conv, mock_db
) -> None:
    """Child role without documents write permission is denied media upload."""
    member = _make_member_with_role("child")
    mock_auth.return_value = member
    result = await handle_incoming_message(
        mock_db, member.phone, "", "msg1", has_media=True, media_file_path="/data/doc.pdf"
    )
    assert "🔒" in result
    assert "מסמכים" in result
    mock_log.assert_called_once()
    call_kwargs = mock_log.call_args
    assert call_kwargs[1]["action"] == "permission_denied" or call_kwargs.kwargs.get("action") == "permission_denied"


@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.log_action")
@patch("src.services.message_handler.check_permission", return_value=False)
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_grandparent_cannot_create_task(
    mock_auth, mock_perm, mock_log, mock_conv, mock_db
) -> None:
    """Grandparent role without tasks write permission is denied task creation."""
    member = _make_member_with_role("grandparent")
    mock_auth.return_value = member
    result = await handle_incoming_message(
        mock_db, member.phone, "משימה חדשה: קניות", "msg1"
    )
    assert "🔒" in result
    assert "ליצור" in result
    mock_log.assert_called_once()
    call_kwargs = mock_log.call_args
    assert call_kwargs[1]["action"] == "permission_denied" or call_kwargs.kwargs.get("action") == "permission_denied"


@pytest.mark.asyncio
@patch("src.services.message_handler._save_conversation")
@patch("src.services.message_handler.process_document", new_callable=AsyncMock)
@patch("src.services.message_handler.log_action")
@patch("src.services.message_handler.list_tasks")
@patch("src.services.message_handler.create_task")
@patch("src.services.message_handler.check_permission", return_value=True)
@patch("src.services.message_handler.get_family_member_by_phone")
async def test_parent_can_do_all_operations(
    mock_auth, mock_perm, mock_create, mock_list, mock_log, mock_doc, mock_conv, mock_db
) -> None:
    """Parent role with full permissions can perform all operations."""
    member = _make_member_with_role("parent")
    mock_auth.return_value = member
    mock_list.return_value = [_make_task("Buy milk")]

    # List tasks
    result = await handle_incoming_message(mock_db, member.phone, "משימות", "msg1")
    assert "Buy milk" in result
    assert "🔒" not in result

    # Create task
    mock_create.return_value = _make_task("קניות")
    result = await handle_incoming_message(
        mock_db, member.phone, "משימה חדשה: קניות", "msg2"
    )
    assert "משימה נוצרה" in result
    assert "🔒" not in result

    # Upload document
    result = await handle_incoming_message(
        mock_db, member.phone, "", "msg3", has_media=True, media_file_path="/data/doc.pdf"
    )
    assert "קיבלתי את הקובץ" in result
    assert "🔒" not in result
