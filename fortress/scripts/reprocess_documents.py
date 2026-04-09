"""Reprocess existing documents through the enhanced pipeline.

Re-runs text extraction (Google DocAI), classification, fact extraction,
and canonical record creation for all documents that were processed
with the old pipeline (tesseract/pdfplumber).

Usage: python -m scripts.reprocess_documents [--dry-run] [--doc-id UUID]
"""
import asyncio
import logging
import sys
from src.database import get_db
from src.models.schema import Document, DocumentFact, SalarySlip
from src.services.documents import process_document

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("reprocess")


def main():
    dry_run = "--dry-run" in sys.argv
    single_id = None
    for i, arg in enumerate(sys.argv):
        if arg == "--doc-id" and i + 1 < len(sys.argv):
            single_id = sys.argv[i + 1]

    db = next(get_db())

    if single_id:
        docs = db.query(Document).filter(Document.id == single_id).all()
    else:
        docs = db.query(Document).order_by(Document.created_at).all()

    logger.info("Found %d documents to reprocess (dry_run=%s)", len(docs), dry_run)

    # Filter to documents that have a file on disk
    reprocessable = []
    for doc in docs:
        if not doc.file_path:
            logger.info("SKIP %s (%s) — no file_path", doc.id, doc.original_filename)
            continue
        import os
        if not os.path.isfile(doc.file_path):
            logger.info("SKIP %s (%s) — file not found: %s", doc.id, doc.original_filename, doc.file_path)
            continue
        reprocessable.append(doc)

    logger.info("Reprocessable: %d / %d", len(reprocessable), len(docs))

    if dry_run:
        for doc in reprocessable:
            meta = doc.doc_metadata or {}
            processor = meta.get("processor_name", "unknown")
            method = meta.get("extraction_method", "unknown")
            logger.info("WOULD reprocess: %s (%s) type=%s processor=%s method=%s",
                        doc.id, doc.original_filename, doc.doc_type, processor, method)
        return

    # Reprocess each document
    success = 0
    failed = 0
    for i, doc in enumerate(reprocessable):
        logger.info("--- [%d/%d] Reprocessing %s (%s) ---",
                    i + 1, len(reprocessable), doc.id, doc.original_filename)
        try:
            # Delete old facts and canonical records
            db.query(DocumentFact).filter(DocumentFact.document_id == doc.id).delete()
            db.query(SalarySlip).filter(SalarySlip.document_id == doc.id).delete()
            # Also try utility bills
            try:
                from src.models.schema import UtilityBill
                db.query(UtilityBill).filter(UtilityBill.document_id == doc.id).delete()
            except Exception:
                pass
            db.delete(doc)
            db.commit()

            # Re-run the full pipeline
            new_doc = asyncio.run(
                process_document(db, doc.file_path, doc.uploaded_by, doc.source or "reprocess")
            )
            logger.info("OK %s → type=%s display=%s review=%s",
                        new_doc.id, new_doc.doc_type,
                        getattr(new_doc, "display_name", "?"),
                        new_doc.review_state)
            success += 1
        except Exception as exc:
            logger.error("FAIL %s (%s): %s: %s",
                         doc.id, doc.original_filename, type(exc).__name__, exc)
            failed += 1
            db.rollback()

    logger.info("=== DONE: %d success, %d failed, %d total ===", success, failed, len(reprocessable))


if __name__ == "__main__":
    main()
