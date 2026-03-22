"""Fortress 2.0 Unified Handler — single LLM call for classify + respond."""

import json
import logging
import re
import time

from src.prompts.personality import TEMPLATES as _PERSONALITY_TEMPLATES
from src.prompts.system_prompts import UNIFIED_CLASSIFY_AND_RESPOND
from src.services.intent_detector import VALID_INTENTS
from src.services.model_dispatch import ModelDispatcher

logger = logging.getLogger(__name__)

HEBREW_FALLBACK_MSG = _PERSONALITY_TEMPLATES["error_fallback"]


def _heal_json(raw: str) -> dict | None:
    """Attempt to extract valid JSON from LLM output.

    Strategies (in order):
    1. Direct parse
    2. Strip markdown code blocks
    3. Find JSON substring with regex
    4. Find first { to last }

    Returns parsed dict or None if all strategies fail.
    """
    if not raw or not raw.strip():
        return None

    text = raw.strip()

    # Strategy 1: Direct parse
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            logger.debug("JSON healing: strategy 1 (direct parse) succeeded")
            return result
    except (json.JSONDecodeError, ValueError):
        pass

    # Strategy 2: Strip markdown ```json ... ``` or ``` ... ```
    md_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if md_match:
        try:
            result = json.loads(md_match.group(1).strip())
            if isinstance(result, dict):
                logger.debug("JSON healing: strategy 2 (markdown strip) succeeded")
                return result
        except (json.JSONDecodeError, ValueError):
            pass

    # Strategy 3: Find JSON object with regex
    json_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
    if json_match:
        try:
            result = json.loads(json_match.group(0))
            if isinstance(result, dict):
                logger.debug("JSON healing: strategy 3 (regex extraction) succeeded")
                return result
        except (json.JSONDecodeError, ValueError):
            pass

    # Strategy 4: First { to last }
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        try:
            result = json.loads(text[first_brace : last_brace + 1])
            if isinstance(result, dict):
                logger.debug("JSON healing: strategy 4 (brace matching) succeeded")
                return result
        except (json.JSONDecodeError, ValueError):
            pass

    logger.warning("JSON healing failed for: %s", text[:200])
    return None


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

        prompt = f"שם המשתמש: {member_name}\n{memory_context}\nהודעה: {message_text}\n\nחשוב: החזר JSON בלבד. בלי markdown, בלי הסברים."

        raw = await dispatcher.dispatch(
            prompt=prompt,
            system_prompt=UNIFIED_CLASSIFY_AND_RESPOND,
            intent="needs_llm",
        )

        logger.info("LLM raw output (%d chars): %s", len(raw) if raw else 0, (raw or "")[:200])

        # Try to parse structured response
        data = _heal_json(raw)
        logger.info("JSON healing result: %s", "success" if data else "failed")

        if data and "intent" in data:
            intent = data.get("intent", "").strip().lower()
            response_text = data.get("response", raw)
            task_data = data.get("task_data") if intent == "create_task" else None
            recurring_data = data.get("recurring_data") if intent == "create_recurring" else None
            delete_target = data.get("delete_target") if intent == "delete_task" else None

            if intent not in VALID_INTENTS:
                logger.warning("Unified handler: invalid intent '%s', defaulting to unknown", intent)
                intent = "unknown"

            # Embed delete_target in task_data for workflow state
            if delete_target is not None:
                task_data = {"delete_target": delete_target}

            # Embed recurring_data in task_data for workflow state
            if recurring_data is not None:
                task_data = {"recurring_data": recurring_data}

            elapsed = time.monotonic() - start
            logger.info(
                "Final decision: intent=%s response_len=%d source=structured elapsed=%.1fs",
                intent, len(response_text), elapsed,
            )
            return intent, response_text, task_data

        # JSON healing failed — but we might have a valid text response
        if raw and raw.strip() and raw.strip() != HEBREW_FALLBACK_MSG:
            elapsed = time.monotonic() - start
            logger.info(
                "Final decision: intent=unknown response_len=%d source=raw_text elapsed=%.1fs",
                len(raw.strip()), elapsed,
            )
            return "unknown", raw.strip(), None

        # Total failure
        elapsed = time.monotonic() - start
        logger.warning(
            "Final decision: intent=unknown source=empty_fallback elapsed=%.1fs", elapsed,
        )
        return "unknown", HEBREW_FALLBACK_MSG, None

    except Exception:
        elapsed = time.monotonic() - start
        logger.exception("Unified handler: unexpected error, elapsed=%.1fs", elapsed)
        return "unknown", HEBREW_FALLBACK_MSG, None
