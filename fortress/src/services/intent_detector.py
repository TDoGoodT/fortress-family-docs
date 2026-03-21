"""Fortress 2.0 intent detector — synchronous keyword-only classification."""

import logging

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
}

VALID_INTENTS: set[str] = set(INTENTS.keys())


def detect_intent(text: str, has_media: bool) -> str:
    """Classify a message into an intent category.

    Priority order:
    1. has_media → upload_document
    2. Keyword matching (Hebrew + English)
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
    """Try to match the message against known keywords. Returns intent or None."""
    stripped = text.strip()
    lower = stripped.lower()

    # List tasks
    if stripped in ("משימות", "מה המשימות") or lower == "tasks":
        return "list_tasks"

    # Create task (prefix match)
    if stripped.startswith("משימה חדשה:") or lower.startswith("new task:"):
        return "create_task"

    # Complete task
    if "סיום משימה" in stripped or lower.startswith("done") or "בוצע" in stripped:
        return "complete_task"

    # Greeting
    greetings_he = ("שלום", "היי", "בוקר טוב")
    greetings_en = ("hello",)
    if stripped in greetings_he or lower in greetings_en:
        return "greeting"

    # List documents
    if "מסמכים" in stripped or lower == "documents":
        return "list_documents"

    return None
