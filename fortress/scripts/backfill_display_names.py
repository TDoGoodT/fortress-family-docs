#!/usr/bin/env python3
"""
Backfill display names for existing documents.

Queries all documents with display_name IS NULL and generates
a human-readable Hebrew display name using the document_namer service.

Usage:
    python scripts/backfill_display_names.py [--dry-run] [--deterministic-only]
"""

import argparse
import logging
import sys
from pathlib import Path

# Ensure fortress/src is importable when run from fortress/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database import SessionLocal
from src.models.schema import Document
from src.services.document_namer import generate_display_name

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("backfill_display_names")


def backfill(dry_run: bool = False, deterministic_only: bool = False) -> dict:
    """Backfill display_name for all documents where it is NULL.

    Returns a summary dict with total, success, and failed counts.
    """
    session = SessionLocal()
    total = 0
    success = 0
    failed = 0

    try:
        docs = session.query(Document).filter(Document.display_name.is_(None)).all()
        total = len(docs)
        logger.info("Found %d documents with NULL display_name", total)

        for doc in docs:
            try:
                name = generate_display_name(
                    doc_type=doc.doc_type,
                    vendor=doc.vendor,
                    doc_date=doc.doc_date,
                    ai_summary=doc.ai_summary,
                    use_llm=not deterministic_only,
                )

                if dry_run:
                    logger.info(
                        "[DRY RUN] doc %s -> %s", doc.id, name,
                    )
                else:
                    doc.display_name = name
                    session.commit()
                    logger.info("Updated doc %s -> %s", doc.id, name)

                success += 1

            except Exception as exc:
                session.rollback()
                failed += 1
                logger.error(
                    "Failed doc %s: %s: %s", doc.id, type(exc).__name__, exc,
                )

    finally:
        session.close()

    logger.info(
        "Backfill complete: total=%d success=%d failed=%d",
        total, success, failed,
    )
    return {"total": total, "success": success, "failed": failed}


def main():
    parser = argparse.ArgumentParser(
        description="Backfill display names for documents with NULL display_name.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log generated names without writing to the database.",
    )
    parser.add_argument(
        "--deterministic-only",
        action="store_true",
        help="Skip LLM refinement; use deterministic naming only.",
    )
    args = parser.parse_args()

    backfill(dry_run=args.dry_run, deterministic_only=args.deterministic_only)


if __name__ == "__main__":
    main()
