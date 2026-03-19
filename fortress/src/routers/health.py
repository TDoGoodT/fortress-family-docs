"""Fortress 2.0 health router — liveness / readiness probe."""

from fastapi import APIRouter

from src.database import test_connection
from src.services.llm_client import OllamaClient

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    """Return service health including database and Ollama connectivity."""
    db_ok = test_connection()

    llm = OllamaClient()
    ollama_ok, model_name = await llm.is_available()

    return {
        "status": "ok",
        "service": "fortress",
        "version": "2.0.0",
        "database": "connected" if db_ok else "disconnected",
        "ollama": "connected" if ollama_ok else "disconnected",
        "ollama_model": model_name if model_name else "not loaded",
    }
