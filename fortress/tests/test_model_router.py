"""Unit tests for the model router service."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.schema import FamilyMember, Task
from src.services.model_router import route_message


def _make_member(
    *,
    phone: str = "972501234567",
    name: str = "Test User",
    role: str = "parent",
) -> MagicMock:
    m = MagicMock(spec=FamilyMember)
    m.id = uuid.uuid4()
    m.name = name
    m.phone = phone
    m.role = role
    m.is_active = True
    return m


def _make_task(title: str = "Buy milk", due_date=None) -> MagicMock:
    t = MagicMock(spec=Task)
    t.id = uuid.uuid4()
    t.title = title
    t.due_date = due_date
    t.status = "open"
    t.priority = "normal"
    return t


# ── Intent routing tests ─────────────────────────────────────────


@pytest.mark.asyncio
@patch("src.services.model_router._save_conversation")
@patch("src.services.model_router.OllamaClient")
@patch("src.services.model_router.detect_intent", new_callable=AsyncMock)
@patch("src.services.model_router.check_permission", return_value=True)
@patch("src.services.model_router.list_tasks")
async def test_list_tasks_intent(
    mock_list, mock_perm, mock_detect, mock_llm_cls, mock_conv, mock_db
) -> None:
    """list_tasks intent should fetch tasks and use LLM to format."""
    mock_detect.return_value = "list_tasks"
    mock_list.return_value = [_make_task("Buy milk")]
    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(return_value="1. 🟢 Buy milk")
    mock_llm_cls.return_value = mock_llm

    member = _make_member()
    result = await route_message(mock_db, member, member.phone, "משימות")
    assert "Buy milk" in result
    mock_list.assert_called_once()


@pytest.mark.asyncio
@patch("src.services.model_router._save_conversation")
@patch("src.services.model_router.OllamaClient")
@patch("src.services.model_router.detect_intent", new_callable=AsyncMock)
@patch("src.services.model_router.check_permission", return_value=True)
@patch("src.services.model_router.create_task")
async def test_create_task_intent(
    mock_create, mock_perm, mock_detect, mock_llm_cls, mock_conv, mock_db
) -> None:
    """create_task intent should extract details and create task."""
    mock_detect.return_value = "create_task"
    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(
        side_effect=['{"title": "לקנות חלב", "due_date": null, "category": "groceries", "priority": "normal"}', "משימה נוצרה: לקנות חלב ✅"]
    )
    mock_llm_cls.return_value = mock_llm
    mock_create.return_value = _make_task("לקנות חלב")

    member = _make_member()
    result = await route_message(mock_db, member, member.phone, "משימה חדשה: לקנות חלב")
    assert "לקנות חלב" in result
    mock_create.assert_called_once()


@pytest.mark.asyncio
@patch("src.services.model_router._save_conversation")
@patch("src.services.model_router.OllamaClient")
@patch("src.services.model_router.detect_intent", new_callable=AsyncMock)
async def test_greeting_intent(mock_detect, mock_llm_cls, mock_conv, mock_db) -> None:
    """greeting intent should generate personalized response."""
    mock_detect.return_value = "greeting"
    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(return_value="שלום Test User! מה שלומך?")
    mock_llm_cls.return_value = mock_llm

    member = _make_member(name="Test User")
    result = await route_message(mock_db, member, member.phone, "שלום")
    assert "Test User" in result


@pytest.mark.asyncio
@patch("src.services.model_router._save_conversation")
@patch("src.services.model_router.OllamaClient")
@patch("src.services.model_router.detect_intent", new_callable=AsyncMock)
async def test_unknown_intent_returns_help(mock_detect, mock_llm_cls, mock_conv, mock_db) -> None:
    """unknown intent should return Hebrew help message."""
    mock_detect.return_value = "unknown"
    mock_llm = MagicMock()
    mock_llm_cls.return_value = mock_llm

    member = _make_member()
    result = await route_message(mock_db, member, member.phone, "gibberish")
    assert "לא הבנתי" in result
    assert "משימות" in result


@pytest.mark.asyncio
@patch("src.services.model_router._save_conversation")
@patch("src.services.model_router.OllamaClient")
@patch("src.services.model_router.detect_intent", new_callable=AsyncMock)
async def test_ask_question_intent(mock_detect, mock_llm_cls, mock_conv, mock_db) -> None:
    """ask_question intent should use LLM to generate response."""
    mock_detect.return_value = "ask_question"
    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(return_value="התשובה היא 42")
    mock_llm_cls.return_value = mock_llm

    member = _make_member()
    result = await route_message(mock_db, member, member.phone, "מה התשובה?")
    assert "42" in result


# ── Permission tests ─────────────────────────────────────────────


@pytest.mark.asyncio
@patch("src.services.model_router._save_conversation")
@patch("src.services.model_router.log_action")
@patch("src.services.model_router.OllamaClient")
@patch("src.services.model_router.detect_intent", new_callable=AsyncMock)
@patch("src.services.model_router.check_permission", return_value=False)
async def test_permission_denied_returns_lock(
    mock_perm, mock_detect, mock_llm_cls, mock_log, mock_conv, mock_db
) -> None:
    """Permission denied should return 🔒 message and audit log."""
    mock_detect.return_value = "list_tasks"
    mock_llm = MagicMock()
    mock_llm_cls.return_value = mock_llm

    member = _make_member()
    result = await route_message(mock_db, member, member.phone, "משימות")
    assert "🔒" in result
    mock_log.assert_called_once()
    call_kwargs = mock_log.call_args[1]
    assert call_kwargs["action"] == "permission_denied"


@pytest.mark.asyncio
@patch("src.services.model_router._save_conversation")
@patch("src.services.model_router.log_action")
@patch("src.services.model_router.OllamaClient")
@patch("src.services.model_router.detect_intent", new_callable=AsyncMock)
@patch("src.services.model_router.check_permission", return_value=False)
async def test_permission_denied_create_task(
    mock_perm, mock_detect, mock_llm_cls, mock_log, mock_conv, mock_db
) -> None:
    """Permission denied on create_task should return 🔒."""
    mock_detect.return_value = "create_task"
    mock_llm = MagicMock()
    mock_llm_cls.return_value = mock_llm

    member = _make_member(role="child")
    result = await route_message(mock_db, member, member.phone, "משימה חדשה: test")
    assert "🔒" in result


# ── Conversation saving ──────────────────────────────────────────


@pytest.mark.asyncio
@patch("src.services.model_router.OllamaClient")
@patch("src.services.model_router.detect_intent", new_callable=AsyncMock)
async def test_conversation_saved_with_intent(mock_detect, mock_llm_cls, mock_db) -> None:
    """Every routed message should save a conversation with the detected intent."""
    mock_detect.return_value = "unknown"
    mock_llm = MagicMock()
    mock_llm_cls.return_value = mock_llm

    member = _make_member()
    await route_message(mock_db, member, member.phone, "test message")
    assert mock_db.add.called
    assert mock_db.commit.called


@pytest.mark.asyncio
@patch("src.services.model_router._save_conversation")
@patch("src.services.model_router.OllamaClient")
@patch("src.services.model_router.detect_intent", new_callable=AsyncMock)
@patch("src.services.model_router.check_permission", return_value=True)
@patch("src.services.model_router.process_document", new_callable=AsyncMock)
@patch("src.services.model_router.log_action")
async def test_upload_document_intent(
    mock_log, mock_doc, mock_perm, mock_detect, mock_llm_cls, mock_conv, mock_db
) -> None:
    """upload_document intent should delegate to document processing."""
    mock_detect.return_value = "upload_document"
    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(return_value="קובץ נשמר ✅")
    mock_llm_cls.return_value = mock_llm

    member = _make_member()
    result = await route_message(
        mock_db, member, member.phone, "", has_media=True, media_file_path="/data/doc.pdf"
    )
    assert "נשמר" in result or "קובץ" in result
    mock_doc.assert_called_once()
