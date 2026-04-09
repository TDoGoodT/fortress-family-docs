"""Fortress document fact extractor — regex + LLM-assisted structured fact extraction."""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from src.services.document_classifier import ALLOWED_FACT_KEYS, MAX_SOURCE_EXCERPT_LENGTH
from src.services.llm_dispatch import llm_generate
from src.services.vision_extractor import extract_structured_with_vision

logger = logging.getLogger(__name__)

_SALARY_SLIP_STRUCTURED_KEYS = {
    "employee_name": None,
    "employer_name": None,
    "pay_month": None,
    "gross_salary": None,
    "net_salary": None,
    "net_to_pay": None,
    "total_deductions": None,
    "income_tax": None,
    "national_insurance": None,
    "health_tax": None,
    "pension_employee": None,
    "pension_employer": None,
    "confidence": 0.0,
}

_SALARY_SLIP_CRITICAL_KEYS = {"pay_month", "gross_salary", "net_salary"}

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
    "electricity_bill": ["source_date", "counterparty", "amount", "currency", "document_reference", "period_start", "period_end"],
    "water_bill": ["source_date", "counterparty", "amount", "currency", "document_reference", "period_start", "period_end"],
    "invoice": ["source_date", "counterparty", "amount", "currency", "document_reference"],
    "receipt": ["source_date", "counterparty", "amount", "currency"],
    "contract": [
        "source_date", "counterparty", "contract_end_date", "document_reference",
        "contract_type", "parties", "obligations", "renewal_terms",
        "penalty_clause", "governing_law", "termination_clause",
        "amount", "currency", "period_start", "period_end",
    ],
    "bank_statement": ["source_date", "counterparty", "period_start", "period_end"],
    "credit_card_statement": ["source_date", "counterparty", "amount", "currency", "period_start", "period_end"],
    "insurance": [
        "source_date", "counterparty", "policy_number", "period_start", "period_end",
        "insurance_type", "coverage_description", "premium_amount", "deductible_amount",
        "insured_name", "beneficiary", "coverage_limit", "amount", "currency",
    ],
    "warranty": ["source_date", "counterparty", "period_end"],
    "official_letter": ["source_date", "counterparty", "document_reference"],
    "other": ["source_date", "counterparty", "amount", "currency"],
    "recipe": ["recipe_name", "ingredients", "instructions", "servings", "prep_time"],
    "salary_slip": ["source_date", "counterparty", "amount", "currency"],
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
    # Contract-specific
    "contract_type": "Type of contract (rental, employment, service, purchase, etc.)",
    "parties": "All named parties to the contract, comma-separated",
    "obligations": "Key obligations or deliverables described in the contract",
    "renewal_terms": "Auto-renewal or renewal conditions (e.g. 'auto-renews annually')",
    "penalty_clause": "Penalties for breach or early termination",
    "governing_law": "Jurisdiction or governing law (e.g. 'Israeli law')",
    "termination_clause": "Conditions under which the contract can be terminated",
    # Insurance-specific
    "insurance_type": "Type of insurance (health, car, home, life, travel, etc.)",
    "coverage_description": "What the policy covers — summary of covered events/items",
    "premium_amount": "The periodic premium payment amount",
    "deductible_amount": "The deductible (self-participation) amount",
    "insured_name": "Name of the insured person or entity",
    "beneficiary": "Named beneficiary of the policy",
    "coverage_limit": "Maximum coverage amount or limit",
}

# ── Schema prompt examples per category ──────────────────────────────────
_CATEGORY_EXAMPLES: dict[str, str] = {
    "electricity_bill": '[{"fact_key": "source_date", "fact_value": "2026-03-01", "confidence": 0.92, "source_excerpt": "תאריך עריכת החשבון: 01/03/2026"}, {"fact_key": "counterparty", "fact_value": "אלקטרה פאוור", "confidence": 0.9, "source_excerpt": "מספר צרכן אלקטרה פאוור"}, {"fact_key": "amount", "fact_value": "208.37", "confidence": 0.88, "source_excerpt": "סכום ב-₪ 208.37"}, {"fact_key": "document_reference", "fact_value": "55940425", "confidence": 0.93, "source_excerpt": "חשבונית מס/קבלה (מקור) 55940425"}]',
    "invoice": '[{"fact_key": "source_date", "fact_value": "2024-03-15", "confidence": 0.9, "source_excerpt": "Invoice Date: 15/03/2024"}, {"fact_key": "counterparty", "fact_value": "Bezeq", "confidence": 0.85, "source_excerpt": "From: Bezeq International"}, {"fact_key": "amount", "fact_value": "1234.56", "confidence": 0.9, "source_excerpt": "Total: ₪1,234.56"}]',
    "receipt": '[{"fact_key": "source_date", "fact_value": "2024-01-10", "confidence": 0.9, "source_excerpt": "Date: 10/01/2024"}, {"fact_key": "counterparty", "fact_value": "Super-Pharm", "confidence": 0.85, "source_excerpt": "Super-Pharm Ltd"}, {"fact_key": "amount", "fact_value": "89.90", "confidence": 0.9, "source_excerpt": "Total: ₪89.90"}]',
    "contract": '[{"fact_key": "source_date", "fact_value": "2024-06-01", "confidence": 0.9, "source_excerpt": "Dated: 01/06/2024"}, {"fact_key": "counterparty", "fact_value": "Partner Communications", "confidence": 0.85, "source_excerpt": "Between: Partner Communications"}, {"fact_key": "contract_type", "fact_value": "service", "confidence": 0.8, "source_excerpt": "הסכם למתן שירותי תקשורת"}, {"fact_key": "parties", "fact_value": "Partner Communications, ישראל ישראלי", "confidence": 0.85, "source_excerpt": "בין: פרטנר תקשורת לבין: ישראל ישראלי"}, {"fact_key": "contract_end_date", "fact_value": "2026-06-01", "confidence": 0.8, "source_excerpt": "תוקף ההסכם: 24 חודשים"}]',
    "bank_statement": '[{"fact_key": "source_date", "fact_value": "2024-02-28", "confidence": 0.9, "source_excerpt": "Statement Date: 28/02/2024"}, {"fact_key": "counterparty", "fact_value": "Bank Leumi", "confidence": 0.85, "source_excerpt": "Bank Leumi Le-Israel"}]',
    "insurance": '[{"fact_key": "source_date", "fact_value": "2025-01-15", "confidence": 0.9, "source_excerpt": "תאריך הפקה: 15/01/2025"}, {"fact_key": "counterparty", "fact_value": "הראל ביטוח", "confidence": 0.9, "source_excerpt": "הראל חברה לביטוח"}, {"fact_key": "policy_number", "fact_value": "POL-2025-78432", "confidence": 0.95, "source_excerpt": "מספר פוליסה: POL-2025-78432"}, {"fact_key": "insurance_type", "fact_value": "home", "confidence": 0.85, "source_excerpt": "ביטוח דירה ותכולה"}, {"fact_key": "premium_amount", "fact_value": "2400", "confidence": 0.8, "source_excerpt": "פרמיה שנתית: ₪2,400"}, {"fact_key": "deductible_amount", "fact_value": "500", "confidence": 0.8, "source_excerpt": "השתתפות עצמית: ₪500"}]',
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


# ── Large document chunking ──────────────────────────────────────────────
# Documents over this character count get chunked extraction
_LARGE_DOC_THRESHOLD = 4000
_CHUNK_SIZE = 3000
_CHUNK_OVERLAP = 300


def _chunk_text(text: str, chunk_size: int = _CHUNK_SIZE, overlap: int = _CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks for multi-pass extraction."""
    if len(text) <= chunk_size:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start = end - overlap
    return chunks


async def _extract_from_chunk(
    chunk: str,
    chunk_idx: int,
    total_chunks: int,
    doc_type: str,
    target_keys: list[str],
    filename: str,
) -> list[dict[str, Any]]:
    """Extract facts from a single chunk of a large document."""
    key_descriptions = "\n".join(
        f"  - {k}: {_FACT_KEY_DESCRIPTIONS.get(k, k)}"
        for k in target_keys
    )
    example = _CATEGORY_EXAMPLES.get(doc_type, _CATEGORY_EXAMPLES.get("invoice", "[]"))

    prompt = (
        f"You are extracting structured facts from part {chunk_idx + 1}/{total_chunks} "
        f"of a {doc_type} document.\n"
        f"Filename: {filename}\n\n"
        f"Target fact keys to extract:\n{key_descriptions}\n\n"
        f"Respond with a JSON array only. Each item must have exactly these fields:\n"
        f'  {{"fact_key": "<key>", "fact_value": "<value>", '
        f'"confidence": <0.0-1.0>, "source_excerpt": "<short quote from text>"}}\n\n'
        f"Rules:\n"
        f"- Only include facts you can actually find in THIS chunk of text\n"
        f"- Only use these allowed keys: {', '.join(target_keys)}\n"
        f"- confidence should reflect how certain you are (0.0 = guess, 1.0 = exact match)\n"
        f"- source_excerpt should be a short quote from the document supporting the fact\n"
        f"- Return [] if no relevant facts are found in this chunk\n\n"
        f"Example output:\n{example}\n\n"
        f"Document text (chunk {chunk_idx + 1}/{total_chunks}):\n{chunk}"
    )
    system = "You are a document fact extractor. Respond only with a valid JSON array."
    raw = await llm_generate(prompt, system, "haiku")
    if not raw:
        return []
    match = re.search(r'\[.*\]', raw, re.DOTALL)
    if not match:
        return []
    try:
        return json.loads(match.group())
    except (json.JSONDecodeError, ValueError):
        return []


def _merge_chunk_facts(
    all_items: list[dict[str, Any]],
    doc_type: str,
    allowed_keys: set[str],
) -> list[dict[str, Any]]:
    """Merge facts from multiple chunks, keeping highest-confidence per key.

    For keys that can have multiple values (obligations, parties, coverage_description),
    we concatenate rather than deduplicate.
    """
    _MULTI_VALUE_KEYS = {
        "obligations", "parties", "coverage_description",
        "penalty_clause", "renewal_terms", "termination_clause",
    }
    best_by_key: dict[str, dict[str, Any]] = {}
    multi_values: dict[str, list[str]] = {}

    for item in all_items:
        key = item.get("fact_key", "")
        value = str(item.get("fact_value", "")).strip()
        if key not in allowed_keys or not value:
            continue
        confidence = float(item.get("confidence", 0.5))
        excerpt = _truncate_excerpt(str(item.get("source_excerpt", "")))

        if key in _MULTI_VALUE_KEYS:
            if key not in multi_values:
                multi_values[key] = []
                best_by_key[key] = {
                    "fact_type": doc_type,
                    "fact_key": key,
                    "fact_value": value,
                    "confidence": confidence,
                    "source_excerpt": excerpt,
                }
            if value not in multi_values[key]:
                multi_values[key].append(value)
                best_by_key[key]["fact_value"] = "; ".join(multi_values[key])
                best_by_key[key]["confidence"] = max(best_by_key[key]["confidence"], confidence)
        else:
            if key not in best_by_key or confidence > best_by_key[key]["confidence"]:
                best_by_key[key] = {
                    "fact_type": doc_type,
                    "fact_key": key,
                    "fact_value": value,
                    "confidence": confidence,
                    "source_excerpt": excerpt,
                }

    return list(best_by_key.values())


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
            is_large = len(raw_text) > _LARGE_DOC_THRESHOLD
            try:
                if is_large:
                    # Chunked extraction for large documents (contracts, insurance, etc.)
                    chunks = _chunk_text(raw_text)
                    logger.info(
                        "fact_extractor: large_doc doc=%s chars=%d chunks=%d doc_type=%s",
                        filename, len(raw_text), len(chunks), doc_type,
                    )
                    all_items: list[dict[str, Any]] = []
                    for idx, chunk in enumerate(chunks):
                        chunk_items = await _extract_from_chunk(
                            chunk, idx, len(chunks), doc_type, remaining_keys, filename,
                        )
                        all_items.extend(chunk_items)
                    merged = _merge_chunk_facts(all_items, doc_type, set(ALLOWED_FACT_KEYS))
                    for fact in merged:
                        if fact["fact_key"] not in extracted_keys:
                            facts.append(fact)
                            extracted_keys.add(fact["fact_key"])
                    logger.info(
                        "fact_extractor: chunked_merge doc=%s chunks=%d raw_items=%d merged=%d",
                        filename, len(chunks), len(all_items), len(merged),
                    )
                else:
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


async def _extract_salary_slip_facts(
    raw_text: str,
    filename: str,
    image_path: str,
    text_quality: float = 1.0,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Extract salary slip facts with structured vision first, text fallback second.

    Returns (facts, metadata_delta).
    """
    structured = {}
    extraction_model = ""
    suffix = Path(image_path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".heic"}:
        structured = await extract_structured_with_vision(image_path)
        if structured:
            extraction_model = "haiku_vision"
    if not structured and raw_text.strip():
        structured, extraction_model = await _extract_salary_slip_from_text(raw_text, filename)
    if not structured:
        fallback = await extract_facts(raw_text, "other", filename, text_quality=text_quality)
        return fallback, {}

    confidence = float(structured.get("confidence") or 0.0)
    facts: list[dict[str, Any]] = []
    field_confidence: dict[str, float] = {}
    for key, value in structured.items():
        if key == "confidence" or value is None:
            continue
        facts.append({
            "fact_type": "salary_slip",
            "fact_key": key,
            "fact_value": str(value),
            "confidence": confidence,
            "source_excerpt": "",
        })
        field_confidence[key] = confidence

    metadata_delta = {
        "structured_payload": structured,
        "field_confidence": field_confidence,
        "extraction_model": extraction_model or "unknown",
        "extraction_version": "v1",
    }
    return facts, metadata_delta


def _coerce_salary_slip_structured_payload(parsed: dict[str, Any]) -> dict[str, Any]:
    result = dict(_SALARY_SLIP_STRUCTURED_KEYS)
    for key in _SALARY_SLIP_STRUCTURED_KEYS:
        if key not in parsed:
            continue
        value = parsed.get(key)
        if key in {"employee_name", "employer_name", "pay_month"}:
            result[key] = str(value).strip() if value is not None else None
        elif key == "confidence":
            try:
                result[key] = max(0.0, min(1.0, float(value)))
            except (TypeError, ValueError):
                result[key] = 0.0
        else:
            try:
                result[key] = float(value) if value is not None else None
            except (TypeError, ValueError):
                result[key] = None
    return result


def _salary_slip_structured_is_strong_enough(structured: dict[str, Any]) -> bool:
    if not structured:
        return False
    confidence = float(structured.get("confidence") or 0.0)
    present_critical = sum(1 for key in _SALARY_SLIP_CRITICAL_KEYS if structured.get(key) is not None)
    return confidence >= 0.6 and present_critical >= 3


async def _extract_salary_slip_from_text(raw_text: str, filename: str) -> tuple[dict[str, Any], str]:
    """Extract salary-slip structured fields from OCR/text when vision is unavailable or unsuitable."""
    base_prompt = (
        "Extract structured salary-slip data from the following text.\n"
        "Return JSON only with exactly these keys:\n"
        "{\n"
        '  "employee_name": str | null,\n'
        '  "employer_name": str | null,\n'
        '  "pay_month": str | null,\n'
        '  "gross_salary": float | null,\n'
        '  "net_salary": float | null,\n'
        '  "net_to_pay": float | null,\n'
        '  "total_deductions": float | null,\n'
        '  "income_tax": float | null,\n'
        '  "national_insurance": float | null,\n'
        '  "health_tax": float | null,\n'
        '  "pension_employee": float | null,\n'
        '  "pension_employer": float | null,\n'
        '  "confidence": float\n'
        "}\n"
        "Rules:\n"
        "- output valid JSON only\n"
        "- numbers must be JSON numbers\n"
        "- unknown values must be null\n"
        "- pay_month should prefer YYYY-MM when clear\n"
        "- confidence should reflect how reliable the extraction is from the text\n\n"
        f"Document filename: {filename}\n"
        f"Document text:\n{raw_text[:7000]}\n\n"
        "Pay special attention to:\n"
        "- net salary / net to pay\n"
        "- gross salary / gross pay\n"
        "- monthly pay period\n"
        "- employer name and employee name when present\n"
        "- pension and mandatory deductions"
    )
    system = (
        "You extract structured payroll data from salary slips. "
        "Return only strict JSON with the requested schema."
    )

    async def _run_extract(model_tier: str, extra_instruction: str = "") -> dict[str, Any]:
        raw = await llm_generate(
            base_prompt + (f"\n\nAdditional instruction:\n{extra_instruction}" if extra_instruction else ""),
            system,
            model_tier,
        )
        if not raw:
            return {}
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            logger.warning("salary_slip_text_extract: no JSON object found doc=%s tier=%s", filename, model_tier)
            return {}
        try:
            parsed = json.loads(match.group())
        except json.JSONDecodeError:
            logger.warning("salary_slip_text_extract: invalid JSON doc=%s tier=%s", filename, model_tier)
            return {}
        if not isinstance(parsed, dict):
            return {}
        return _coerce_salary_slip_structured_payload(parsed)

    structured = await _run_extract("haiku")
    logger.info(
        "salary_slip_text_extract: doc=%s tier=%s confidence=%.2f has_gross=%s has_net=%s",
        filename,
        "haiku",
        float(structured.get("confidence") or 0.0) if structured else 0.0,
        bool(structured.get("gross_salary")) if structured else False,
        bool(structured.get("net_salary")) if structured else False,
    )
    if _salary_slip_structured_is_strong_enough(structured):
        return structured, "haiku_text"

    stronger_instruction = (
        "The first pass was weak or incomplete. Re-read carefully and prefer exact payroll values. "
        "If multiple candidate salary numbers exist, prefer the main pay totals and net-to-pay figures. "
        "Do not guess names. Leave uncertain fields null."
    )
    stronger = await _run_extract("sonnet", stronger_instruction)
    logger.info(
        "salary_slip_text_extract: doc=%s tier=%s confidence=%.2f has_gross=%s has_net=%s",
        filename,
        "sonnet",
        float(stronger.get("confidence") or 0.0) if stronger else 0.0,
        bool(stronger.get("gross_salary")) if stronger else False,
        bool(stronger.get("net_salary")) if stronger else False,
    )
    if _salary_slip_structured_is_strong_enough(stronger):
        return stronger, "sonnet_text"

    if stronger and (float(stronger.get("confidence") or 0.0) >= float(structured.get("confidence") or 0.0)):
        return stronger, "sonnet_text"
    return structured, "haiku_text"
