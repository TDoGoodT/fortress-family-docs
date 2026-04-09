from __future__ import annotations
"""Fortress document service — document ingestion and enrichment pipeline."""

import hashlib
import logging
import os
import re
import shutil
import uuid as uuid_mod
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from src.config import STORAGE_PATH, DOCUMENT_VISION_FALLBACK_ENABLED
from src.models.schema import Document, DocumentFact, SalarySlip
from src.services.text_extractor import extract_text, extract_text_v2
from src.services.image_preprocessor import get_quality_band
from src.services.document_processors.processor_router import process_with_best
from src.services.document_processors.base_processor import ProcessorResult
from src.services.document_classifier import (
    classify_document,
    REVIEW_CONFIDENCE_THRESHOLD,
)
from src.services.document_fact_extractor import extract_facts
from src.services.document_fact_extractor import _extract_salary_slip_facts
from src.services.document_summarizer import summarize_document
from src.services.document_namer import generate_display_name
from src.services.document_query_service import merge_tags, normalize_tag

logger = logging.getLogger(__name__)

# File types where text extraction is expected (not spreadsheets or unsupported)
_EXTRACTABLE_EXTENSIONS = {".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png", ".heic"}
_SPREADSHEET_EXTENSIONS = {".xls", ".xlsx"}


def _log_step(step: str, doc_id, filename: str, status: str, **extra) -> None:
    """Emit a structured pipeline log entry."""
    parts = [f"[PIPELINE] step={step} doc_id={doc_id} filename={filename} status={status}"]
    for k, v in extra.items():
        parts.append(f"{k}={v}")
    logger.info(" ".join(parts))


def _extract_year_tag(doc_date, filename: str) -> str:
    """Return a year tag from source date or filename, if present."""
    if doc_date:
        return str(doc_date.year)
    for token in filename.replace(".", " ").replace("-", " ").split():
        if token.isdigit() and len(token) == 4 and token.startswith(("19", "20")):
            return token
    return ""


_UUID_PREFIX_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}_")


def _strip_uuid_prefix(filename: str) -> str:
    """Strip leading UUID prefix from filenames like '2e7797c9-...-4f0d9a81554e_MyFile.pdf'."""
    return _UUID_PREFIX_RE.sub("", filename)


def _compute_file_hash(file_path: str) -> str:
    """Compute SHA-256 hash of a file's contents for dedup."""
    h = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
    except Exception:
        return ""
    return h.hexdigest()


def _find_duplicate(db: Session, file_hash: str, uploaded_by: UUID) -> Document | None:
    """Check if a document with the same content hash already exists for this user."""
    if not file_hash:
        return None
    return (
        db.query(Document)
        .filter(
            Document.uploaded_by == uploaded_by,
            Document.doc_metadata["file_hash"].astext == file_hash,
        )
        .first()
    )


def _generate_auto_tags(doc: Document, facts: list[dict], filename: str) -> list[str]:
    """Generate deterministic, explainable tags from structured pipeline signals."""
    tags: list[str] = []

    if doc.doc_type:
        tags.append(doc.doc_type)
    if doc.vendor:
        tags.append(doc.vendor)
    if doc.review_state:
        tags.append(doc.review_state)

    year_tag = _extract_year_tag(doc.doc_date, filename)
    if year_tag:
        tags.append(year_tag)

    for fact in facts:
        fact_type = normalize_tag(fact.get("fact_type", ""))
        if fact_type in {"policy", "contract", "invoice", "payment"}:
            tags.append(fact_type)

    return merge_tags([], tags)


# ── Fact Promotion ───────────────────────────────────────────────────────

# Maps fact_key → Document column name
PROMOTION_MAP: dict[str, str] = {
    "counterparty": "vendor",
    "amount": "amount",
    "currency": "currency",
    "source_date": "doc_date",
}


def _parse_amount(value: str) -> Decimal | None:
    """Parse an amount string to Decimal, stripping commas/whitespace.

    Handles '1,234.56', '1234.56', '1234'. Returns None on failure.
    """
    try:
        cleaned = value.replace(",", "").strip()
        if not cleaned:
            return None
        return Decimal(cleaned)
    except (InvalidOperation, ValueError, ArithmeticError):
        return None


def _parse_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value: str) -> date | None:
    """Parse a date string. Tries ISO YYYY-MM-DD first, then DD/MM/YYYY and DD.MM.YYYY.

    Returns None on failure.
    """
    stripped = value.strip()
    # ISO format: YYYY-MM-DD
    try:
        return date.fromisoformat(stripped)
    except (ValueError, TypeError):
        pass
    # DD/MM/YYYY
    for sep in ("/", "."):
        parts = stripped.split(sep)
        if len(parts) == 3:
            try:
                day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
                return date(year, month, day)
            except (ValueError, TypeError):
                continue
    return None


def _parse_salary_slip_period(value: Any) -> tuple[int | None, int | None]:
    """Parse a salary-slip pay period from values like 2026-03 or 03/2026."""
    if value is None:
        return None, None
    text = str(value).strip()
    if not text:
        return None, None

    match = re.match(r"^(?P<year>\d{4})[-/.](?P<month>\d{1,2})$", text)
    if not match:
        match = re.match(r"^(?P<month>\d{1,2})[-/.](?P<year>\d{4})$", text)
    if not match:
        return None, None

    year = _parse_int(match.group("year"))
    month = _parse_int(match.group("month"))
    if month is not None and not 1 <= month <= 12:
        month = None
    return year, month


def _build_salary_slip_review_reason(structured: dict[str, Any]) -> str | None:
    confidence = float(structured.get("confidence") or 0.0)
    reasons: list[str] = []
    if confidence < 0.6:
        reasons.append("low_confidence")
    if not structured.get("gross_salary"):
        reasons.append("missing_gross_salary")
    if not structured.get("net_salary"):
        reasons.append("missing_net_salary")
    return ",".join(reasons) if reasons else None


def _upsert_salary_slip(
    db: Session,
    doc: Document,
    uploaded_by: UUID,
    source: str,
    metadata: dict[str, Any],
    extracted_facts: list[dict[str, Any]],
) -> SalarySlip:
    structured = metadata.get("structured_payload", {}) if isinstance(metadata, dict) else {}
    if not isinstance(structured, dict):
        structured = {}
    fact_map = {
        fact.get("fact_key"): fact.get("fact_value")
        for fact in extracted_facts
        if fact.get("fact_key") and fact.get("fact_value") not in (None, "")
    }

    pay_period_value = structured.get("pay_month") or fact_map.get("pay_month")
    pay_year, pay_month = _parse_salary_slip_period(pay_period_value)
    extraction_confidence = _parse_amount(str(structured.get("confidence", "0.0"))) or Decimal("0.0")
    review_reason = _build_salary_slip_review_reason(structured)

    salary_slip = (
        db.query(SalarySlip)
        .filter(SalarySlip.document_id == doc.id)
        .first()
    )
    if salary_slip is None:
        salary_slip = SalarySlip(document_id=doc.id)
        db.add(salary_slip)

    salary_slip.family_member_id = uploaded_by
    salary_slip.employee_name = structured.get("employee_name") or fact_map.get("employee_name")
    salary_slip.employer_name = structured.get("employer_name") or fact_map.get("employer_name") or doc.vendor
    salary_slip.pay_year = pay_year
    salary_slip.pay_month = pay_month
    salary_slip.currency = structured.get("currency") or fact_map.get("currency") or doc.currency or "ILS"
    salary_slip.gross_salary = _parse_amount(str(structured.get("gross_salary") or fact_map.get("gross_salary") or ""))
    salary_slip.net_salary = _parse_amount(str(structured.get("net_salary") or fact_map.get("net_salary") or ""))
    salary_slip.net_to_pay = _parse_amount(str(structured.get("net_to_pay") or fact_map.get("net_to_pay") or ""))
    salary_slip.total_deductions = _parse_amount(str(structured.get("total_deductions") or fact_map.get("total_deductions") or ""))
    salary_slip.income_tax = _parse_amount(str(structured.get("income_tax") or fact_map.get("income_tax") or ""))
    salary_slip.national_insurance = _parse_amount(str(structured.get("national_insurance") or fact_map.get("national_insurance") or ""))
    salary_slip.health_tax = _parse_amount(str(structured.get("health_tax") or fact_map.get("health_tax") or ""))
    salary_slip.pension_employee = _parse_amount(str(structured.get("pension_employee") or fact_map.get("pension_employee") or ""))
    salary_slip.pension_employer = _parse_amount(str(structured.get("pension_employer") or fact_map.get("pension_employer") or ""))
    salary_slip.extraction_confidence = extraction_confidence
    salary_slip.review_state = doc.review_state
    salary_slip.review_reason = review_reason
    salary_slip.source_channel = source
    salary_slip.raw_payload = structured

    doc.doc_metadata = {
        **(doc.doc_metadata or {}),
        "source_channel": source,
        "canonical_record_type": "salary_slip",
        "canonical_record_ready": bool(structured),
        "canonical_salary_period": {
            "pay_year": pay_year,
            "pay_month": pay_month,
        },
    }
    return salary_slip


def promote_facts_to_document(
    doc: Document,
    facts: list[dict[str, Any]],
    confidence_threshold: float = 0.6,
) -> dict[str, str]:
    """Promote high-confidence extracted facts to Document columns.

    Mapping (PROMOTION_MAP):
        counterparty → doc.vendor
        amount       → doc.amount (parsed to Decimal)
        currency     → doc.currency
        source_date  → doc.doc_date (parsed to date)

    Rules:
    - Only promotes facts with confidence >= threshold
    - Never overwrites existing non-null column values
    - Skips amount if string can't parse to Decimal (logs warning)
    - Skips source_date if string can't parse to date (logs warning)
    - Does NOT call db.commit()
    - Returns dict of {column_name: promoted_value_str} for logging
    """
    promoted: dict[str, str] = {}

    for fact in facts:
        fact_key = fact.get("fact_key", "")
        if fact_key not in PROMOTION_MAP:
            continue

        confidence = float(fact.get("confidence", 0.0))
        if confidence < confidence_threshold:
            continue

        col_name = PROMOTION_MAP[fact_key]
        current_value = getattr(doc, col_name, None)
        if current_value is not None:
            continue

        fact_value = str(fact.get("fact_value", "")).strip()
        if not fact_value:
            continue

        # Type-specific parsing
        if col_name == "amount":
            parsed = _parse_amount(fact_value)
            if parsed is None:
                logger.warning(
                    "fact_promotion: failed to parse amount value=%r doc_id=%s",
                    fact_value, doc.id,
                )
                continue
            doc.amount = parsed
            promoted[col_name] = fact_value

        elif col_name == "doc_date":
            parsed = _parse_date(fact_value)
            if parsed is None:
                logger.warning(
                    "fact_promotion: failed to parse date value=%r doc_id=%s",
                    fact_value, doc.id,
                )
                continue
            doc.doc_date = parsed
            promoted[col_name] = fact_value

        else:
            # String columns: vendor, currency
            setattr(doc, col_name, fact_value)
            promoted[col_name] = fact_value

    return promoted


def _promote_salary_slip_fields(
    doc: Document,
    facts: list[dict[str, Any]],
    confidence_threshold: float = 0.8,
) -> dict[str, str]:
    """Conservative promotion for salary slips: employer_name -> vendor only."""
    promoted: dict[str, str] = {}
    if doc.vendor:
        return promoted
    for fact in facts:
        if fact.get("fact_type") != "salary_slip" or fact.get("fact_key") != "employer_name":
            continue
        confidence = float(fact.get("confidence", 0.0))
        if confidence < confidence_threshold:
            continue
        value = str(fact.get("fact_value", "")).strip()
        if not value:
            continue
        doc.vendor = value
        promoted["vendor"] = value
        break
    return promoted


async def process_document(
    db: Session,
    file_path: str,
    uploaded_by: UUID,
    source: str,
) -> Document:
    """Ingest a document through the full enrichment pipeline.

    Step 0: File copy + DB record (guaranteed — pipeline aborts only here)
    Step 1: Text extraction
    Step 2: Classification
    Step 3: Fact extraction
    Step 4: Summary generation
    Step 5: Review state assignment
    Step 6: Final persist + log summary

    Each step after Step 0 is wrapped in try/except — failures are logged
    and the pipeline continues with partial results.
    """
    if not file_path:
        raise ValueError("process_document: file_path is empty or None")

    logger.info("[PIPELINE] media_received file_path=%s source=%s", file_path, source)

    original_filename = os.path.basename(file_path)
    # Strip UUID prefix from WhatsApp filenames (e.g. "2e7797c9-..._MyFile.pdf" → "MyFile.pdf")
    original_filename = _strip_uuid_prefix(original_filename)
    _, ext = os.path.splitext(original_filename)
    ext_lower = ext.lower()

    # ── Duplicate detection ──────────────────────────────────────────────
    file_hash = _compute_file_hash(file_path)
    if file_hash:
        existing = _find_duplicate(db, file_hash, uploaded_by)
        if existing:
            dn = getattr(existing, "display_name", None) or existing.original_filename or "מסמך"
            logger.info("[PIPELINE] duplicate detected: file_hash=%s existing_doc_id=%s", file_hash, existing.id)
            return existing

    # ── Step 0: File copy + DB record ────────────────────────────────────
    now = datetime.now(timezone.utc)
    unique_id = uuid_mod.uuid4().hex[:8]
    storage_dir = os.path.join(STORAGE_PATH, str(now.year), f"{now.month:02d}")
    os.makedirs(storage_dir, exist_ok=True)

    # If the file is already inside STORAGE_PATH (saved by save_media), use it directly.
    # Otherwise copy it to storage.
    abs_storage = os.path.abspath(STORAGE_PATH)
    abs_file = os.path.abspath(file_path)
    if abs_file.startswith(abs_storage):
        storage_path = file_path
        logger.info("[PIPELINE] step=file_store doc_id=pending filename=%s status=reused path=%s",
                    original_filename, storage_path)
    else:
        storage_filename = f"{unique_id}_{original_filename}"
        storage_path = os.path.join(storage_dir, storage_filename)
        shutil.copy2(file_path, storage_path)
        logger.info("[PIPELINE] step=file_store doc_id=pending filename=%s status=copied path=%s",
                    original_filename, storage_path)

    doc = Document(
        file_path=storage_path,
        original_filename=original_filename,
        doc_type="other",
        uploaded_by=uploaded_by,
        source=source,
        review_state="pending",
        confidence=0.0,
        tags=[],
        doc_metadata={"file_hash": file_hash} if file_hash else {},
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    doc_id = str(doc.id)
    logger.info("[PIPELINE] step=db_record doc_id=%s filename=%s status=success", doc_id, original_filename)

    # Track pipeline outcomes for final summary log
    steps_ok: list[str] = []
    steps_failed: list[str] = []

    # ── Step 1: Text extraction ───────────────────────────────────────────
    raw_text = ""
    text_quality = 0.0
    extraction_method = "none"
    processor_result: ProcessorResult | None = None
    try:
        if ext_lower not in _SPREADSHEET_EXTENSIONS:
            # Try new processor system first (Google DocAI → Bedrock Vision → Tesseract)
            processor_result = await process_with_best(storage_path, doc_type="other")
            if processor_result and processor_result.has_text:
                raw_text = processor_result.raw_text
                text_quality = processor_result.confidence
                extraction_method = processor_result.extraction_method
                doc.raw_text = raw_text
                _log_step("text_extraction", doc_id, original_filename, "success",
                          chars=len(raw_text), method=extraction_method,
                          quality=f"{text_quality:.2f}",
                          processor=processor_result.processor_name,
                          pages=processor_result.page_count,
                          lang=processor_result.language_detected or "unknown",
                          tables=len(processor_result.tables))
                # Log extracted tables for debugging
                if processor_result.tables:
                    for t_idx, table in enumerate(processor_result.tables):
                        logger.info("[PIPELINE] doc_id=%s table_%d rows=%d: %s",
                                    doc_id, t_idx, len(table),
                                    str(table[:3])[:500])  # first 3 rows, truncated
                # Log first 500 chars of extracted text for debugging
                logger.info("[PIPELINE] doc_id=%s text_preview: %s",
                            doc_id, raw_text[:500].replace("\n", " | "))
                steps_ok.append("text_extraction")
            else:
                # Fallback to legacy extract_text_v2
                logger.info("[PIPELINE] doc_id=%s processor_router returned no text, falling back to extract_text_v2",
                            doc_id)
                raw_text, text_quality, extraction_method = await extract_text_v2(storage_path)
                if raw_text:
                    doc.raw_text = raw_text
                    _log_step("text_extraction", doc_id, original_filename, "success",
                              chars=len(raw_text), method=extraction_method,
                              quality=f"{text_quality:.2f}")
                    steps_ok.append("text_extraction")
                else:
                    _log_step("text_extraction", doc_id, original_filename, "skipped",
                              reason="empty_result")
                    steps_ok.append("text_extraction")

            # Merge quality metadata into doc_metadata
            doc.doc_metadata = {
                **(doc.doc_metadata or {}),
                "text_quality_score": text_quality,
                "extraction_method": extraction_method,
                "quality_band": get_quality_band(text_quality) if extraction_method != "google_docai" else "GOOD",
                "vision_fallback_enabled": DOCUMENT_VISION_FALLBACK_ENABLED,
                "processor_name": processor_result.processor_name if processor_result else "legacy",
                "processor_tables_count": len(processor_result.tables) if processor_result else 0,
            }
        else:
            _log_step("text_extraction", doc_id, original_filename, "skipped",
                      reason="spreadsheet")
            steps_ok.append("text_extraction")
    except Exception as exc:
        _log_step("text_extraction", doc_id, original_filename, "failed",
                  error=f"{type(exc).__name__}: {exc}")
        steps_failed.append("text_extraction")

    # ── Step 2: Classification ────────────────────────────────────────────
    classification_confidence = 0.0
    try:
        category, confidence = await classify_document(raw_text, original_filename)
        doc.doc_type = category
        doc.confidence = confidence
        classification_confidence = confidence
        _log_step("classification", doc_id, original_filename, "success",
                  category=category, confidence=f"{confidence:.2f}")
        steps_ok.append("classification")
    except Exception as exc:
        _log_step("classification", doc_id, original_filename, "failed",
                  error=f"{type(exc).__name__}: {exc}")
        steps_failed.append("classification")

    # ── Step 3: Fact extraction ───────────────────────────────────────────
    fact_count = 0
    extracted_facts: list[dict] = []
    metadata_delta: dict[str, Any] = {}
    try:
        if doc.doc_type == "salary_slip":
            extracted_facts, metadata_delta = await _extract_salary_slip_facts(
                raw_text=raw_text,
                filename=original_filename,
                image_path=storage_path,
                text_quality=text_quality,
            )
            if metadata_delta:
                doc.doc_metadata = {
                    **(doc.doc_metadata or {}),
                    **metadata_delta,
                }
        else:
            extracted_facts = await extract_facts(raw_text, doc.doc_type, original_filename, text_quality=text_quality)
        for fact_data in extracted_facts:
            fact = DocumentFact(
                document_id=doc.id,
                fact_type=fact_data["fact_type"],
                fact_key=fact_data["fact_key"],
                fact_value=fact_data["fact_value"],
                confidence=fact_data.get("confidence", 0.5),
                source_excerpt=fact_data.get("source_excerpt", ""),
            )
            db.add(fact)
        fact_count = len(extracted_facts)
        _log_step("fact_extraction", doc_id, original_filename, "success",
                  facts_count=fact_count)
        steps_ok.append("fact_extraction")
    except Exception as exc:
        _log_step("fact_extraction", doc_id, original_filename, "failed",
                  error=f"{type(exc).__name__}: {exc}")
        steps_failed.append("fact_extraction")

    # ── Step 3.5: Fact promotion ──────────────────────────────────────────
    try:
        if doc.doc_type == "salary_slip":
            promoted = _promote_salary_slip_fields(doc, extracted_facts)
        else:
            promoted = promote_facts_to_document(doc, extracted_facts)
        if promoted:
            _log_step("fact_promotion", doc_id, original_filename, "success",
                      promoted_fields=",".join(promoted.keys()))
            steps_ok.append("fact_promotion")
        else:
            _log_step("fact_promotion", doc_id, original_filename, "skipped",
                      reason="no_promotable_facts")
            steps_ok.append("fact_promotion")
    except Exception as exc:
        _log_step("fact_promotion", doc_id, original_filename, "failed",
                  error=f"{type(exc).__name__}: {exc}")
        steps_failed.append("fact_promotion")

    # ── Step 4: Summary generation ────────────────────────────────────────
    try:
        summary = await summarize_document(raw_text, doc.doc_type, original_filename)
        if summary:
            doc.ai_summary = summary
        _log_step("summary", doc_id, original_filename, "success" if summary else "skipped")
        steps_ok.append("summary")
    except Exception as exc:
        _log_step("summary", doc_id, original_filename, "failed",
                  error=f"{type(exc).__name__}: {exc}")
        steps_failed.append("summary")

    # ── Step 5.25: Display name generation ──────────────────────────────
    try:
        # Read vendor/doc_date from Document columns first
        dn_vendor = doc.vendor
        dn_doc_date = doc.doc_date

        # Fall back to document_facts for counterparty and source_date
        if not dn_vendor or not dn_doc_date:
            for fact_data in extracted_facts:
                fk = fact_data.get("fact_key", "")
                fv = fact_data.get("fact_value", "")
                if not dn_vendor and fk == "counterparty" and fv:
                    dn_vendor = fv
                if not dn_doc_date and fk == "source_date" and fv:
                    from datetime import date as _date_type
                    try:
                        dn_doc_date = _date_type.fromisoformat(fv)
                    except (ValueError, TypeError):
                        pass

        # Promote recipe_name to vendor for better deterministic display naming
        if doc.doc_type == "recipe" and not dn_vendor:
            recipe_names = [
                f.get("fact_value", "")
                for f in extracted_facts
                if f.get("fact_key") == "recipe_name" and f.get("fact_value", "").strip()
            ]
            if len(recipe_names) == 1:
                dn_vendor = recipe_names[0]

        display_name = generate_display_name(
            doc_type=doc.doc_type,
            vendor=dn_vendor,
            doc_date=dn_doc_date,
            ai_summary=doc.ai_summary,
        )
        if display_name:
            doc.display_name = display_name
        _log_step("display_name", doc_id, original_filename,
                  "success" if display_name else "skipped",
                  display_name=display_name or "")
        steps_ok.append("display_name")
    except Exception as exc:
        _log_step("display_name", doc_id, original_filename, "failed",
                  error=f"{type(exc).__name__}: {exc}")
        steps_failed.append("display_name")

    # ── Step 5: Review state assignment ──────────────────────────────────
    try:
        if doc.doc_type == "salary_slip":
            structured = (doc.doc_metadata or {}).get("structured_payload", {})
            confidence = float(structured.get("confidence", 0.0)) if isinstance(structured, dict) else 0.0
            has_net = bool(structured.get("net_salary")) if isinstance(structured, dict) else False
            has_gross = bool(structured.get("gross_salary")) if isinstance(structured, dict) else False
            if confidence < 0.6 or not has_net or not has_gross:
                doc.review_state = "needs_review"
            else:
                doc.review_state = "auto_verified"
            _log_step("review_state", doc_id, original_filename, doc.review_state)
            steps_ok.append("review_state")
        else:
            signal_a = classification_confidence >= REVIEW_CONFIDENCE_THRESHOLD
            # Signal B: text extraction expected and non-empty (skip check for spreadsheets)
            if ext_lower in _SPREADSHEET_EXTENSIONS or ext_lower not in _EXTRACTABLE_EXTENSIONS:
                signal_b = True  # not expected to have text
            else:
                signal_b = bool(raw_text and raw_text.strip())
            signal_c = fact_count >= 1 or bool(doc.ai_summary)

            if signal_a and signal_b and signal_c:
                doc.review_state = "auto_verified"
            else:
                doc.review_state = "needs_review"
                failed_signals = []
                if not signal_a:
                    failed_signals.append(f"classification_confidence={classification_confidence:.2f}<{REVIEW_CONFIDENCE_THRESHOLD}")
                if not signal_b:
                    failed_signals.append("text_extraction_empty")
                if not signal_c:
                    failed_signals.append("no_facts_and_no_summary")
                logger.warning(
                    "[PIPELINE] step=review_state doc_id=%s filename=%s status=needs_review signals=%s",
                    doc_id, original_filename, ",".join(failed_signals),
                )

            _log_step("review_state", doc_id, original_filename, doc.review_state)
            steps_ok.append("review_state")
    except Exception as exc:
        _log_step("review_state", doc_id, original_filename, "failed",
                  error=f"{type(exc).__name__}: {exc}")
        doc.review_state = "needs_review"
        steps_failed.append("review_state")

    # ── Step 5.1: canonical salary-slip row ─────────────────────────────
    try:
        if doc.doc_type == "salary_slip":
            salary_slip = _upsert_salary_slip(
                db=db,
                doc=doc,
                uploaded_by=uploaded_by,
                source=source,
                metadata=doc.doc_metadata or metadata_delta,
                extracted_facts=extracted_facts,
            )
            _log_step(
                "salary_slip_persist",
                doc_id,
                original_filename,
                "success",
                pay_year=salary_slip.pay_year or "",
                pay_month=salary_slip.pay_month or "",
                employer=salary_slip.employer_name or "",
            )
            steps_ok.append("salary_slip_persist")
    except Exception as exc:
        _log_step("salary_slip_persist", doc_id, original_filename, "failed",
                  error=f"{type(exc).__name__}: {exc}")
        steps_failed.append("salary_slip_persist")

    # ── Step 5.5: deterministic auto-tagging ────────────────────────────
    try:
        auto_tags = _generate_auto_tags(doc, extracted_facts, original_filename)
        doc.tags = merge_tags(doc.tags or [], auto_tags)
        _log_step("tagging", doc_id, original_filename, "success", tags_count=len(doc.tags or []))
        steps_ok.append("tagging")
    except Exception as exc:
        _log_step("tagging", doc_id, original_filename, "failed",
                  error=f"{type(exc).__name__}: {exc}")
        steps_failed.append("tagging")

    # ── Step 6: Final persist + summary log ──────────────────────────────
    db.commit()
    db.refresh(doc)

    total = len(steps_ok) + len(steps_failed)
    logger.info(
        "[PIPELINE] doc_id=%s filename=%s result=%s steps_ok=%d/%d failed=%s",
        doc_id, original_filename,
        "complete" if not steps_failed else "partial",
        len(steps_ok), total,
        ",".join(steps_failed) if steps_failed else "none",
    )

    return doc


async def process_text(
    db: Session,
    raw_text: str,
    uploaded_by: UUID,
    title: str | None = None,
) -> Document:
    """Ingest raw text through the enrichment pipeline.

    Like process_document but skips file-copy and text-extraction steps.
    Persists the text as a .txt file and creates a Document record with
    source="text_message".

    Each enrichment step is wrapped in try/except — the raw text is saved
    to the database before any enrichment runs, so it's never lost.
    """
    if not raw_text or not raw_text.strip():
        raise ValueError("process_text: raw_text is empty or whitespace")

    logger.info("[PIPELINE] text_received chars=%d source=text_message", len(raw_text))

    now = datetime.now(timezone.utc)
    unique_id = uuid_mod.uuid4().hex[:8]
    initial_filename = title if title else f"text_{now.strftime('%Y-%m-%d')}.txt"

    # ── Step 0: Write .txt file + DB record ──────────────────────────────
    storage_dir = os.path.join(STORAGE_PATH, str(now.year), f"{now.month:02d}")
    os.makedirs(storage_dir, exist_ok=True)
    storage_filename = f"{unique_id}_{initial_filename}"
    if not storage_filename.endswith(".txt"):
        storage_filename += ".txt"
    storage_path = os.path.join(storage_dir, storage_filename)

    with open(storage_path, "w", encoding="utf-8") as f:
        f.write(raw_text)
    logger.info("[PIPELINE] step=text_file_write filename=%s path=%s", initial_filename, storage_path)

    doc = Document(
        file_path=storage_path,
        original_filename=initial_filename,
        raw_text=raw_text,
        doc_type="other",
        uploaded_by=uploaded_by,
        source="text_message",
        review_state="pending",
        confidence=0.0,
        tags=[],
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    doc_id = str(doc.id)
    logger.info("[PIPELINE] step=db_record doc_id=%s filename=%s source=text_message", doc_id, initial_filename)

    steps_ok: list[str] = []
    steps_failed: list[str] = []

    # ── Step 1: Classification ────────────────────────────────────────────
    classification_confidence = 0.0
    try:
        category, confidence = await classify_document(raw_text, initial_filename)
        doc.doc_type = category
        doc.confidence = confidence
        classification_confidence = confidence
        # Update filename to reflect classified type if no title was provided
        if not title:
            doc.original_filename = f"{category}_{now.strftime('%Y-%m-%d')}.txt"
        _log_step("classification", doc_id, doc.original_filename, "success",
                  category=category, confidence=f"{confidence:.2f}")
        steps_ok.append("classification")
    except Exception as exc:
        _log_step("classification", doc_id, initial_filename, "failed",
                  error=f"{type(exc).__name__}: {exc}")
        steps_failed.append("classification")

    # ── Step 2: Fact extraction ───────────────────────────────────────────
    fact_count = 0
    extracted_facts: list[dict] = []
    try:
        extracted_facts = await extract_facts(raw_text, doc.doc_type, doc.original_filename, text_quality=1.0)
        for fact_data in extracted_facts:
            fact = DocumentFact(
                document_id=doc.id,
                fact_type=fact_data["fact_type"],
                fact_key=fact_data["fact_key"],
                fact_value=fact_data["fact_value"],
                confidence=fact_data.get("confidence", 0.5),
                source_excerpt=fact_data.get("source_excerpt", ""),
            )
            db.add(fact)
        fact_count = len(extracted_facts)
        _log_step("fact_extraction", doc_id, doc.original_filename, "success",
                  facts_count=fact_count)
        steps_ok.append("fact_extraction")
    except Exception as exc:
        _log_step("fact_extraction", doc_id, doc.original_filename, "failed",
                  error=f"{type(exc).__name__}: {exc}")
        steps_failed.append("fact_extraction")

    # ── Step 2.5: Fact promotion ──────────────────────────────────────────
    try:
        promoted = promote_facts_to_document(doc, extracted_facts)
        if promoted:
            _log_step("fact_promotion", doc_id, doc.original_filename, "success",
                      promoted_fields=",".join(promoted.keys()))
            steps_ok.append("fact_promotion")
        else:
            _log_step("fact_promotion", doc_id, doc.original_filename, "skipped",
                      reason="no_promotable_facts")
            steps_ok.append("fact_promotion")
    except Exception as exc:
        _log_step("fact_promotion", doc_id, doc.original_filename, "failed",
                  error=f"{type(exc).__name__}: {exc}")
        steps_failed.append("fact_promotion")

    # ── Step 3: Summary generation ────────────────────────────────────────
    try:
        summary = await summarize_document(raw_text, doc.doc_type, doc.original_filename)
        if summary:
            doc.ai_summary = summary
        _log_step("summary", doc_id, doc.original_filename, "success" if summary else "skipped")
        steps_ok.append("summary")
    except Exception as exc:
        _log_step("summary", doc_id, doc.original_filename, "failed",
                  error=f"{type(exc).__name__}: {exc}")
        steps_failed.append("summary")

    # ── Step 4: Display name generation ──────────────────────────────────
    try:
        dn_vendor = doc.vendor
        dn_doc_date = doc.doc_date
        if not dn_vendor or not dn_doc_date:
            for fact_data in extracted_facts:
                fk = fact_data.get("fact_key", "")
                fv = fact_data.get("fact_value", "")
                if not dn_vendor and fk == "counterparty" and fv:
                    dn_vendor = fv
                if not dn_doc_date and fk == "source_date" and fv:
                    from datetime import date as _date_type
                    try:
                        dn_doc_date = _date_type.fromisoformat(fv)
                    except (ValueError, TypeError):
                        pass
        if doc.doc_type == "recipe" and not dn_vendor:
            recipe_names = [
                f.get("fact_value", "")
                for f in extracted_facts
                if f.get("fact_key") == "recipe_name" and f.get("fact_value", "").strip()
            ]
            if len(recipe_names) == 1:
                dn_vendor = recipe_names[0]

        display_name = generate_display_name(
            doc_type=doc.doc_type,
            vendor=dn_vendor,
            doc_date=dn_doc_date,
            ai_summary=doc.ai_summary,
        )
        if display_name:
            doc.display_name = display_name
        _log_step("display_name", doc_id, doc.original_filename,
                  "success" if display_name else "skipped",
                  display_name=display_name or "")
        steps_ok.append("display_name")
    except Exception as exc:
        _log_step("display_name", doc_id, doc.original_filename, "failed",
                  error=f"{type(exc).__name__}: {exc}")
        steps_failed.append("display_name")

    # ── Step 5: Review state assignment ──────────────────────────────────
    try:
        signal_a = classification_confidence >= REVIEW_CONFIDENCE_THRESHOLD
        signal_b = True  # text is always present for text_message source
        signal_c = fact_count >= 1 or bool(doc.ai_summary)
        if signal_a and signal_b and signal_c:
            doc.review_state = "auto_verified"
        else:
            doc.review_state = "needs_review"
        _log_step("review_state", doc_id, doc.original_filename, doc.review_state)
        steps_ok.append("review_state")
    except Exception as exc:
        _log_step("review_state", doc_id, doc.original_filename, "failed",
                  error=f"{type(exc).__name__}: {exc}")
        doc.review_state = "needs_review"
        steps_failed.append("review_state")

    # ── Step 6: Auto-tagging ─────────────────────────────────────────────
    try:
        auto_tags = _generate_auto_tags(doc, extracted_facts, doc.original_filename)
        doc.tags = merge_tags(doc.tags or [], auto_tags)
        _log_step("tagging", doc_id, doc.original_filename, "success", tags_count=len(doc.tags or []))
        steps_ok.append("tagging")
    except Exception as exc:
        _log_step("tagging", doc_id, doc.original_filename, "failed",
                  error=f"{type(exc).__name__}: {exc}")
        steps_failed.append("tagging")

    # ── Step 7: Final persist ────────────────────────────────────────────
    db.commit()
    db.refresh(doc)

    total = len(steps_ok) + len(steps_failed)
    logger.info(
        "[PIPELINE] doc_id=%s filename=%s source=text_message result=%s steps_ok=%d/%d failed=%s",
        doc_id, doc.original_filename,
        "complete" if not steps_failed else "partial",
        len(steps_ok), total,
        ",".join(steps_failed) if steps_failed else "none",
    )

    return doc
