"""Fortress 2.0 prompts package — system prompt templates."""

from src.prompts.personality import (
    GREETINGS,
    PERSONALITY,
    TEMPLATES,
    format_task_created,
    format_task_list,
    get_greeting,
)
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
    "GREETINGS",
    "INTENT_CLASSIFIER",
    "MEMORY_EXTRACTOR",
    "PERSONALITY",
    "TASK_EXTRACTOR",
    "TASK_EXTRACTOR_BEDROCK",
    "TASK_RESPONDER",
    "TEMPLATES",
    "format_task_created",
    "format_task_list",
    "get_greeting",
]
