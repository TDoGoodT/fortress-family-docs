"""Bug condition exploration tests for document routing.

These tests encode the EXPECTED behavior: document-related Hebrew messages
should route to DocumentSkill. On UNFIXED code, they are expected to FAIL,
confirming the bug exists.

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.6**
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
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def doc_registry() -> SkillRegistry:
    """Registry with DocumentSkill registered (mirrors production setup)."""
    reg = SkillRegistry()
    reg.register(DocumentSkill())
    return reg


def _make_doc_registry() -> SkillRegistry:
    """Standalone helper (for use inside hypothesis tests where fixtures aren't available)."""
    reg = SkillRegistry()
    reg.register(DocumentSkill())
    return reg


# ---------------------------------------------------------------------------
# Property 1: Bug Condition — document-related messages SHOULD route to
# DocumentSkill but currently DON'T.
# ---------------------------------------------------------------------------

# Hebrew messages that are clearly document-related but miss existing regex patterns
DOCUMENT_MESSAGES_THAT_SHOULD_ROUTE = [
    "איזה מסמכים קיימים?",       # "What documents exist?" — listing variant
    "תביא לי הסכם שיפוץ",        # "Bring me the renovation contract" — fetch by name
    "כמה עלה הביטוח",             # "How much did the insurance cost?" — category search
    "רשימת מסמכים",               # "Document list" — listing variant
    "מה המסמכים שלי?",            # "What are my documents?" — listing variant
]


def test_delete_documents_intent_maps_to_delete_action():
    registry = _make_doc_registry()
    command = parse_command("נקה מסמכים", registry)
    assert command is not None
    assert command.skill == "document"
    assert command.action == "delete_documents"


@given(msg=st.sampled_from(DOCUMENT_MESSAGES_THAT_SHOULD_ROUTE))
@settings(max_examples=len(DOCUMENT_MESSAGES_THAT_SHOULD_ROUTE))
def test_document_messages_route_to_document_skill(msg: str):
    """Property 1: Bug Condition — document-related Hebrew messages must route to DocumentSkill.

    **Validates: Requirements 1.1, 1.2, 1.3, 1.6**

    On UNFIXED code this test is EXPECTED TO FAIL because parse_command returns
    None for these messages (they fall through to ChatSkill).
    """
    registry = _make_doc_registry()
    command = parse_command(msg, registry)

    # Expected behavior: command should not be None and should route to "document" skill
    assert command is not None, (
        f"parse_command returned None for document-related message: '{msg}' — "
        f"message falls through to ChatSkill instead of DocumentSkill"
    )
    assert command.skill == "document", (
        f"parse_command routed '{msg}' to skill='{command.skill}' instead of 'document'"
    )


# ---------------------------------------------------------------------------
# Bug Condition: _FIELD_QUESTION_MAP gap — "לתשלום" is not mapped
# ---------------------------------------------------------------------------

def test_field_question_map_missing_payment_keyword():
    """Confirm that 'לתשלום' IS now in _FIELD_QUESTION_MAP after the fix.

    **Validates: Requirements 1.4**

    The fix added "לתשלום" → "amount" to _FIELD_QUESTION_MAP, so this test
    now asserts the keyword IS present and maps to the correct field.
    """
    assert "לתשלום" in _FIELD_QUESTION_MAP, (
        "Expected 'לתשלום' to be in _FIELD_QUESTION_MAP after the fix, "
        "but it was not found."
    )
    assert _FIELD_QUESTION_MAP["לתשלום"] == "amount", (
        f"Expected _FIELD_QUESTION_MAP['לתשלום'] == 'amount', "
        f"but got '{_FIELD_QUESTION_MAP['לתשלום']}'"
    )
