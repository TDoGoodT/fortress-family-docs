from __future__ import annotations
"""Fortress document service — document ingestion and enrichment pipeline."""

import hashlib
import logging
import os
import re
import shutil
import uuid as uuid_mod
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from src.config import STORAGE_PATH, DOCUMENT_VISION_FALLBACK_ENABLED
from src.models.schema import Document, DocumentFact
from src.services.text_extractor import extract_text, extract_text_v2
from src.services.image_preprocessor import get_quality_band
from src.services.document_classifier import (
    classify_document,
    REVIEW_CONFIDENCE_THRESHOLD,
)
from src.services.document_fact_extractor import extract_facts
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
    try:
        if ext_lower not in _SPREADSHEET_EXTENSIONS:
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
                "quality_band": get_quality_band(text_quality),
                "vision_fallback_enabled": DOCUMENT_VISION_FALLBACK_ENABLED,
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
    try:
        extracted_facts = await extract_facts(raw_text, doc.doc_type, original_filename)
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
        extracted_facts = await extract_facts(raw_text, doc.doc_type, doc.original_filename)
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
