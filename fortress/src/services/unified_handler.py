"""Fortress 2.0 Unified Handler — single LLM call for classify + respond."""

import json
import logging
import time

from src.prompts.system_prompts import UNIFIED_CLASSIFY_AND_RESPOND
from src.services.intent_detector import VALID_INTENTS
from src.services.model_dispatch import ModelDispatcher

logger = logging.getLogger(__name__)

HEBREW_FALLBACK_MSG = "מצטער, לא הצלחתי לעבד את הבקשה. נסה שוב."


async def handle_with_llm(
    message_text: str,
    member_name: str,
    memories: list,
    dispatcher: ModelDispatcher,
) -> tuple[str, str, dict | None]:
    """Single LLM call: classify intent + generate response.

    Returns (intent, response_text, task_details_or_none).
    """
    start = time.monotonic()

    try:
        memory_context = ""
        if memories:
            memory_lines = [f"- {m.content}" for m in memories]
            memory_context = "\nזיכרונות רלוונטיים:\n" + "\n".join(memory_lines) + "\n"

        prompt = f"שם המשתמש: {member_name}\n{memory_context}\nהודעה: {message_text}"

        raw = await dispatcher.dispatch(
            prompt=prompt,
            system_prompt=UNIFIED_CLASSIFY_AND_RESPOND,
            intent="needs_llm",
        )

        data = json.loads(raw)
        intent = data.get("intent", "").strip().lower()
        response_text = data.get("response", "")
        task_data = data.get("task_data") if intent == "create_task" else None

        if intent not in VALID_INTENTS:
            logger.warning("Unified handler: invalid intent '%s', defaulting to unknown", intent)
            intent = "unknown"

        elapsed = time.monotonic() - start
        logger.info(
            "Unified handler: intent=%s response_len=%d elapsed=%.1fs",
            intent, len(response_text), elapsed,
        )
        return intent, response_text, task_data

    except (json.JSONDecodeError, AttributeError, TypeError):
        elapsed = time.monotonic() - start
        logger.warning("Unified handler: invalid JSON, elapsed=%.1fs", elapsed)
        return "unknown", HEBREW_FALLBACK_MSG, None
    except Exception:
        elapsed = time.monotonic() - start
        logger.exception("Unified handler: unexpected error, elapsed=%.1fs", elapsed)
        return "unknown", HEBREW_FALLBACK_MSG, None
