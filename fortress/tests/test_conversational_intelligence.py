"""Tests for the conversational-intelligence feature.

Covers:
- Completion phrase detection
- Signal-based task tracking functions (record_task_signal, check_downgrade_signals, etc.)
- Inactivity timeout
- Dev intent detection
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from src.models.schema import ConversationState, FamilyMember

# Patch target for get_state (imported locally inside model_selector functions)
_GET_STATE = "src.services.conversation_state.get_state"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(context: dict | None = None) -> MagicMock:
    s = MagicMock(spec=ConversationState)
    s.context = dict(context) if context else {}
    return s


MEMBER_ID = uuid.uuid4()


# ---------------------------------------------------------------------------
# 1. _is_completion_phrase tests
# ---------------------------------------------------------------------------

class TestCompletionPhrase:
    def test_hebrew_toda(self):
        from src.services.message_handler import _is_completion_phrase
        assert _is_completion_phrase("תודה") is True

    def test_english_done(self):
        from src.services.message_handler import _is_completion_phrase
        assert _is_completion_phrase("done") is True

    def test_english_thanks(self):
        from src.services.message_handler import _is_completion_phrase
        assert _is_completion_phrase("thanks") is True

    def test_english_bye(self):
        from src.services.message_handler import _is_completion_phrase
        assert _is_completion_phrase("bye") is True

    def test_hebrew_toda_raba(self):
        from src.services.message_handler import _is_completion_phrase
        assert _is_completion_phrase("תודה רבה") is True

    def test_case_insensitive(self):
        from src.services.message_handler import _is_completion_phrase
        assert _is_completion_phrase("Done") is True
        assert _is_completion_phrase("THANKS") is True

    def test_whitespace_stripped(self):
        from src.services.message_handler import _is_completion_phrase
        assert _is_completion_phrase("  done  ") is True

    def test_normal_message_rejected(self):
        from src.services.message_handler import _is_completion_phrase
        assert _is_completion_phrase("מה המשימות שלי") is False

    def test_partial_match_rejected(self):
        from src.services.message_handler import _is_completion_phrase
        assert _is_completion_phrase("thanks for the help") is False

    def test_empty_string_rejected(self):
        from src.services.message_handler import _is_completion_phrase
        assert _is_completion_phrase("") is False


# ---------------------------------------------------------------------------
# 2. record_task_signal tests
# ---------------------------------------------------------------------------

class TestRecordTaskSignal:
    @patch(_GET_STATE)
    def test_writes_signal_to_context(self, mock_get_state):
        from src.services.model_selector import record_task_signal
        state = _make_state()
        mock_get_state.return_value = state
        db = MagicMock(spec=Session)

        record_task_signal(db, MEMBER_ID, "tool_completed")

        assert state.context["last_task_signal"] == "tool_completed"
        db.flush.assert_called_once()

    @patch(_GET_STATE)
    def test_overwrites_previous_signal(self, mock_get_state):
        from src.services.model_selector import record_task_signal
        state = _make_state({"last_task_signal": "tool_completed"})
        mock_get_state.return_value = state
        db = MagicMock(spec=Session)

        record_task_signal(db, MEMBER_ID, "post_tool_chat")

        assert state.context["last_task_signal"] == "post_tool_chat"

    @patch(_GET_STATE)
    def test_preserves_other_context_keys(self, mock_get_state):
        from src.services.model_selector import record_task_signal
        state = _make_state({"model_tier_override": "powerful", "other_key": "value"})
        mock_get_state.return_value = state
        db = MagicMock(spec=Session)

        record_task_signal(db, MEMBER_ID, "user_done")

        assert state.context["model_tier_override"] == "powerful"
        assert state.context["other_key"] == "value"
        assert state.context["last_task_signal"] == "user_done"


# ---------------------------------------------------------------------------
# 3. check_inactivity_timeout tests
# ---------------------------------------------------------------------------

class TestCheckInactivityTimeout:
    @patch(_GET_STATE)
    def test_returns_false_when_no_timestamp(self, mock_get_state):
        from src.services.model_selector import check_inactivity_timeout
        state = _make_state({})
        mock_get_state.return_value = state
        db = MagicMock(spec=Session)

        assert check_inactivity_timeout(db, MEMBER_ID) is False

    @patch("src.config.INACTIVITY_TIMEOUT_MINUTES", 10)
    @patch(_GET_STATE)
    def test_returns_true_when_expired(self, mock_get_state):
        from src.services.model_selector import check_inactivity_timeout
        old_ts = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
        state = _make_state({"last_message_ts": old_ts})
        mock_get_state.return_value = state
        db = MagicMock(spec=Session)

        assert check_inactivity_timeout(db, MEMBER_ID) is True

    @patch("src.config.INACTIVITY_TIMEOUT_MINUTES", 10)
    @patch(_GET_STATE)
    def test_returns_false_when_recent(self, mock_get_state):
        from src.services.model_selector import check_inactivity_timeout
        recent_ts = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
        state = _make_state({"last_message_ts": recent_ts})
        mock_get_state.return_value = state
        db = MagicMock(spec=Session)

        assert check_inactivity_timeout(db, MEMBER_ID) is False

    @patch(_GET_STATE)
    def test_returns_false_for_invalid_timestamp(self, mock_get_state):
        from src.services.model_selector import check_inactivity_timeout
        state = _make_state({"last_message_ts": "not-a-timestamp"})
        mock_get_state.return_value = state
        db = MagicMock(spec=Session)

        assert check_inactivity_timeout(db, MEMBER_ID) is False


# ---------------------------------------------------------------------------
# 4. check_downgrade_signals tests
# ---------------------------------------------------------------------------

class TestCheckDowngradeSignals:
    @patch(_GET_STATE)
    def test_returns_true_for_post_tool_chat(self, mock_get_state):
        from src.services.model_selector import check_downgrade_signals
        state = _make_state({"last_task_signal": "post_tool_chat"})
        mock_get_state.return_value = state
        db = MagicMock(spec=Session)

        assert check_downgrade_signals(db, MEMBER_ID) is True

    @patch(_GET_STATE)
    def test_returns_true_for_user_done(self, mock_get_state):
        from src.services.model_selector import check_downgrade_signals
        state = _make_state({"last_task_signal": "user_done"})
        mock_get_state.return_value = state
        db = MagicMock(spec=Session)

        assert check_downgrade_signals(db, MEMBER_ID) is True

    @patch(_GET_STATE)
    def test_returns_true_for_topic_shift(self, mock_get_state):
        from src.services.model_selector import check_downgrade_signals
        state = _make_state({"last_task_signal": "topic_shift"})
        mock_get_state.return_value = state
        db = MagicMock(spec=Session)

        assert check_downgrade_signals(db, MEMBER_ID) is True

    @patch(_GET_STATE)
    def test_returns_false_for_tool_completed(self, mock_get_state):
        from src.services.model_selector import check_downgrade_signals
        state = _make_state({"last_task_signal": "tool_completed"})
        mock_get_state.return_value = state
        db = MagicMock(spec=Session)

        assert check_downgrade_signals(db, MEMBER_ID) is False

    @patch(_GET_STATE)
    def test_returns_false_when_no_signal(self, mock_get_state):
        from src.services.model_selector import check_downgrade_signals
        state = _make_state({})
        mock_get_state.return_value = state
        db = MagicMock(spec=Session)

        assert check_downgrade_signals(db, MEMBER_ID) is False


# ---------------------------------------------------------------------------
# 5. detect_dev_intent tests
# ---------------------------------------------------------------------------

class TestDetectDevIntent:
    def test_returns_none_for_non_admin(self):
        from src.services.agent_loop import detect_dev_intent
        result = detect_dev_intent("אני רוצה שפורטרס ידע לזהות מתכונים", is_admin=False, tool_router_intent="chat")
        assert result == (None, None)

    def test_returns_none_when_tool_router_is_dev(self):
        from src.services.agent_loop import detect_dev_intent
        result = detect_dev_intent("אני רוצה שפורטרס ידע לזהות מתכונים", is_admin=True, tool_router_intent="dev")
        assert result == (None, None)

    def test_detects_hebrew_feature_request(self):
        from src.services.agent_loop import detect_dev_intent
        tool, msg = detect_dev_intent("אני רוצה שפורטרס ידע לזהות מתכונים מתמונות", is_admin=True, tool_router_intent="chat")
        assert tool == "dev_plan"
        assert msg is not None
        assert "פיצ'ר" in msg

    def test_detects_english_feature_request(self):
        from src.services.agent_loop import detect_dev_intent
        tool, msg = detect_dev_intent("I want fortress to recognize recipes from images", is_admin=True, tool_router_intent="chat")
        assert tool == "dev_plan"
        assert msg is not None

    def test_detects_hebrew_gap(self):
        from src.services.agent_loop import detect_dev_intent
        tool, msg = detect_dev_intent("למה אין אפשרות לחפש לפי תאריך", is_admin=True, tool_router_intent="chat")
        assert tool == "dev_query"
        assert msg is not None

    def test_returns_none_for_normal_conversation(self):
        from src.services.agent_loop import detect_dev_intent
        assert detect_dev_intent("מה שלומך", is_admin=True, tool_router_intent="chat") == (None, None)
        assert detect_dev_intent("מה המשימות שלי", is_admin=True, tool_router_intent="chat") == (None, None)
        assert detect_dev_intent("how are you", is_admin=True, tool_router_intent="chat") == (None, None)

    def test_detects_need_to_add(self):
        from src.services.agent_loop import detect_dev_intent
        tool, msg = detect_dev_intent("צריך להוסיף תמיכה בתמונות", is_admin=True, tool_router_intent="chat")
        assert tool == "dev_plan"

    def test_detects_can_you_build(self):
        from src.services.agent_loop import detect_dev_intent
        tool, msg = detect_dev_intent("can you build a dashboard for tasks?", is_admin=True, tool_router_intent="chat")
        assert tool == "dev_plan"


# ---------------------------------------------------------------------------
# 6. clear_task_tracking tests
# ---------------------------------------------------------------------------

class TestClearTaskTracking:
    @patch(_GET_STATE)
    def test_removes_tracking_keys(self, mock_get_state):
        from src.services.model_selector import clear_task_tracking
        state = _make_state({
            "last_task_signal": "tool_completed",
            "last_intent_group": "documents",
            "model_tier_override": "powerful",
        })
        mock_get_state.return_value = state
        db = MagicMock(spec=Session)

        clear_task_tracking(db, MEMBER_ID)

        assert "last_task_signal" not in state.context
        assert "last_intent_group" not in state.context
        assert state.context["model_tier_override"] == "powerful"
        db.flush.assert_called_once()


# ---------------------------------------------------------------------------
# 7. record_intent_group / record_message_timestamp tests
# ---------------------------------------------------------------------------

class TestRecordMetadata:
    @patch(_GET_STATE)
    def test_record_intent_group(self, mock_get_state):
        from src.services.model_selector import record_intent_group
        state = _make_state()
        mock_get_state.return_value = state
        db = MagicMock(spec=Session)

        record_intent_group(db, MEMBER_ID, "documents")

        assert state.context["last_intent_group"] == "documents"
        db.flush.assert_called_once()

    @patch(_GET_STATE)
    def test_record_message_timestamp(self, mock_get_state):
        from src.services.model_selector import record_message_timestamp
        state = _make_state()
        mock_get_state.return_value = state
        db = MagicMock(spec=Session)

        record_message_timestamp(db, MEMBER_ID)

        ts = state.context["last_message_ts"]
        assert ts is not None
        parsed = datetime.fromisoformat(ts)
        assert (datetime.now(timezone.utc) - parsed).total_seconds() < 5
