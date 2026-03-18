"""Fortress 2.0 health router — liveness / readiness probe."""

from fastapi import APIRouter

from src.database import test_connection

router = APIRouter()


@router.get("/health")
def health() -> dict:
    """Return service health including database connectivity."""
    db_ok = test_connection()
    return {
        "status": "ok",
        "service": "fortress",
        "version": "2.0.0",
        "database": "connected" if db_ok else "disconnected",
    }
