from __future__ import annotations
"""Fortress 2.0 health router — liveness / readiness probe."""

from fastapi import APIRouter

from src.config import OPENROUTER_API_KEY
from src.database import test_connection
from src.services.bedrock_client import BedrockClient
from src.services.llm_client import OllamaClient
from src.services.openrouter_client import OpenRouterClient

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    """Return service health including database, Ollama, Bedrock, and OpenRouter connectivity."""
    db_ok = test_connection()

    llm = OllamaClient()
    ollama_ok, model_name = await llm.is_available()

    bedrock = BedrockClient()
    bedrock_ok, bedrock_model = await bedrock.is_available()

    # OpenRouter check
    if not OPENROUTER_API_KEY:
        openrouter_status = "no_key"
        openrouter_model = "not configured"
    else:
        openrouter = OpenRouterClient()
        or_ok, or_model = await openrouter.is_available()
        openrouter_status = "connected" if or_ok else "disconnected"
        openrouter_model = or_model or "not available"

    return {
        "status": "ok",
        "service": "fortress",
        "version": "2.0.0",
        "database": "connected" if db_ok else "disconnected",
        "ollama": "connected" if ollama_ok else "disconnected",
        "ollama_model": model_name if model_name else "not loaded",
        "bedrock": "connected" if bedrock_ok else "disconnected",
        "bedrock_model": bedrock_model if bedrock_model else "not available",
        "openrouter": openrouter_status,
        "openrouter_model": openrouter_model,
    }
