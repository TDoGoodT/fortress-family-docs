"""Tests for memory_service — category validation."""

import logging
import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from src.services.memory_service import (
    CATEGORY_MAP,
    VALID_CATEGORIES,
    save_memory,
)


def test_valid_categories_constant():
    """VALID_CATEGORIES contains exactly the five DB-allowed values."""
    assert VALID_CATEGORIES == {"preference", "goal", "fact", "habit", "context"}


def test_category_map_contains_task():
    """CATEGORY_MAP maps 'task' to 'context'."""
    assert "task" in CATEGORY_MAP
    assert CATEGORY_MAP["task"] == "context"


def test_category_map_known_entries():
    """CATEGORY_MAP maps all known invalid categories."""
    assert CATEGORY_MAP["reminder"] == "context"
    assert CATEGORY_MAP["note"] == "fact"
    assert CATEGORY_MAP["info"] == "fact"
    assert CATEGORY_MAP["memory"] == "fact"


@pytest.mark.asyncio
async def test_save_memory_valid_category_passthrough():
    """Valid category passes through unchanged."""
    db = MagicMock(spec=Session)
    db.query.return_value.filter.return_value.all.return_value = []

    mem = await save_memory(
        db, uuid.uuid4(), "likes coffee", "preference", "short",
    )
    # Memory was added to session
    db.add.assert_called_once()
    added = db.add.call_args[0][0]
    assert added.category == "preference"


@pytest.mark.asyncio
async def test_save_memory_mapped_category_task():
    """Category 'task' is mapped to 'context'."""
    db = MagicMock(spec=Session)
    db.query.return_value.filter.return_value.all.return_value = []

    mem = await save_memory(
        db, uuid.uuid4(), "buy milk", "task", "short",
    )
    db.add.assert_called_once()
    added = db.add.call_args[0][0]
    assert added.category == "context"


@pytest.mark.asyncio
async def test_save_memory_mapped_category_reminder():
    """Category 'reminder' is mapped to 'context'."""
    db = MagicMock(spec=Session)
    db.query.return_value.filter.return_value.all.return_value = []

    mem = await save_memory(
        db, uuid.uuid4(), "dentist appointment", "reminder", "short",
    )
    db.add.assert_called_once()
    added = db.add.call_args[0][0]
    assert added.category == "context"


@pytest.mark.asyncio
async def test_save_memory_unknown_category_defaults_context(caplog):
    """Unknown category defaults to 'context' with warning."""
    db = MagicMock(spec=Session)
    db.query.return_value.filter.return_value.all.return_value = []

    with caplog.at_level(logging.WARNING):
        mem = await save_memory(
            db, uuid.uuid4(), "something", "banana", "short",
        )
    db.add.assert_called_once()
    added = db.add.call_args[0][0]
    assert added.category == "context"
    assert "Invalid memory category 'banana'" in caplog.text
