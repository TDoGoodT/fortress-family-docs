"""Fortress document summarizer — generates a short grounded Hebrew summary."""
from __future__ import annotations

import logging

from src.services.llm_dispatch import llm_generate

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "אתה עוזר משפחתי שמסכם מסמכים בצורה קצרה וברורה.\n"
    "כתוב 1-3 משפטים בעברית פשוטה ומעשית.\n"
    "השתמש רק במידע שמופיע בטקסט המסמך.\n"
    "אם אתה לא בטוח בפרט מסוים, ציין זאת.\n"
    "אל תמציא מידע שאינו בטקסט.\n"
    "החזר טקסט רגיל בלבד — ללא JSON, ללא markdown."
)


async def summarize_document(raw_text: str, doc_type: str, filename: str) -> str:
    """Generate a 1-3 sentence Hebrew summary of a document.

    Returns empty string if raw_text is empty or on any failure.
    """
    if not raw_text or not raw_text.strip():
        logger.info("summarizer: empty raw_text, skipping doc=%s", filename)
        return ""

    try:
        truncated = raw_text[:3000]
        prompt = (
            f"סכם את המסמך הבא ב-1 עד 3 משפטים.\n"
            f"סוג מסמך: {doc_type}\n"
            f"שם קובץ: {filename}\n\n"
            f"תוכן המסמך:\n{truncated}"
        )
        result = await llm_generate(prompt, _SYSTEM_PROMPT, "lite")

        if not result or not result.strip():
            logger.warning("summarizer: LLM returned empty doc=%s", filename)
            return ""

        summary = result.strip()
        logger.info("summarizer: success doc=%s summary_len=%d", filename, len(summary))
        return summary

    except Exception as exc:
        logger.error("summarizer: failed doc=%s error=%s: %s", filename, type(exc).__name__, exc)
        return ""
