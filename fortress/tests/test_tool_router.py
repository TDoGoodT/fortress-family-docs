"""Unit tests for Tool_Router classify() function."""
import sys
from unittest.mock import MagicMock

# Inject fake psycopg2 before any src imports
if "psycopg2" not in sys.modules:
    _fake = MagicMock()
    sys.modules["psycopg2"] = _fake
    sys.modules["psycopg2.extensions"] = _fake.extensions
    sys.modules["psycopg2.extras"] = _fake.extras

from src.engine.tool_router import classify


def _tool_names(tools: list[dict]) -> list[str]:
    """Extract tool names from schema list."""
    return [t["toolSpec"]["name"] for t in tools]


# ---------------------------------------------------------------------------
# Intent classification tests
# ---------------------------------------------------------------------------

class TestClassifyIntentGroups:
    """Test that each intent group is correctly classified."""

    def test_empty_string_returns_chat(self):
        group, tools = classify("", None)
        assert group == "chat"
        assert len(tools) == 5

    def test_documents_hebrew_keyword_sum(self):
        group, tools = classify("מה הסכום?", "document")
        assert group == "documents"
        assert "document_query" in _tool_names(tools)

    def test_documents_hebrew_keyword_invoice(self):
        group, tools = classify("יש לי חשבונית חדשה", None)
        assert group == "documents"

    def test_documents_english_keyword(self):
        group, tools = classify("show me the invoice", None)
        assert group == "documents"

    def test_tasks_group(self):
        group, tools = classify("צור משימה", None)
        assert group == "tasks"
        names = _tool_names(tools)
        assert "task_create" in names

    def test_recipes_group(self):
        group, tools = classify("מתכון לעוגה", None)
        assert group == "recipes"
        names = _tool_names(tools)
        assert "document_recipe_list" in names

    def test_memory_group(self):
        group, tools = classify("זכור שאני אוהב פיצה", None)
        assert group == "memory"
        names = _tool_names(tools)
        assert "memory_list" in names

    def test_recurring_group(self):
        group, tools = classify("כל שבוע תזכיר לי", None)
        assert group == "recurring"
        names = _tool_names(tools)
        assert "recurring_create" in names

    def test_bugs_group(self):
        group, tools = classify("יש באג", None)
        assert group == "bugs"
        names = _tool_names(tools)
        assert "bug_report" in names

    def test_system_group(self):
        group, tools = classify("עזרה", None)
        assert group == "system"
        names = _tool_names(tools)
        assert "system_help" in names


# ---------------------------------------------------------------------------
# Context boost tests
# ---------------------------------------------------------------------------

class TestContextBoost:
    """Test context boost when last_entity_type is 'document'."""

    def test_no_keyword_with_document_entity_boosts_to_documents(self):
        """No keyword match + last_entity_type='document' → documents group."""
        group, tools = classify("מה זה?", "document")
        assert group == "documents"
        assert "document_query" in _tool_names(tools)

    def test_no_keyword_without_entity_falls_to_chat(self):
        """No keyword match + no entity → chat group."""
        group, tools = classify("מה זה?", None)
        assert group == "chat"

    def test_keyword_match_overrides_entity_type(self):
        """Keyword match takes priority over entity type."""
        group, tools = classify("צור משימה", "document")
        assert group == "tasks"


# ---------------------------------------------------------------------------
# Tool count bounds tests
# ---------------------------------------------------------------------------

class TestToolCountBounds:
    """Test that all groups return between 5 and 8 tools."""

    def test_chat_tool_count(self):
        _, tools = classify("", None)
        assert 5 <= len(tools) <= 8

    def test_documents_tool_count(self):
        _, tools = classify("מסמך", None)
        assert 5 <= len(tools) <= 8

    def test_tasks_tool_count(self):
        _, tools = classify("משימה", None)
        assert 5 <= len(tools) <= 8

    def test_recipes_tool_count(self):
        _, tools = classify("מתכון", None)
        assert 5 <= len(tools) <= 8

    def test_memory_tool_count(self):
        _, tools = classify("זיכרון", None)
        assert 5 <= len(tools) <= 8

    def test_recurring_tool_count(self):
        _, tools = classify("כל שבוע", None)
        assert 5 <= len(tools) <= 8

    def test_bugs_tool_count(self):
        _, tools = classify("באג", None)
        assert 5 <= len(tools) <= 8

    def test_system_tool_count(self):
        _, tools = classify("עזרה", None)
        assert 5 <= len(tools) <= 8


# ---------------------------------------------------------------------------
# Group invariants tests
# ---------------------------------------------------------------------------

class TestGroupInvariants:
    """Test that specific tools are always present in their groups."""

    def test_documents_always_has_document_query(self):
        group, tools = classify("חשבונית", None)
        assert group == "documents"
        assert "document_query" in _tool_names(tools)

    def test_chat_always_has_save_text(self):
        group, tools = classify("", None)
        assert group == "chat"
        assert "save_text" in _tool_names(tools)

    def test_tools_are_valid_schema_dicts(self):
        """Every returned tool must have toolSpec.name."""
        _, tools = classify("מסמך", None)
        for tool in tools:
            assert "toolSpec" in tool
            assert "name" in tool["toolSpec"]


# ---------------------------------------------------------------------------
# Priority order tests
# ---------------------------------------------------------------------------

class TestPriorityOrder:
    """Test that documents has higher priority than other groups."""

    def test_document_keyword_wins_over_task_context(self):
        """'מסמך' keyword → documents, even with task-like context."""
        group, _ = classify("מסמך של משימה", None)
        assert group == "documents"
