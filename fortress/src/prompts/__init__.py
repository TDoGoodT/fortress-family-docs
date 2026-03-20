"""Fortress 2.0 prompts package — system prompt templates."""

from src.prompts.system_prompts import (
    FORTRESS_BASE,
    INTENT_CLASSIFIER,
    MEMORY_EXTRACTOR,
    TASK_EXTRACTOR,
    TASK_EXTRACTOR_BEDROCK,
    TASK_RESPONDER,
)

__all__ = [
    "FORTRESS_BASE",
    "INTENT_CLASSIFIER",
    "MEMORY_EXTRACTOR",
    "TASK_EXTRACTOR",
    "TASK_EXTRACTOR_BEDROCK",
    "TASK_RESPONDER",
]
