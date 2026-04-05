"""Unit tests for recipe query service extensions — Task 6."""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.schema import Document, DocumentFact, FamilyMember
from src.services.document_query_service import (
    QAResult,
    answer_document_question,
    get_document_recipes,
    get_recipe_details,
    list_member_recipes,
    search_recipes,
)


def _make_member() -> MagicMock:
    m = MagicMock(spec=FamilyMember)
    m.id = uuid.uuid4()
    m.role = "parent"
    return m


def _make_doc(**kwargs) -> MagicMock:
    doc = MagicMock(spec=Document)
    doc.id = kwargs.get("id", uuid.uuid4())
    doc.doc_type = kwargs.get("doc_type", "recipe")
    doc.vendor = kwargs.get("vendor", None)
    doc.doc_date = kwargs.get("doc_date", None)
    doc.amount = kwargs.get("amount", None)
    doc.ai_summary = kwargs.get("ai_summary", None)
    doc.raw_text = kwargs.get("raw_text", "")
    doc.uploaded_by = kwargs.get("uploaded_by", uuid.uuid4())
    doc.display_name = kwargs.get("display_name", "ספר מתכונים של סבתא")
    doc.original_filename = kwargs.get("original_filename", "recipes.pdf")
    return doc


def _make_recipe_fact(document_id, fact_key, fact_value, source_excerpt="") -> MagicMock:
    f = MagicMock(spec=DocumentFact)
    f.id = uuid.uuid4()
    f.document_id = document_id
    f.fact_type = "recipe"
    f.fact_key = fact_key
    f.fact_value = fact_value
    f.confidence = Decimal("0.7")
    f.source_excerpt = source_excerpt
    return f


# ---------------------------------------------------------------------------
# 6.1 list_member_recipes
# ---------------------------------------------------------------------------

def test_list_member_recipes_returns_recipes():
    db = MagicMock()
    member_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    fact = _make_recipe_fact(doc_id, "recipe_name", "דג חריף")
    db.query.return_value.join.return_value.filter.return_value.all.return_value = [
        (fact, "ספר מתכונים של סבתא")
    ]

    results = list_member_recipes(db, member_id)
    assert len(results) == 1
    assert results[0]["recipe_name"] == "דג חריף"
    assert results[0]["document_id"] == doc_id
    assert results[0]["display_name"] == "ספר מתכונים של סבתא"


def test_list_member_recipes_empty():
    db = MagicMock()
    db.query.return_value.join.return_value.filter.return_value.all.return_value = []

    results = list_member_recipes(db, uuid.uuid4())
    assert results == []


def test_list_member_recipes_handles_none_display_name():
    db = MagicMock()
    doc_id = uuid.uuid4()
    fact = _make_recipe_fact(doc_id, "recipe_name", "בורקס גבינה")
    db.query.return_value.join.return_value.filter.return_value.all.return_value = [
        (fact, None)
    ]

    results = list_member_recipes(db, uuid.uuid4())
    assert results[0]["display_name"] == ""


# ---------------------------------------------------------------------------
# 6.2 search_recipes
# ---------------------------------------------------------------------------

def test_search_recipes_by_name():
    db = MagicMock()
    member_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    fact = _make_recipe_fact(doc_id, "recipe_name", "דג חריף")
    # name_matches returns results, ingredient_matches returns empty
    join_mock = db.query.return_value.join.return_value
    join_mock.filter.return_value.all.side_effect = [
        [(fact, "ספר מתכונים")],  # name matches
        [],                        # ingredient matches
    ]

    results = search_recipes(db, member_id, "דג")
    assert len(results) == 1
    assert results[0]["recipe_name"] == "דג חריף"
    assert results[0]["match_type"] == "name"


def test_search_recipes_by_ingredient():
    db = MagicMock()
    member_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    ingredient_fact = _make_recipe_fact(doc_id, "ingredients", "שמן זית, לימון, דג", "דג חריף")
    join_mock = db.query.return_value.join.return_value
    join_mock.filter.return_value.all.side_effect = [
        [],                                    # name matches
        [(ingredient_fact, "ספר מתכונים")],   # ingredient matches
    ]

    results = search_recipes(db, member_id, "לימון")
    assert len(results) == 1
    assert results[0]["recipe_name"] == "דג חריף"
    assert results[0]["match_type"] == "ingredient"


def test_search_recipes_empty_query():
    db = MagicMock()
    results = search_recipes(db, uuid.uuid4(), "")
    assert results == []


def test_search_recipes_no_duplicates():
    """Same recipe matched by both name and ingredient should appear once."""
    db = MagicMock()
    member_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    name_fact = _make_recipe_fact(doc_id, "recipe_name", "דג חריף")
    ingredient_fact = _make_recipe_fact(doc_id, "ingredients", "דג, שמן", "דג חריף")

    join_mock = db.query.return_value.join.return_value
    join_mock.filter.return_value.all.side_effect = [
        [(name_fact, "ספר מתכונים")],          # name matches
        [(ingredient_fact, "ספר מתכונים")],    # ingredient matches
    ]

    results = search_recipes(db, member_id, "דג")
    assert len(results) == 1


# ---------------------------------------------------------------------------
# 6.3 get_recipe_details
# ---------------------------------------------------------------------------

def test_get_recipe_details_found():
    db = MagicMock()
    member_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    name_fact = _make_recipe_fact(doc_id, "recipe_name", "דג חריף", "דג חריף")
    ingredients_fact = _make_recipe_fact(doc_id, "ingredients", "דג, שמן זית", "דג חריף")
    instructions_fact = _make_recipe_fact(doc_id, "instructions", "חממו תנור", "דג חריף")
    servings_fact = _make_recipe_fact(doc_id, "servings", "4", "דג חריף")

    # First query: find recipe_name fact
    db.query.return_value.join.return_value.filter.return_value.first.return_value = (
        name_fact, "ספר מתכונים של סבתא"
    )
    # Second query: load related facts
    db.query.return_value.filter.return_value.all.return_value = [
        name_fact, ingredients_fact, instructions_fact, servings_fact
    ]

    result = get_recipe_details(db, member_id, "דג חריף")
    assert result is not None
    assert result["recipe_name"] == "דג חריף"
    assert result["ingredients"] == "דג, שמן זית"
    assert result["instructions"] == "חממו תנור"
    assert result["servings"] == "4"
    assert result["display_name"] == "ספר מתכונים של סבתא"


def test_get_recipe_details_not_found():
    db = MagicMock()
    db.query.return_value.join.return_value.filter.return_value.first.return_value = None

    result = get_recipe_details(db, uuid.uuid4(), "מתכון שלא קיים")
    assert result is None


def test_get_recipe_details_empty_name():
    db = MagicMock()
    result = get_recipe_details(db, uuid.uuid4(), "")
    assert result is None


# ---------------------------------------------------------------------------
# 6.4 get_document_recipes
# ---------------------------------------------------------------------------

def test_get_document_recipes_returns_all():
    db = MagicMock()
    member_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    facts = [
        _make_recipe_fact(doc_id, "recipe_name", "דג חריף"),
        _make_recipe_fact(doc_id, "recipe_name", "בורקס גבינה"),
        _make_recipe_fact(doc_id, "recipe_name", "סלט ירקות"),
    ]

    db.query.return_value.join.return_value.filter.return_value.all.return_value = facts

    results = get_document_recipes(db, member_id, doc_id)
    assert len(results) == 3
    names = [r["recipe_name"] for r in results]
    assert "דג חריף" in names
    assert "בורקס גבינה" in names
    assert "סלט ירקות" in names


def test_get_document_recipes_empty():
    db = MagicMock()
    db.query.return_value.join.return_value.filter.return_value.all.return_value = []

    results = get_document_recipes(db, uuid.uuid4(), uuid.uuid4())
    assert results == []


# ---------------------------------------------------------------------------
# 6.5 answer_document_question recipe-aware path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_answer_recipe_list_question():
    """When asking about recipes on a recipe doc, return recipe names."""
    db = MagicMock()
    member = _make_member()
    doc = _make_doc(doc_type="recipe", display_name="ספר מתכונים של סבתא")

    recipe_facts = [
        _make_recipe_fact(doc.id, "recipe_name", "דג חריף"),
        _make_recipe_fact(doc.id, "recipe_name", "בורקס גבינה"),
    ]

    # Step 2 fact lookup returns no matching fact_key
    db.query.return_value.filter.return_value.all.side_effect = [
        [],             # step 2: no matching fact_key
        recipe_facts,   # step 2.5: recipe facts
    ]

    result = await answer_document_question(db, member, "איזה מתכונים יש?", doc)
    assert result.source == "document_fact"
    assert "2" in result.answer_text
    assert "דג חריף" in result.answer_text
    assert "בורקס גבינה" in result.answer_text


@pytest.mark.asyncio
async def test_answer_recipe_instructions_question():
    """When asking how to make something on a recipe doc, return instructions."""
    db = MagicMock()
    member = _make_member()
    doc = _make_doc(doc_type="recipe")

    recipe_facts = [
        _make_recipe_fact(doc.id, "recipe_name", "דג חריף"),
        _make_recipe_fact(doc.id, "instructions", "חממו תנור ל-200 מעלות"),
    ]

    db.query.return_value.filter.return_value.all.side_effect = [
        [],             # step 2
        recipe_facts,   # step 2.5
    ]

    result = await answer_document_question(db, member, "איך מכינים דג חריף?", doc)
    assert result.source == "document_fact"
    assert result.field_used == "instructions"
    assert "חממו תנור" in result.answer_text


@pytest.mark.asyncio
async def test_answer_recipe_not_found_on_recipe_doc():
    """When recipe doc has no recipe facts, return not found."""
    db = MagicMock()
    member = _make_member()
    doc = _make_doc(doc_type="recipe", raw_text="")

    db.query.return_value.filter.return_value.all.side_effect = [
        [],  # step 2
        [],  # step 2.5: no recipe facts
    ]

    result = await answer_document_question(db, member, "מתכון לדג?", doc)
    assert result.source == "not_found"
    assert "לא נמצאו מתכונים" in result.answer_text


@pytest.mark.asyncio
async def test_answer_non_recipe_question_unchanged():
    """Non-recipe questions on non-recipe docs should work as before."""
    db = MagicMock()
    member = _make_member()
    doc = _make_doc(doc_type="invoice", amount=Decimal("500.00"))

    result = await answer_document_question(db, member, "כמה עולה?", doc)
    assert result.source == "db_field"
    assert result.field_used == "amount"
