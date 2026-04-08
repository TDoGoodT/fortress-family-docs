"""Fortress document classifier — keyword-based + LLM fallback classification."""
from __future__ import annotations

import json
import logging
import re

from src.services.llm_dispatch import llm_generate

logger = logging.getLogger(__name__)

# Shared constants — reused across classifier, fact extractor, query service, and tests
SUPPORTED_CATEGORIES: list[str] = [
    "contract",
    "invoice",
    "receipt",
    "salary_slip",
    "bank_statement",
    "credit_card_statement",
    "insurance",
    "warranty",
    "official_letter",
    "recipe",
    "other",
]

ALLOWED_FACT_KEYS: list[str] = [
    "source_date",
    "counterparty",
    "amount",
    "currency",
    "document_reference",
    "period_start",
    "period_end",
    "policy_number",
    "contract_end_date",
    "recipe_name",
    "ingredients",
    "instructions",
    "servings",
    "prep_time",
]

MAX_SOURCE_EXCERPT_LENGTH: int = 250
REVIEW_CONFIDENCE_THRESHOLD: float = 0.5

# Keyword rules: (category, [patterns]) — checked against filename + raw_text (lowercased)
_KEYWORD_RULES: list[tuple[str, list[str]]] = [
    ("invoice", ["invoice", "חשבונית", "tax invoice", "vat invoice"]),
    ("receipt", ["receipt", "קבלה", "קבלה על תשלום"]),
    ("salary_slip", ["תלוש שכר", "תלוש משכורת", "ברוטו", "נטו", "מס הכנסה", "salary slip", "payslip", "pay stub"]),
    ("contract", ["contract", "חוזה", "הסכם", "agreement", "עסקה"]),
    ("bank_statement", ["bank statement", "דף חשבון", "account statement", "תנועות בחשבון"]),
    ("credit_card_statement", ["credit card", "כרטיס אשראי", "card statement", "חיובי כרטיס"]),
    ("insurance", ["insurance", "ביטוח", "פוליסה", "policy", "insured"]),
    ("warranty", ["warranty", "אחריות", "guarantee", "תעודת אחריות"]),
    ("official_letter", ["official", "רשמי", "עירייה", "משרד", "municipality", "government", "ministry"]),
    ("recipe", ["מתכון", "מצרכים", "אופן הכנה", "הוראות הכנה", "recipe", "ingredients", "instructions", "כוסות", "כפות", "גרם"]),
]

_SPREADSHEET_EXTENSIONS = {".xls", ".xlsx"}


def _classify_by_keywords(text: str, filename: str) -> tuple[str, float]:
    """Phase 1: deterministic keyword matching. Returns (category, confidence)."""
    import os
    _, ext = os.path.splitext(filename)
    haystack = (filename + " " + text).lower()

    for category, keywords in _KEYWORD_RULES:
        for kw in keywords:
            if kw.lower() in haystack:
                return category, 0.8

    return "other", 0.0


async def classify_document(raw_text: str, filename: str) -> tuple[str, float]:
    """Classify a document into one of SUPPORTED_CATEGORIES.

    Phase 1: deterministic keyword/filename rules (fast, no LLM).
    Phase 2: LLM fallback (Bedrock micro) if Phase 1 confidence < 0.6.
    Returns ("other", 0.0) on any error.
    """
    import os
    _, ext = os.path.splitext(filename)

    # XLS/XLSX: filename-only, no text analysis
    text_for_classification = "" if ext.lower() in _SPREADSHEET_EXTENSIONS else raw_text

    try:
        category, confidence = _classify_by_keywords(text_for_classification, filename)
        if confidence >= 0.6:
            logger.info(
                "classifier: phase1 doc=%s category=%s confidence=%.2f",
                filename, category, confidence,
            )
            return category, confidence

        # Phase 2: LLM fallback (skip for spreadsheets)
        if ext.lower() in _SPREADSHEET_EXTENSIONS:
            logger.info("classifier: spreadsheet filename-only, defaulting to other doc=%s", filename)
            return "other", 0.3

        prompt = (
            f"Classify this document into exactly one category.\n"
            f"Categories: {', '.join(SUPPORTED_CATEGORIES)}\n\n"
            f"Filename: {filename}\n"
            f"Text (first 500 chars): {raw_text[:500]}\n\n"
            f"Respond with JSON only: {{\"category\": \"<category>\", \"confidence\": <0.0-1.0>}}"
        )
        system = "You are a document classifier. Respond only with valid JSON."
        raw = await llm_generate(prompt, system, "micro")

        if not raw:
            logger.warning("classifier: LLM returned empty, defaulting to other doc=%s", filename)
            return "other", 0.0

        # Extract JSON from response
        match = re.search(r'\{[^}]+\}', raw)
        if not match:
            return "other", 0.0

        data = json.loads(match.group())
        llm_category = data.get("category", "other")
        llm_confidence = float(data.get("confidence", 0.0))

        if llm_category not in SUPPORTED_CATEGORIES:
            llm_category = "other"
            llm_confidence = 0.0

        logger.info(
            "classifier: phase2 doc=%s category=%s confidence=%.2f",
            filename, llm_category, llm_confidence,
        )
        return llm_category, llm_confidence

    except Exception as exc:
        logger.error("classifier: failed doc=%s error=%s: %s", filename, type(exc).__name__, exc)
        return "other", 0.0
