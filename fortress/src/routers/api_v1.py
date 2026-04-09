"""Fortress Data Access API v1 — REST endpoints for agents.

Every request must include X-Agent-Id and X-Agent-Role headers.
Fortress validates the role against the permission matrix before returning data.
"""
from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, File, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.api.data_access import (
    PermissionDenied,
    get_contracts,
    get_document_by_id,
    get_documents,
    get_insurance_policies,
    get_library_stats,
    get_salary_slips,
    get_utility_bills,
    search_facts,
)
from src.api.permissions import get_accessible_tables, get_role_permissions
from src.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["data-access"])


def _require_agent_headers(
    x_agent_id: str = Header(..., alias="X-Agent-Id"),
    x_agent_role: str = Header(..., alias="X-Agent-Role"),
) -> tuple[str, str]:
    """Extract and validate agent identity headers."""
    if not x_agent_id or not x_agent_role:
        raise HTTPException(status_code=401, detail="Missing agent identity headers")
    return x_agent_id, x_agent_role


def _handle_permission_error(exc: PermissionDenied) -> None:
    raise HTTPException(
        status_code=403,
        detail=f"Agent '{exc.agent_role}' lacks '{exc.required}' access to '{exc.table}'",
    )


# ── Introspection ────────────────────────────────────────────────────────

@router.get("/whoami")
def whoami(
    agent: tuple[str, str] = Depends(_require_agent_headers),
) -> dict[str, Any]:
    """Return the agent's identity and permissions."""
    agent_id, agent_role = agent
    return {
        "agent_id": agent_id,
        "agent_role": agent_role,
        "permissions": get_role_permissions(agent_role),
        "accessible_tables": get_accessible_tables(agent_role),
    }


# ── Library Stats ────────────────────────────────────────────────────────

@router.get("/stats")
def stats(
    db: Session = Depends(get_db),
    agent: tuple[str, str] = Depends(_require_agent_headers),
) -> dict[str, Any]:
    """Get high-level library statistics."""
    _, agent_role = agent
    try:
        return get_library_stats(db, agent_role)
    except PermissionDenied as exc:
        _handle_permission_error(exc)


# ── Documents ────────────────────────────────────────────────────────────

@router.get("/documents")
def list_documents(
    doc_type: Optional[str] = Query(None),
    vendor: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    review_state: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    agent: tuple[str, str] = Depends(_require_agent_headers),
) -> list[dict[str, Any]]:
    """List documents with optional filters."""
    _, agent_role = agent
    try:
        return get_documents(
            db, agent_role,
            doc_type=doc_type, vendor=vendor, tag=tag,
            review_state=review_state, limit=limit, offset=offset,
        )
    except PermissionDenied as exc:
        _handle_permission_error(exc)


@router.get("/documents/{doc_id}")
def get_document(
    doc_id: UUID,
    db: Session = Depends(get_db),
    agent: tuple[str, str] = Depends(_require_agent_headers),
) -> dict[str, Any]:
    """Get a single document by ID."""
    _, agent_role = agent
    try:
        result = get_document_by_id(db, agent_role, doc_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Document not found")
        return result
    except PermissionDenied as exc:
        _handle_permission_error(exc)


# ── Facts ────────────────────────────────────────────────────────────────

@router.get("/facts")
def list_facts(
    fact_key: Optional[str] = Query(None),
    fact_type: Optional[str] = Query(None),
    q: Optional[str] = Query(None, alias="query"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    agent: tuple[str, str] = Depends(_require_agent_headers),
) -> list[dict[str, Any]]:
    """Search extracted facts."""
    _, agent_role = agent
    try:
        return search_facts(
            db, agent_role,
            fact_key=fact_key, fact_type=fact_type, query_text=q, limit=limit,
        )
    except PermissionDenied as exc:
        _handle_permission_error(exc)


# ── Salary Slips ─────────────────────────────────────────────────────────

@router.get("/salary-slips")
def list_salary_slips(
    year: Optional[int] = Query(None),
    employer: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    agent: tuple[str, str] = Depends(_require_agent_headers),
) -> list[dict[str, Any]]:
    """Get salary slip records."""
    _, agent_role = agent
    try:
        return get_salary_slips(db, agent_role, year=year, employer=employer, limit=limit)
    except PermissionDenied as exc:
        _handle_permission_error(exc)


# ── Utility Bills ────────────────────────────────────────────────────────

@router.get("/utility-bills")
def list_utility_bills(
    service_type: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    agent: tuple[str, str] = Depends(_require_agent_headers),
) -> list[dict[str, Any]]:
    """Get utility bill records."""
    _, agent_role = agent
    try:
        return get_utility_bills(db, agent_role, service_type=service_type, provider=provider, limit=limit)
    except PermissionDenied as exc:
        _handle_permission_error(exc)


# ── Contracts ────────────────────────────────────────────────────────────

@router.get("/contracts")
def list_contracts(
    active_only: bool = Query(False),
    contract_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    agent: tuple[str, str] = Depends(_require_agent_headers),
) -> list[dict[str, Any]]:
    """Get contract records."""
    _, agent_role = agent
    try:
        return get_contracts(db, agent_role, active_only=active_only, contract_type=contract_type, limit=limit)
    except PermissionDenied as exc:
        _handle_permission_error(exc)


# ── Insurance Policies ───────────────────────────────────────────────────

@router.get("/insurance-policies")
def list_insurance_policies(
    active_only: bool = Query(False),
    insurance_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    agent: tuple[str, str] = Depends(_require_agent_headers),
) -> list[dict[str, Any]]:
    """Get insurance policy records."""
    _, agent_role = agent
    try:
        return get_insurance_policies(db, agent_role, active_only=active_only, insurance_type=insurance_type, limit=limit)
    except PermissionDenied as exc:
        _handle_permission_error(exc)


# ── Document Ingestion ───────────────────────────────────────────────────

@router.post("/ingest")
async def ingest_document(
    file: UploadFile = File(...),
    source: str = Query("api", description="Ingestion source channel"),
    uploaded_by_phone: Optional[str] = Query(None, description="Phone number of the uploader"),
    db: Session = Depends(get_db),
    agent: tuple[str, str] = Depends(_require_agent_headers),
) -> dict[str, Any]:
    """Submit a document for processing through the full pipeline.

    The file is saved to storage, then processed through:
    OCR → Classification → Fact Extraction → Canonical Table Persist.

    Returns the processed document metadata.
    """
    agent_id, agent_role = agent

    # Only librarian and orchestrator can ingest
    from src.api.permissions import check_access, AccessLevel
    if not check_access(agent_role, "documents", AccessLevel.WRITE):
        raise HTTPException(
            status_code=403,
            detail=f"Agent '{agent_role}' lacks 'write' access to 'documents'",
        )

    import os
    import tempfile
    from src.services.documents import process_document
    from src.models.schema import FamilyMember

    # Resolve uploader — default to first admin if no phone provided
    uploader = None
    if uploaded_by_phone:
        from src.utils.phone import normalize_phone
        phone = normalize_phone(uploaded_by_phone)
        uploader = db.query(FamilyMember).filter(FamilyMember.phone == phone).first()
    if uploader is None:
        uploader = db.query(FamilyMember).filter(FamilyMember.is_admin == True).first()
    if uploader is None:
        raise HTTPException(status_code=400, detail="No valid uploader found")

    # Save uploaded file to temp location
    suffix = os.path.splitext(file.filename or "document")[1] or ".pdf"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        doc = await process_document(db, tmp_path, uploader.id, source)

        # Check for duplicate
        if hasattr(doc, "_is_duplicate") and doc._is_duplicate:
            return {
                "status": "duplicate",
                "document_id": str(doc.id),
                "display_name": doc.display_name,
                "message": "Document already exists in the library",
            }

        return {
            "status": "processed",
            "document_id": str(doc.id),
            "doc_type": doc.doc_type,
            "display_name": doc.display_name,
            "review_state": doc.review_state,
            "facts_count": len(doc.facts) if doc.facts else 0,
        }
    except Exception as exc:
        logger.error("ingest: pipeline failed: %s: %s", type(exc).__name__, exc)
        raise HTTPException(status_code=500, detail=f"Pipeline error: {type(exc).__name__}")
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
