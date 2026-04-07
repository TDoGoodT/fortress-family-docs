"""Fortress standalone LLM dispatch helper.

Provides a simple Bedrock-primary / Ollama-fallback generate function
for use by document processing services (classifier, fact extractor, summarizer)
and ChatSkill.

Returns empty string on total failure — callers must handle empty string
as a signal to skip LLM-dependent output.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def llm_generate(
    prompt: str,
    system_prompt: str,
    model_tier: str = "lite",
    task_type: str | None = None,
) -> str:
    """Generate text via Bedrock (primary) with Ollama fallback.

    Args:
        prompt: The user prompt.
        system_prompt: The system/instruction prompt.
        model_tier: Bedrock model tier — "micro", "lite", "haiku", or "sonnet".
            Used when task_type is not provided.
        task_type: Task type for select_model() routing (e.g. "chat", "agent").
            When provided, takes priority over model_tier.

    Returns:
        Generated text string, or empty string on total failure.
        Callers are responsible for handling empty string (skip LLM output).
    """
    # Resolve model_id — task_type takes priority over model_tier
    from src.services.model_selector import get_model_id, resolve_tier, select_model
    if task_type is not None:
        model_id = select_model(task_type)
    else:
        model_id = get_model_id(resolve_tier(model_tier))

    # Primary: Bedrock
    try:
        from src.services.bedrock_client import BedrockClient
        bedrock = BedrockClient()
        result = await bedrock.generate(prompt, system_prompt, model=model_id)
        if result and result.strip():
            from src.services.bedrock_client import HEBREW_FALLBACK
            if result != HEBREW_FALLBACK:
                logger.debug("llm_dispatch: bedrock success tier=%s len=%d", model_tier, len(result))
                return result
    except Exception as exc:
        logger.warning("llm_dispatch: bedrock failed tier=%s error=%s: %s", model_tier, type(exc).__name__, exc)

    # Fallback: Ollama (local)
    try:
        from src.services.llm_client import OllamaClient, HEBREW_FALLBACK as OLLAMA_FALLBACK
        ollama = OllamaClient()
        result = await ollama.generate(prompt, system_prompt)
        if result and result.strip() and result != OLLAMA_FALLBACK:
            logger.debug("llm_dispatch: ollama fallback success len=%d", len(result))
            return result
    except Exception as exc:
        logger.warning("llm_dispatch: ollama failed error=%s: %s", type(exc).__name__, exc)

    logger.error("llm_dispatch: all providers failed tier=%s", model_tier)
    return ""
