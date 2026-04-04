"""Preservation property tests for document routing.

These tests capture the BASELINE behavior of the unfixed code — every command
that already works correctly today.  They MUST PASS on unfixed code so that
after the fix we can re-run them to confirm zero regressions.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8**
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.engine.command_parser import parse_command
from src.services.document_query_service import _FIELD_QUESTION_MAP
from src.skills.document_skill import DocumentSkill
from src.skills.registry import SkillRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_doc_registry() -> SkillRegistry:
    """Registry with only DocumentSkill (mirrors production for routing tests)."""
    reg = SkillRegistry()
    reg.register(DocumentSkill())
    return reg


# ---------------------------------------------------------------------------
# Known-good command → (skill, action) pairs observed on UNFIXED code
# ---------------------------------------------------------------------------

EXISTING_DOCUMENT_COMMANDS: list[tuple[str, str, str]] = [
    # (message, expected_skill, expected_action)
    ("מסמכים", "document", "list"),
    ("הראה חשבוניות", "document", "search"),
    ("מסמך אחרון", "document", "recent"),
    ("מסמכים אחרונים", "document", "recent_feed"),
    ("תוסיף תגית #test", "document", "tag_add"),
    ("הסר תגית #test", "document", "tag_remove"),
    ("חוזים פעילים", "document", "view_active_contracts"),
    ("מסמכי ביטוח", "document", "view_insurance_documents"),
    ("חשבוניות אחרונות", "document", "view_recent_invoices"),
    ("מסמכים לבדיקה", "document", "view_needs_review"),
    ("מה הסכום של המסמך", "document", "query"),
]

# Messages that return None from parse_command (free-form / ChatSkill)
FREEFORM_MESSAGES: list[str] = [
    "שלום",
    "מה המצב?",
    "תודה רבה",
    "בוקר טוב",
    "מה שלומך?",
]


# ---------------------------------------------------------------------------
# Property 2a: Existing document commands preserve (skill, action) routing
# **Validates: Requirements 3.1, 3.2, 3.3, 3.7, 3.8**
# ---------------------------------------------------------------------------

@given(
    data=st.sampled_from(EXISTING_DOCUMENT_COMMANDS),
)
@settings(max_examples=len(EXISTING_DOCUMENT_COMMANDS))
def test_existing_document_commands_preserve_routing(data):
    """Property 2a: Every known-good document command produces the same
    (skill, action) tuple as observed on unfixed code.

    **Validates: Requirements 3.1, 3.2, 3.7, 3.8**
    """
    message, expected_skill, expected_action = data
    registry = _make_doc_registry()
    command = parse_command(message, registry)

    assert command is not None, (
        f"parse_command returned None for known-good message: '{message}' — "
        f"expected ({expected_skill}, {expected_action})"
    )
    assert command.skill == expected_skill, (
        f"Skill mismatch for '{message}': got '{command.skill}', expected '{expected_skill}'"
    )
    assert command.action == expected_action, (
        f"Action mismatch for '{message}': got '{command.action}', expected '{expected_action}'"
    )


# ---------------------------------------------------------------------------
# Property 2b: Non-document free-form messages return None
# **Validates: Requirements 3.4, 3.5**
# ---------------------------------------------------------------------------

@given(msg=st.sampled_from(FREEFORM_MESSAGES))
@settings(max_examples=len(FREEFORM_MESSAGES))
def test_freeform_messages_return_none(msg: str):
    """Property 2b: Non-document free-form messages return None from
    parse_command (they should continue to fall through to ChatSkill).

    **Validates: Requirements 3.4, 3.5**
    """
    registry = _make_doc_registry()
    command = parse_command(msg, registry)

    assert command is None, (
        f"parse_command should return None for free-form message '{msg}', "
        f"but got Command(skill='{command.skill}', action='{command.action}')"
    )


# ---------------------------------------------------------------------------
# Property 2c: Media messages route to document save
# **Validates: Requirements 3.6**
# ---------------------------------------------------------------------------

def test_media_messages_route_to_document_save():
    """Property 2c: Media messages continue to route to DocumentSkill save.

    **Validates: Requirements 3.6**
    """
    registry = _make_doc_registry()
    command = parse_command(
        "", registry, has_media=True, media_file_path="/tmp/test.pdf"
    )

    assert command is not None
    assert command.skill == "document"
    assert command.action == "save"
    assert command.params.get("media_file_path") == "/tmp/test.pdf"


# ---------------------------------------------------------------------------
# Property 2d: _FIELD_QUESTION_MAP existing entries are preserved
# **Validates: Requirements 3.3, 3.8**
# ---------------------------------------------------------------------------

EXPECTED_FIELD_MAP_ENTRIES: list[tuple[str, str]] = [
    ("סכום", "amount"),
    ("amount", "amount"),
    ("כמה", "amount"),
    ("עולה", "amount"),
    ("סוג", "doc_type"),
    ("type", "doc_type"),
    ("what type", "doc_type"),
    ("מה סוג", "doc_type"),
    ("ספק", "vendor"),
    ("vendor", "vendor"),
    ("counterparty", "vendor"),
    ("מי", "vendor"),
    ("תאריך", "doc_date"),
    ("date", "doc_date"),
    ("מתי", "doc_date"),
    ("סיכום", "ai_summary"),
    ("summary", "ai_summary"),
    ("תקציר", "ai_summary"),
]


@given(entry=st.sampled_from(EXPECTED_FIELD_MAP_ENTRIES))
@settings(max_examples=len(EXPECTED_FIELD_MAP_ENTRIES))
def test_field_question_map_entries_preserved(entry):
    """Property 2d: All existing _FIELD_QUESTION_MAP entries are preserved.

    **Validates: Requirements 3.3, 3.8**
    """
    keyword, expected_field = entry
    assert keyword in _FIELD_QUESTION_MAP, (
        f"Expected keyword '{keyword}' to be in _FIELD_QUESTION_MAP but it was missing"
    )
    assert _FIELD_QUESTION_MAP[keyword] == expected_field, (
        f"_FIELD_QUESTION_MAP['{keyword}'] = '{_FIELD_QUESTION_MAP[keyword]}', "
        f"expected '{expected_field}'"
    )


# ---------------------------------------------------------------------------
# Property 2e: System commands (confirm/cancel) still work
# **Validates: Requirements 3.4 (non-document routing preserved)**
# ---------------------------------------------------------------------------

SYSTEM_COMMANDS: list[tuple[str, str, str]] = [
    ("כן", "system", "confirm"),
    ("בטל", "system", "cancel"),
]


@given(data=st.sampled_from(SYSTEM_COMMANDS))
@settings(max_examples=len(SYSTEM_COMMANDS))
def test_system_commands_preserved(data):
    """Property 2e: System confirm/cancel commands still route correctly.

    **Validates: Requirements 3.4**
    """
    message, expected_skill, expected_action = data
    registry = _make_doc_registry()
    command = parse_command(message, registry)

    assert command is not None, (
        f"parse_command returned None for system command: '{message}'"
    )
    assert command.skill == expected_skill, (
        f"Skill mismatch for '{message}': got '{command.skill}', expected '{expected_skill}'"
    )
    assert command.action == expected_action, (
        f"Action mismatch for '{message}': got '{command.action}', expected '{expected_action}'"
    )
