"""Fortress 2.0 intent detector — synchronous keyword-only classification."""

import logging
import re

logger = logging.getLogger(__name__)

INTENTS: dict[str, dict[str, str]] = {
    "list_tasks": {"model_tier": "local"},
    "create_task": {"model_tier": "local"},
    "complete_task": {"model_tier": "local"},
    "greeting": {"model_tier": "local"},
    "upload_document": {"model_tier": "local"},
    "list_documents": {"model_tier": "local"},
    "ask_question": {"model_tier": "local"},
    "unknown": {"model_tier": "local"},
    "delete_task": {"model_tier": "local"},
    "list_recurring": {"model_tier": "local"},
    "create_recurring": {"model_tier": "local"},
    "delete_recurring": {"model_tier": "local"},
    "report_bug": {"model_tier": "local"},
    "list_bugs": {"model_tier": "local"},
    "cancel_action": {"model_tier": "local"},
    "update_task": {"model_tier": "local"},
    "multi_intent": {"model_tier": "local"},
    "ambiguous": {"model_tier": "local"},
    "bulk_delete_tasks": {"model_tier": "local"},
    "bulk_delete_range": {"model_tier": "local"},
    "store_info": {"model_tier": "local"},
}

VALID_INTENTS: set[str] = set(INTENTS.keys())


def detect_intent(text: str, has_media: bool) -> str:
    """Classify a message into an intent category.

    Priority order:
    1. has_media → upload_document
    2. Keyword matching (Hebrew + English) with 4-tier priority
    3. No match → "needs_llm"
    """
    if has_media:
        logger.info("Intent: upload_document | method: media | msg: %s", text[:50])
        return "upload_document"

    keyword_intent = _match_keywords(text)
    if keyword_intent is not None:
        logger.info("Intent: %s | method: keyword | msg: %s", keyword_intent, text[:50])
        return keyword_intent

    logger.info("Intent: needs_llm | method: no_keyword | msg: %s", text[:50])
    return "needs_llm"


def _match_keywords(text: str) -> str | None:
    """Try to match the message against known keywords.

    Returns intent string or None (caller maps None → needs_llm).

    Priority tiers:
      0 — Cancel override: "אל " prefix, "לא" exact, cancel words
      1 — Exact phrases (including bulk patterns)
      2 — Action verbs (substring match)
      3 — Standalone keywords (exact match)
      4 — No match → return None (→ needs_llm)
    """
    stripped = text.strip()
    lower = stripped.lower()

    # ── Priority 0: Cancel override ──────────────────────────────
    if stripped.startswith("אל ") or stripped == "לא":
        return "cancel_action"
    cancel_words = {"עזוב", "תעזוב", "בטל", "תבטל", "cancel"}
    if stripped in cancel_words or lower in cancel_words:
        return "cancel_action"

    # ── Priority 1: Exact phrases ────────────────────────────────
    # Create task (prefix)
    if stripped.startswith("משימה חדשה:") or lower.startswith("new task:"):
        return "create_task"
    # Create recurring (prefix)
    if stripped.startswith("תזכורת חדשה:") or lower.startswith("recurring:"):
        return "create_recurring"
    # Delete task (substring — multi-word phrases)
    if "מחק משימה" in stripped or "הסר משימה" in stripped or "בטל משימה" in stripped:
        return "delete_task"
    # Delete recurring (substring — multi-word phrases)
    if "מחק תזכורת" in stripped or "בטל תזכורת" in stripped:
        return "delete_recurring"
    # Complete task (substring / prefix)
    if "סיום משימה" in stripped or lower.startswith("done"):
        return "complete_task"
    # Report bug (prefix)
    if stripped.startswith("באג:") or lower.startswith("bug:"):
        return "report_bug"
    # Bulk delete all
    if "מחק הכל" in stripped or "נקה הכל" in stripped or "delete all" in lower:
        return "bulk_delete_tasks"
    # Bulk delete range (regex)
    range_match = re.search(r"מחק\s+(\d+)\s*(?:[-–]|עד)\s*(\d+)", stripped)
    if range_match is None:
        range_match = re.search(r"delete\s+(\d+)\s*[-–to]\s*(\d+)", lower)
    if range_match:
        return "bulk_delete_range"

    # ── Priority 2: Action verbs (substring) ─────────────────────
    update_verbs = ("תשנה", "תעדכן", "עדכן", "שנה")
    if any(v in stripped for v in update_verbs) or "update" in lower:
        return "update_task"
    delete_verbs = ("תמחק", "תמחוק")
    if any(v in stripped for v in delete_verbs):
        return "delete_task"
    create_verbs = ("תיצור", "תוסיף", "הוסף")
    if any(v in stripped for v in create_verbs):
        return "create_task"
    complete_verbs = ("תסיים", "סיים", "בוצע")
    if any(v in stripped for v in complete_verbs):
        return "complete_task"

    # ── Priority 3: Standalone keywords (exact) ──────────────────
    if stripped in ("משימות", "מה המשימות") or lower == "tasks":
        return "list_tasks"
    if "מסמכים" in stripped or lower == "documents":
        return "list_documents"
    if "תזכורות" in stripped or "חוזרות" in stripped or lower == "recurring":
        return "list_recurring"
    if stripped in ("באגים", "רשימת באגים") or lower == "bugs":
        return "list_bugs"
    if stripped in ("שלום", "היי", "בוקר טוב") or lower in ("hello",):
        return "greeting"
    if stripped in ("באג",) or lower in ("bug",):
        return "report_bug"
    if stripped == "מחק" or "delete task" in lower:
        return "delete_task"

    # "משימה" singular → falls through to None (→ needs_llm)

    # ── Priority 4: No match ─────────────────────────────────────
    return None
