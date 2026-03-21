"""Fortress 2.0 Routing Policy — intent-based sensitivity routing for LLM providers."""

from typing import Literal

SensitivityLevel = Literal["low", "medium", "high"]
Provider = Literal["openrouter", "bedrock", "ollama"]

SENSITIVITY_MAP: dict[str, SensitivityLevel] = {
    "greeting": "low",
    "list_tasks": "medium",
    "create_task": "medium",
    "complete_task": "medium",
    "list_documents": "medium",
    "unknown": "medium",
    "ask_question": "high",
    "upload_document": "high",
    "needs_llm": "medium",
}

ROUTE_MAP: dict[SensitivityLevel, list[Provider]] = {
    "low": ["openrouter", "bedrock", "ollama"],
    "medium": ["openrouter", "bedrock", "ollama"],
    "high": ["bedrock", "ollama"],
}


def get_sensitivity(intent: str) -> SensitivityLevel:
    """Return the sensitivity level for an intent.

    Defaults to 'high' for unknown intents (fail-safe).
    """
    return SENSITIVITY_MAP.get(intent, "high")


def get_route(intent: str) -> list[Provider]:
    """Return the ordered provider list for an intent."""
    sensitivity = get_sensitivity(intent)
    return list(ROUTE_MAP[sensitivity])
