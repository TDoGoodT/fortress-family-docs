"""Fortress document namer — deterministic Hebrew display name generation.

Generates human-readable Hebrew titles for documents using structured metadata.
Deterministic-first: pure template assembly from doc_type, vendor, doc_date.
Optional LLM micro-tier refinement for naturalness when ai_summary is available.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)

# Hebrew labels for each supported document category
DOC_TYPE_LABEL_MAP: dict[str, str] = {
    "contract": "חוזה",
    "invoice": "חשבונית",
    "receipt": "קבלה",
    "bank_statement": "דף חשבון",
    "credit_card_statement": "כרטיס אשראי",
    "insurance": "ביטוח",
    "warranty": "אחריות",
    "official_letter": "מכתב רשמי",
    "recipe": "מתכון",
    "other": "מסמך",
}

# Hebrew month names (transliterated Gregorian months)
HEBREW_MONTHS: dict[int, str] = {
    1: "ינואר",
    2: "פברואר",
    3: "מרץ",
    4: "אפריל",
    5: "מאי",
    6: "יוני",
    7: "יולי",
    8: "אוגוסט",
    9: "ספטמבר",
    10: "אוקטובר",
    11: "נובמבר",
    12: "דצמבר",
}

_LLM_MAX_LENGTH = 60


def generate_display_name(
    doc_type: Optional[str],
    vendor: Optional[str],
    doc_date: Optional[date],
    ai_summary: Optional[str] = None,
    use_llm: bool = True,
) -> str:
    """Generate a human-readable Hebrew display name for a document.

    Deterministic template assembly, with optional LLM refinement.
    Always returns a non-empty string.

    Args:
        doc_type: Document category (from SUPPORTED_CATEGORIES) or None.
        vendor: Vendor/counterparty name, or None.
        doc_date: Document date, or None.
        ai_summary: AI-generated summary for LLM refinement context.
        use_llm: If True and ai_summary is available, attempt LLM refinement.

    Returns:
        A non-empty Hebrew display name string.
    """
    deterministic = _build_deterministic_name(doc_type, vendor, doc_date)

    if use_llm and ai_summary:
        try:
            refined = _run_llm_refinement(deterministic, ai_summary)
            if refined and refined.strip():
                return refined.strip()
        except Exception as exc:
            logger.warning(
                "document_namer: LLM refinement failed, using deterministic name: %s: %s",
                type(exc).__name__, exc,
            )

    return deterministic


def _build_deterministic_name(
    doc_type: Optional[str],
    vendor: Optional[str],
    doc_date: Optional[date],
) -> str:
    """Build a deterministic display name from structured fields.

    Template rules:
      - doc_type + vendor + doc_date → "{label} {vendor} {month} {year}"
      - doc_type + doc_date (no vendor) → "{label} {month} {year}"
      - doc_type + vendor (no date) → "{label} {vendor}"
      - doc_type only → "{label}"
      - other/missing + doc_date → "מסמך {YYYY-MM-DD}"
      - other/missing, no date → "מסמך"
    """
    is_other = doc_type is None or doc_type == "other" or doc_type not in DOC_TYPE_LABEL_MAP

    if is_other:
        if doc_date is not None:
            return f"מסמך {doc_date.isoformat()}"
        return "מסמך"

    label = DOC_TYPE_LABEL_MAP[doc_type]
    has_vendor = vendor is not None and vendor.strip() != ""
    has_date = doc_date is not None

    if has_vendor and has_date:
        month_name = HEBREW_MONTHS[doc_date.month]
        return f"{label} {vendor} {month_name} {doc_date.year}"
    elif has_date:
        month_name = HEBREW_MONTHS[doc_date.month]
        return f"{label} {month_name} {doc_date.year}"
    elif has_vendor:
        return f"{label} {vendor}"
    else:
        return label


def _run_llm_refinement(deterministic_name: str, ai_summary: str) -> str:
    """Run async LLM refinement from sync context using a fresh event loop in a thread."""
    import threading

    result_holder: list[str] = []
    exc_holder: list[Exception] = []

    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                _refine_with_llm(deterministic_name, ai_summary)
            )
            result_holder.append(result)
        except Exception as e:
            exc_holder.append(e)
        finally:
            loop.close()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=30)

    if exc_holder:
        raise exc_holder[0]
    if result_holder:
        return result_holder[0]
    return deterministic_name


async def _refine_with_llm(deterministic_name: str, ai_summary: str) -> str:
    """Refine a deterministic name using LLM micro-tier.

    Returns the deterministic_name unchanged on any failure.
    Truncates LLM output to 60 characters.
    """
    try:
        from src.services.llm_dispatch import llm_generate

        system_prompt = (
            "אתה עוזר שנותן כותרות קצרות למסמכים בעברית. "
            "החזר רק את כותרת המסמך, בלי JSON, בלי markdown, בלי הסברים."
        )
        prompt = (
            f"הכותרת הנוכחית: {deterministic_name}\n"
            f"תקציר המסמך: {ai_summary}\n\n"
            f"החזר כותרת קצרה ומתאימה בעברית בלבד."
        )

        result = await llm_generate(prompt, system_prompt, "micro")

        if not result or not result.strip():
            return deterministic_name

        refined = result.strip()
        if len(refined) > _LLM_MAX_LENGTH:
            refined = refined[:_LLM_MAX_LENGTH]

        return refined

    except Exception as exc:
        logger.warning(
            "document_namer: _refine_with_llm failed: %s: %s",
            type(exc).__name__, exc,
        )
        return deterministic_name
