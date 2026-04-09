"""Browsing state manager for waterfall document browsing.

Stores browsing state in ConversationState.context['browse'] JSONB field.
No schema migration needed.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from src.services.conversation_state import get_state, update_state

logger = logging.getLogger(__name__)


@dataclass
class BrowsingState:
    level: str  # "categories" | "periods" | "detail"
    category: str | None = None
    period: str | None = None
    items: list[dict[str, Any]] = field(default_factory=list)


def get_browsing_state(db: Session, member_id: UUID) -> BrowsingState | None:
    """Read browsing state from ConversationState.context['browse']."""
    state = get_state(db, member_id)
    ctx = state.context or {}
    browse = ctx.get("browse")
    if not browse or not isinstance(browse, dict):
        return None
    return BrowsingState(
        level=browse.get("level", "categories"),
        category=browse.get("category"),
        period=browse.get("period"),
        items=browse.get("items") or [],
    )


def set_browsing_state(db: Session, member_id: UUID, bs: BrowsingState) -> None:
    """Write browsing state and set last_intent='document.browse'."""
    state = get_state(db, member_id)
    ctx = dict(state.context or {})
    ctx["browse"] = asdict(bs)
    update_state(db, member_id, intent="document.browse", context=ctx)


def clear_browsing_state(db: Session, member_id: UUID) -> None:
    """Remove browsing state from context."""
    state = get_state(db, member_id)
    ctx = dict(state.context or {})
    ctx.pop("browse", None)
    update_state(db, member_id, context=ctx)


def is_browsing(db: Session, member_id: UUID) -> bool:
    """Check if a browsing session is active."""
    state = get_state(db, member_id)
    ctx = state.context or {}
    return isinstance(ctx.get("browse"), dict) and bool(ctx["browse"].get("level"))


def handle_browse_input(db: Session, member_id: UUID, message: str) -> str | None:
    """Handle user input during an active browsing session.

    Returns a response string if the input was handled (numeric selection, back, etc.)
    Returns None if the message is unrelated — caller should clear state and dispatch normally.
    """
    from src.services.document_browse_queries import get_categories, get_periods, get_details
    from src.services.browse_formatter import (
        format_category_view, format_period_view, format_detail_view, format_error_range,
    )

    bs = get_browsing_state(db, member_id)
    if not bs:
        return None

    text = message.strip()

    # Back navigation
    if text in ("חזרה", "back", "אחורה"):
        if bs.level == "periods":
            # Go back to categories
            categories = get_categories(db, member_id)
            items = [{"key": c.doc_type, "label": c.label} for c in categories]
            set_browsing_state(db, member_id, BrowsingState(level="categories", items=items))
            return format_category_view(categories)
        elif bs.level in ("detail", "detail_select"):
            # Go back to periods
            if bs.category:
                periods = get_periods(db, member_id, bs.category)
                cat_label = bs.items[0].get("category_label", bs.category) if bs.items else bs.category
                # Find the category label
                categories = get_categories(db, member_id)
                cat_label = next((c.label for c in categories if c.doc_type == bs.category), bs.category)
                items = [{"key": p.period_key, "label": p.label, "category_label": cat_label} for p in periods]
                set_browsing_state(db, member_id, BrowsingState(level="periods", category=bs.category, items=items))
                return format_period_view(periods, cat_label)
        # Back from categories or unknown — clear
        clear_browsing_state(db, member_id)
        return None

    # Numeric selection
    if text.isdigit():
        idx = int(text) - 1
        if not bs.items or idx < 0 or idx >= len(bs.items):
            return format_error_range(len(bs.items) if bs.items else 0)

        selected = bs.items[idx]

        if bs.level == "categories":
            # Drill into periods for selected category
            doc_type = selected["key"]
            cat_label = selected["label"]
            periods = get_periods(db, member_id, doc_type)
            if not periods:
                return f"לא נמצאו מסמכים בקטגוריה {cat_label} 📂"
            items = [{"key": p.period_key, "label": p.label, "category_label": cat_label} for p in periods]
            set_browsing_state(db, member_id, BrowsingState(level="periods", category=doc_type, items=items))
            return format_period_view(periods, cat_label)

        elif bs.level == "periods":
            # Drill into details for selected period
            period_key = selected["key"]
            period_label = selected["label"]
            cat_label = selected.get("category_label", bs.category or "")
            details = get_details(db, member_id, bs.category or "", period_key)
            if not details:
                return f"לא נמצאו מסמכים ב{cat_label} עבור {period_label}"
            items = [{"key": str(d.document_id), "label": d.display_name, "category_label": cat_label, "period_label": period_label} for d in details]
            set_browsing_state(db, member_id, BrowsingState(level="detail", category=bs.category, period=period_key, items=items))
            return format_detail_view(details, cat_label, period_label)

        elif bs.level == "detail" and len(bs.items) > 1:
            # Multiple docs — user picked one
            detail = get_details(db, member_id, bs.category or "", bs.period or "")
            if idx < len(detail):
                from src.services.browse_formatter import _format_single_detail
                return _format_single_detail(detail[idx])

    # Text label match — check if the text matches any item label
    if bs.items:
        for i, item in enumerate(bs.items):
            if text == item.get("label", ""):
                # Simulate numeric selection
                return handle_browse_input(db, member_id, str(i + 1))

    # Unrelated message — return None to signal normal dispatch
    return None
