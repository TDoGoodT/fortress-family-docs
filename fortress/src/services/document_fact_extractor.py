"""Fortress document fact extractor — regex + LLM-assisted structured fact extraction."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from src.services.document_classifier import ALLOWED_FACT_KEYS, MAX_SOURCE_EXCERPT_LENGTH
from src.services.llm_dispatch import llm_generate

logger = logging.getLogger(__name__)

# Regex patterns for Phase 1 deterministic extraction
_DATE_PATTERNS = [
    re.compile(r'\b(\d{1,2}[./]\d{1,2}[./]\d{2,4})\b'),          # DD/MM/YYYY or DD.MM.YYYY
    re.compile(r'\b(\d{4}-\d{2}-\d{2})\b'),                        # YYYY-MM-DD
    re.compile(r'\b(\d{1,2}\s+(?:ינואר|פברואר|מרץ|אפריל|מאי|יוני|יולי|אוגוסט|ספטמבר|אוקטובר|נובמבר|דצמבר)\s+\d{4})\b'),
]

_AMOUNT_PATTERN = re.compile(
    r'(?:NIS|ILS|₪|\$|€|USD|EUR)\s*([\d,]+(?:\.\d{1,2})?)'
    r'|'
    r'([\d,]+(?:\.\d{1,2})?)\s*(?:NIS|ILS|₪|\$|€|USD|EUR|ש"ח|שקל)',
    re.IGNORECASE,
)

_CURRENCY_MAP = {
    "₪": "ILS", "ש\"ח": "ILS", "שקל": "ILS", "NIS": "ILS", "ILS": "ILS",
    "$": "USD", "USD": "USD",
    "€": "EUR", "EUR": "EUR",
}

# Fact keys relevant per document category
_CATEGORY_FACT_KEYS: dict[str, list[str]] = {
    "invoice": ["source_date", "counterparty", "amount", "currency", "document_reference"],
    "receipt": ["source_date", "counterparty", "amount", "currency"],
    "contract": ["source_date", "counterparty", "contract_end_date", "document_reference"],
    "bank_statement": ["source_date", "counterparty", "period_start", "period_end"],
    "credit_card_statement": ["source_date", "counterparty", "amount", "currency", "period_start", "period_end"],
    "insurance": ["source_date", "counterparty", "policy_number", "period_start", "period_end"],
    "warranty": ["source_date", "counterparty", "period_end"],
    "official_letter": ["source_date", "counterparty", "document_reference"],
    "other": ["source_date", "counterparty", "amount", "currency"],
}


def _truncate_excerpt(text: str) -> str:
    return text[:MAX_SOURCE_EXCERPT_LENGTH]


def _extract_dates_regex(text: str) -> list[dict[str, Any]]:
    facts = []
    for pattern in _DATE_PATTERNS:
        for m in pattern.finditer(text):
            start = max(0, m.start() - 30)
            end = min(len(text), m.end() + 30)
            facts.append({
                "fact_key": "source_date",
                "fact_value": m.group(1) if m.lastindex else m.group(),
                "confidence": 0.75,
                "source_excerpt": _truncate_excerpt(text[start:end].strip()),
            })
            break  # take first date only
    return facts[:1]


def _extract_amounts_regex(text: str) -> list[dict[str, Any]]:
    facts = []
    for m in _AMOUNT_PATTERN.finditer(text):
        amount_str = (m.group(1) or m.group(2) or "").replace(",", "")
        if not amount_str:
            continue
        # Detect currency from surrounding context
        context = text[max(0, m.start()-5):m.end()+5]
        currency = "ILS"
        for symbol, code in _CURRENCY_MAP.items():
            if symbol in context:
                currency = code
                break

        start = max(0, m.start() - 20)
        end = min(len(text), m.end() + 20)
        facts.append({
            "fact_key": "amount",
            "fact_value": amount_str,
            "confidence": 0.8,
            "source_excerpt": _truncate_excerpt(text[start:end].strip()),
        })
        facts.append({
            "fact_key": "currency",
            "fact_value": currency,
            "confidence": 0.8,
            "source_excerpt": _truncate_excerpt(text[start:end].strip()),
        })
        break  # take first amount only
    return facts


async def extract_facts(raw_text: str, doc_type: str, filename: str) -> list[dict[str, Any]]:
    """Extract structured facts from raw_text.

    Phase 1: regex-based extraction for dates and amounts.
    Phase 2: LLM-assisted extraction for remaining target keys.
    Returns list of fact dicts with fact_type, fact_key, fact_value, confidence, source_excerpt.
    Returns empty list on total failure.
    """
    if not raw_text or not raw_text.strip():
        return []

    facts: list[dict[str, Any]] = []
    extracted_keys: set[str] = set()

    # Phase 1: regex
    try:
        date_facts = _extract_dates_regex(raw_text)
        for f in date_facts:
            f["fact_type"] = doc_type
            facts.append(f)
            extracted_keys.add(f["fact_key"])

        amount_facts = _extract_amounts_regex(raw_text)
        for f in amount_facts:
            f["fact_type"] = doc_type
            facts.append(f)
            extracted_keys.add(f["fact_key"])
    except Exception as exc:
        logger.warning("fact_extractor: phase1 failed doc=%s error=%s: %s", filename, type(exc).__name__, exc)

    # Phase 2: LLM for remaining target keys
    target_keys = _CATEGORY_FACT_KEYS.get(doc_type, _CATEGORY_FACT_KEYS["other"])
    remaining_keys = [k for k in target_keys if k not in extracted_keys]

    if remaining_keys:
        try:
            truncated_text = raw_text[:2000]
            prompt = (
                f"Extract the following facts from this document.\n"
                f"Facts to extract: {', '.join(remaining_keys)}\n"
                f"Document type: {doc_type}\n"
                f"Filename: {filename}\n\n"
                f"Document text:\n{truncated_text}\n\n"
                f"Respond with a JSON array only. Each item: "
                f'{{\"fact_key\": \"<key>\", \"fact_value\": \"<value>\", '
                f'\"confidence\": <0.0-1.0>, \"source_excerpt\": \"<short quote>\"}}\n'
                f"Only include facts you can find in the text. Allowed keys: {', '.join(ALLOWED_FACT_KEYS)}"
            )
            system = "You are a document fact extractor. Respond only with a valid JSON array."
            raw = await llm_generate(prompt, system, "lite")

            if raw:
                # Extract JSON array from response
                match = re.search(r'\[.*\]', raw, re.DOTALL)
                if match:
                    items = json.loads(match.group())
                    for item in items:
                        key = item.get("fact_key", "")
                        value = str(item.get("fact_value", "")).strip()
                        if key not in ALLOWED_FACT_KEYS or not value:
                            continue
                        if key in extracted_keys:
                            continue
                        facts.append({
                            "fact_type": doc_type,
                            "fact_key": key,
                            "fact_value": value,
                            "confidence": float(item.get("confidence", 0.5)),
                            "source_excerpt": _truncate_excerpt(str(item.get("source_excerpt", ""))),
                        })
                        extracted_keys.add(key)
        except Exception as exc:
            logger.warning("fact_extractor: phase2 failed doc=%s error=%s: %s", filename, type(exc).__name__, exc)

    logger.info("fact_extractor: doc=%s doc_type=%s facts_count=%d", filename, doc_type, len(facts))
    return facts
