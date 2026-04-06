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
    "recipe": ["recipe_name", "ingredients", "instructions", "servings", "prep_time"],
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


async def _extract_recipe_facts(raw_text: str, filename: str) -> list[dict[str, Any]]:
    """Extract structured recipe facts from raw_text using LLM.

    Handles both single-recipe and multi-recipe documents.
    Returns list of fact dicts with fact_type="recipe".
    Each recipe produces: recipe_name, ingredients, instructions,
    and optionally servings and prep_time.
    For multi-recipe docs, source_excerpt contains the recipe name
    to associate related facts.
    """
    try:
        truncated_text = raw_text[:4000]
        prompt = (
            "Extract all recipes from this document.\n"
            "For each recipe, return a JSON object with these fields:\n"
            '  - "recipe_name": the name/title of the recipe (required)\n'
            '  - "ingredients": the full ingredients list as text (required)\n'
            '  - "instructions": the preparation steps as text (required)\n'
            '  - "servings": number of servings if mentioned (optional, omit if not found)\n'
            '  - "prep_time": preparation time if mentioned (optional, omit if not found)\n\n'
            "Respond with a JSON array of recipe objects only.\n"
            "If there is one recipe, return an array with one object.\n"
            "If there are multiple recipes, return an array with one object per recipe.\n\n"
            f"Document text:\n{truncated_text}"
        )
        system = "You are a recipe extractor. Respond only with a valid JSON array of recipe objects."
        raw = await llm_generate(prompt, system, "lite")

        if not raw:
            logger.warning("fact_extractor: recipe LLM returned empty doc=%s", filename)
            return []

        # Extract JSON array from response
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if not match:
            logger.warning("fact_extractor: recipe LLM no JSON array found doc=%s", filename)
            return []

        recipes = json.loads(match.group())
        if not isinstance(recipes, list) or not recipes:
            logger.warning("fact_extractor: recipe LLM returned empty/invalid array doc=%s", filename)
            return []

        facts: list[dict[str, Any]] = []
        is_multi = len(recipes) > 1

        for recipe in recipes:
            try:
                recipe_name = str(recipe.get("recipe_name", "")).strip()
                if not recipe_name:
                    continue

                excerpt = _truncate_excerpt(recipe_name) if is_multi else ""

                # Required fields
                facts.append({
                    "fact_type": "recipe",
                    "fact_key": "recipe_name",
                    "fact_value": recipe_name,
                    "confidence": 0.7,
                    "source_excerpt": excerpt,
                })

                ingredients = str(recipe.get("ingredients", "")).strip()
                if ingredients:
                    facts.append({
                        "fact_type": "recipe",
                        "fact_key": "ingredients",
                        "fact_value": ingredients,
                        "confidence": 0.7,
                        "source_excerpt": excerpt,
                    })

                instructions = str(recipe.get("instructions", "")).strip()
                if instructions:
                    facts.append({
                        "fact_type": "recipe",
                        "fact_key": "instructions",
                        "fact_value": instructions,
                        "confidence": 0.7,
                        "source_excerpt": excerpt,
                    })

                # Optional fields
                servings = str(recipe.get("servings", "")).strip()
                if servings:
                    facts.append({
                        "fact_type": "recipe",
                        "fact_key": "servings",
                        "fact_value": servings,
                        "confidence": 0.6,
                        "source_excerpt": excerpt,
                    })

                prep_time = str(recipe.get("prep_time", "")).strip()
                if prep_time:
                    facts.append({
                        "fact_type": "recipe",
                        "fact_key": "prep_time",
                        "fact_value": prep_time,
                        "confidence": 0.6,
                        "source_excerpt": excerpt,
                    })
            except Exception as exc:
                logger.warning(
                    "fact_extractor: recipe partial failure doc=%s recipe=%s error=%s: %s",
                    filename, recipe.get("recipe_name", "unknown"), type(exc).__name__, exc,
                )
                continue

        if is_multi:
            recipe_count = sum(1 for f in facts if f["fact_key"] == "recipe_name")
            logger.info("fact_extractor: multi-recipe doc=%s recipes_extracted=%d", filename, recipe_count)

        return facts

    except Exception as exc:
        logger.error("fact_extractor: recipe extraction failed doc=%s error=%s: %s", filename, type(exc).__name__, exc)
        return []


# ── Fact key descriptions for schema prompt ─────────────────────────────
_FACT_KEY_DESCRIPTIONS: dict[str, str] = {
    "source_date": "The primary date of the document (issue date, transaction date, statement date)",
    "counterparty": "The other party — company name, vendor, service provider, or sender",
    "amount": "The total monetary amount (e.g. '1,234.56' or '1234')",
    "currency": "The currency code (ILS, USD, EUR) or symbol (₪, $, €)",
    "document_reference": "Reference number, invoice number, or document ID",
    "period_start": "Start date of a covered period (for statements, policies)",
    "period_end": "End date of a covered period (for statements, policies, warranties)",
    "policy_number": "Insurance policy number or identifier",
    "contract_end_date": "Expiration or end date of a contract",
}

# ── Schema prompt examples per category ──────────────────────────────────
_CATEGORY_EXAMPLES: dict[str, str] = {
    "invoice": '[{"fact_key": "source_date", "fact_value": "2024-03-15", "confidence": 0.9, "source_excerpt": "Invoice Date: 15/03/2024"}, {"fact_key": "counterparty", "fact_value": "Bezeq", "confidence": 0.85, "source_excerpt": "From: Bezeq International"}, {"fact_key": "amount", "fact_value": "1234.56", "confidence": 0.9, "source_excerpt": "Total: ₪1,234.56"}]',
    "receipt": '[{"fact_key": "source_date", "fact_value": "2024-01-10", "confidence": 0.9, "source_excerpt": "Date: 10/01/2024"}, {"fact_key": "counterparty", "fact_value": "Super-Pharm", "confidence": 0.85, "source_excerpt": "Super-Pharm Ltd"}, {"fact_key": "amount", "fact_value": "89.90", "confidence": 0.9, "source_excerpt": "Total: ₪89.90"}]',
    "contract": '[{"fact_key": "source_date", "fact_value": "2024-06-01", "confidence": 0.9, "source_excerpt": "Dated: 01/06/2024"}, {"fact_key": "counterparty", "fact_value": "Partner Communications", "confidence": 0.85, "source_excerpt": "Between: Partner Communications"}]',
    "bank_statement": '[{"fact_key": "source_date", "fact_value": "2024-02-28", "confidence": 0.9, "source_excerpt": "Statement Date: 28/02/2024"}, {"fact_key": "counterparty", "fact_value": "Bank Leumi", "confidence": 0.85, "source_excerpt": "Bank Leumi Le-Israel"}]',
}


def _build_schema_prompt(
    raw_text: str,
    doc_type: str,
    target_keys: list[str],
    filename: str,
) -> str:
    """Build a structured extraction prompt for the given doc_type.

    Includes document type context, target fact key descriptions,
    expected JSON output format, one example per category, and
    up to 3000 chars of raw text.
    """
    key_descriptions = "\n".join(
        f"  - {k}: {_FACT_KEY_DESCRIPTIONS.get(k, k)}"
        for k in target_keys
    )

    example = _CATEGORY_EXAMPLES.get(doc_type, _CATEGORY_EXAMPLES.get("invoice", "[]"))

    truncated_text = raw_text[:3000]

    prompt = (
        f"You are extracting structured facts from a {doc_type} document.\n"
        f"Filename: {filename}\n\n"
        f"Target fact keys to extract:\n{key_descriptions}\n\n"
        f"Respond with a JSON array only. Each item must have exactly these fields:\n"
        f'  {{"fact_key": "<key>", "fact_value": "<value>", '
        f'"confidence": <0.0-1.0>, "source_excerpt": "<short quote from text>"}}\n\n'
        f"Rules:\n"
        f"- Only include facts you can actually find in the text\n"
        f"- Only use these allowed keys: {', '.join(target_keys)}\n"
        f"- confidence should reflect how certain you are (0.0 = guess, 1.0 = exact match)\n"
        f"- source_excerpt should be a short quote from the document supporting the fact\n\n"
        f"Example output for a {doc_type} document:\n{example}\n\n"
        f"Document text:\n{truncated_text}"
    )
    return prompt


async def extract_facts(
    raw_text: str,
    doc_type: str,
    filename: str,
    text_quality: float = 1.0,
) -> list[dict[str, Any]]:
    """Extract structured facts from raw_text.

    Phase 1: regex-based extraction for dates and amounts.
    Phase 2: schema-driven LLM extraction (haiku tier) for remaining target keys.

    If text_quality < 0.3, skip LLM extraction entirely and return regex facts only.
    Recipe extraction unchanged (lite tier).

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

    # Quality gate: skip LLM if text quality is too low
    if text_quality < 0.3:
        logger.info(
            "fact_extractor: skipping LLM extraction doc=%s text_quality=%.2f reason=below_threshold",
            filename, text_quality,
        )
        logger.info("fact_extractor: doc=%s doc_type=%s facts_count=%d", filename, doc_type, len(facts))
        return facts

    # Phase 2: LLM for remaining target keys
    if doc_type == "recipe":
        # Recipe-specific extraction replaces generic Phase 2 — stays on lite tier
        try:
            recipe_facts = await _extract_recipe_facts(raw_text, filename)
            facts.extend(recipe_facts)
            logger.info("fact_extractor: model_tier=lite doc=%s doc_type=recipe", filename)
        except Exception as exc:
            logger.warning("fact_extractor: recipe phase2 failed doc=%s error=%s: %s", filename, type(exc).__name__, exc)
    else:
        target_keys = _CATEGORY_FACT_KEYS.get(doc_type, _CATEGORY_FACT_KEYS["other"])
        remaining_keys = [k for k in target_keys if k not in extracted_keys]

        if remaining_keys:
            try:
                prompt = _build_schema_prompt(raw_text, doc_type, remaining_keys, filename)
                system = "You are a document fact extractor. Respond only with a valid JSON array."
                raw = await llm_generate(prompt, system, "haiku")

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
                logger.info("fact_extractor: model_tier=haiku doc=%s doc_type=%s", filename, doc_type)
            except Exception as exc:
                logger.warning("fact_extractor: phase2 failed doc=%s error=%s: %s", filename, type(exc).__name__, exc)

    logger.info("fact_extractor: doc=%s doc_type=%s facts_count=%d", filename, doc_type, len(facts))
    return facts
