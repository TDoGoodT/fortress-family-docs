"""Regression safety tests — edge cases and Hebrew keyword boundaries.

Sprint R3, Requirement 6.
"""

from src.engine.command_parser import parse_command
from src.engine.response_formatter import format_response, TRUNCATION_INDICATOR
from src.skills.base_skill import Command, Result
from src.skills.registry import registry

# Ensure skills are registered
import src.skills  # noqa: F401


# ── 1. Cancel keywords ──────────────────────────────────────────

def test_cancel_keywords():
    """All Hebrew cancel keywords should return a cancel Command."""
    keywords = ["לא", "עזוב", "תעזוב", "בטל", "תבטל", "ביטול"]
    for kw in keywords:
        cmd = parse_command(kw, registry)
        assert cmd is not None, f"'{kw}' should match cancel"
        assert cmd.skill == "system"
        assert cmd.action == "cancel"


# ── 2. Confirm keywords ─────────────────────────────────────────

def test_confirm_keywords():
    """All Hebrew confirm keywords should return a confirm Command."""
    keywords = ["כן", "אישור", "אשר", "בטח", "אוקיי", "אוקי"]
    for kw in keywords:
        cmd = parse_command(kw, registry)
        assert cmd is not None, f"'{kw}' should match confirm"
        assert cmd.skill == "system"
        assert cmd.action == "confirm"


# ── 3. "משימה" singular → task list, not delete ─────────────────

def test_singular_mishima_routes_to_list():
    """'משימה' alone should not trigger delete."""
    cmd = parse_command("משימה", registry)
    # Should either match task.list pattern or fall through to None (LLM)
    # It should NOT match delete
    if cmd is not None:
        assert cmd.action != "delete", "'משימה' should not trigger delete"


# ── 4. Media with text → media takes priority ───────────────────

def test_media_with_text_prioritizes_media():
    """Media messages should take priority over text content."""
    cmd = parse_command(
        "משימה חדשה: test", registry,
        has_media=True, media_file_path="/data/file.pdf",
    )
    assert cmd is not None
    assert cmd.skill == "document"
    assert cmd.action == "save"


# ── 5. Empty message → None (LLM fallback) ──────────────────────

def test_empty_message_llm_fallback():
    """Empty message should return None for LLM fallback."""
    cmd = parse_command("", registry)
    assert cmd is None


# ── 6. Long response → truncated ────────────────────────────────

def test_long_response_truncated():
    """Response exceeding 3500 chars should be truncated."""
    long_msg = "א" * 4000
    result = Result(success=True, message=long_msg)
    formatted = format_response(result)
    assert len(formatted) < len(long_msg)
    assert TRUNCATION_INDICATOR in formatted


# ── 7. Mixed Hebrew + English → pattern matching works ──────────

def test_mixed_hebrew_english():
    """Mixed Hebrew/English should attempt pattern matching normally."""
    cmd = parse_command("משימה חדשה: buy milk", registry)
    assert cmd is not None
    assert cmd.skill == "task"
    assert cmd.action == "create"
    assert cmd.params.get("title") == "buy milk"


def test_explicit_assignee_create_phrase_parses():
    """Explicit assignee create phrase should route to task.create with assignee."""
    cmd = parse_command("תרשום לחן משימה - לברר מה הקוד", registry)
    assert cmd is not None
    assert cmd.skill == "task"
    assert cmd.action == "create"
    assert cmd.params.get("assignee_name") == "חן"
    assert cmd.params.get("title") == "לברר מה הקוד"


def test_reassign_phrase_parses():
    """Post-create correction phrase should route to task.reassign."""
    cmd = parse_command("משימה 2 היא של חן", registry)
    assert cmd is not None
    assert cmd.skill == "task"
    assert cmd.action == "reassign"
    assert cmd.params.get("index") == "2"
    assert cmd.params.get("assignee_name") == "חן"


# ── 8. Emoji-only → None (LLM fallback) ─────────────────────────

def test_emoji_only_llm_fallback():
    """Emoji-only message should return None for LLM fallback."""
    cmd = parse_command("😀🎉👍", registry)
    assert cmd is None


# ── 9. Numbers-only → None (LLM fallback) ───────────────────────

def test_numbers_only_llm_fallback():
    """Numbers-only message should return None for LLM fallback."""
    cmd = parse_command("12345", registry)
    assert cmd is None
