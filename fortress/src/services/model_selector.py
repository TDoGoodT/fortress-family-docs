"""Fortress dynamic model selector — config-driven 5-tier model routing.

Provides:
- MODEL_REGISTRY: 5-tier model registry with metadata (ModelEntry dataclass)
- TASK_TIERS: task-type → canonical tier mapping
- resolve_tier() / get_model_id(): tier name resolution with legacy support
- select_model(): returns a resolved model_id for a task type + optional session override
- detect_upgrade_trigger(): check if user message warrants a model upgrade
- get_session_tier() / set_session_tier() / clear_session_tier(): per-member model override
- record_task_signal() / check_downgrade_signals() / clear_task_tracking(): signal-based downgrade
- record_intent_group() / record_message_timestamp() / check_inactivity_timeout(): context tracking
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from src.config import (
    BEDROCK_HAIKU_MODEL,
    BEDROCK_LITE_MODEL,
    BEDROCK_MAX_MODEL,
    BEDROCK_MICRO_MODEL,
    BEDROCK_MODEL_REGISTRY,
    BEDROCK_SONNET_MODEL,
    TASK_TIER_MAP,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ModelEntry dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ModelEntry:
    """Immutable metadata for a single model tier."""
    tier_name: str
    model_id: str
    capabilities: tuple[str, ...]
    cost_tier: int
    display_name: str


# ---------------------------------------------------------------------------
# Legacy tier name mapping
# ---------------------------------------------------------------------------

LEGACY_TIER_MAP: dict[str, str] = {
    "micro": "economy",
    "lite": "standard",
    "haiku": "strong",
    "sonnet": "powerful",
}

# ---------------------------------------------------------------------------
# Built-in defaults for the 5-tier registry
# ---------------------------------------------------------------------------

_BUILTIN_DEFAULTS: dict[str, dict] = {
    "economy": {
        "model_id": "amazon.nova-micro-v1:0",
        "capabilities": (),
        "cost_tier": 1,
        "display_name": "Nova Micro",
    },
    "standard": {
        "model_id": "amazon.nova-lite-v1:0",
        "capabilities": ("hebrew",),
        "cost_tier": 2,
        "display_name": "Nova Lite",
    },
    "strong": {
        "model_id": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
        "capabilities": ("tool_calling", "hebrew"),
        "cost_tier": 3,
        "display_name": "Claude Haiku",
    },
    "powerful": {
        "model_id": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        "capabilities": ("tool_calling", "hebrew", "vision"),
        "cost_tier": 4,
        "display_name": "Claude Sonnet",
    },
    "max": {
        "model_id": "anthropic.claude-opus-4-6-v1",
        "capabilities": ("tool_calling", "hebrew", "vision"),
        "cost_tier": 5,
        "display_name": "Claude Opus",
    },
}

# ---------------------------------------------------------------------------
# Registry builder
# ---------------------------------------------------------------------------

def _build_registry() -> dict[str, ModelEntry]:
    """Build the model registry from config sources.

    Priority:
    1. BEDROCK_MODEL_REGISTRY env var (JSON string) — full override
    2. Legacy env vars (BEDROCK_MICRO_MODEL, etc.) — per-tier override
    3. Built-in defaults
    """
    # --- Try JSON override first ---
    json_str = BEDROCK_MODEL_REGISTRY
    if json_str:
        try:
            raw = json.loads(json_str)
            registry: dict[str, ModelEntry] = {}
            for tier_name, entry_data in raw.items():
                mid = entry_data.get("model_id")
                if not mid:
                    logger.error("model_selector: skipping tier %s — missing model_id", tier_name)
                    continue
                caps = entry_data.get("capabilities", [])
                registry[tier_name] = ModelEntry(
                    tier_name=tier_name,
                    model_id=mid,
                    capabilities=tuple(caps) if not isinstance(caps, tuple) else caps,
                    cost_tier=int(entry_data.get("cost_tier", 1)),
                    display_name=entry_data.get("display_name", tier_name),
                )
            if registry:
                logger.info("model_selector: loaded %d tiers from BEDROCK_MODEL_REGISTRY", len(registry))
                return registry
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.error("model_selector: malformed BEDROCK_MODEL_REGISTRY JSON — %s, using defaults", exc)

    # --- Build from legacy env vars + built-in defaults ---
    legacy_env_map = {
        "economy": BEDROCK_MICRO_MODEL,
        "standard": BEDROCK_LITE_MODEL,
        "strong": BEDROCK_HAIKU_MODEL,
        "powerful": BEDROCK_SONNET_MODEL,
        "max": BEDROCK_MAX_MODEL,
    }

    registry = {}
    for tier_name, defaults in _BUILTIN_DEFAULTS.items():
        model_id = legacy_env_map.get(tier_name) or defaults["model_id"]
        registry[tier_name] = ModelEntry(
            tier_name=tier_name,
            model_id=model_id,
            capabilities=defaults["capabilities"],
            cost_tier=defaults["cost_tier"],
            display_name=defaults["display_name"],
        )

    return registry


# Module-level singleton
MODEL_REGISTRY: dict[str, ModelEntry] = _build_registry()


# ---------------------------------------------------------------------------
# Task → default tier mapping (uses canonical tier names)
# ---------------------------------------------------------------------------

_DEFAULT_TASK_TIERS: dict[str, str] = {
    "classify": "economy",
    "chat": "standard",
    "chat_greeting": "standard",
    "chat_question": "strong",
    "agent": "strong",
    "fact_extraction": "strong",
    "document_summary": "standard",
}


def _build_task_tiers() -> dict[str, str]:
    """Build task-to-tier mapping, with optional TASK_TIER_MAP JSON override."""
    json_str = TASK_TIER_MAP
    if json_str:
        try:
            overrides = json.loads(json_str)
            if isinstance(overrides, dict):
                merged = dict(_DEFAULT_TASK_TIERS)
                merged.update(overrides)
                logger.info("model_selector: loaded %d task-tier overrides from TASK_TIER_MAP", len(overrides))
                return merged
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.error("model_selector: malformed TASK_TIER_MAP JSON — %s, using defaults", exc)
    return dict(_DEFAULT_TASK_TIERS)


TASK_TIERS: dict[str, str] = _build_task_tiers()


# ---------------------------------------------------------------------------
# Tier resolution and model ID lookup
# ---------------------------------------------------------------------------

def resolve_tier(name: str) -> str:
    """Map a legacy or canonical tier name to the canonical tier name.

    Unknown names are returned as-is.
    """
    return LEGACY_TIER_MAP.get(name, name)


def get_model_id(tier: str) -> str:
    """Return the Bedrock model_id for a canonical tier name.

    Falls back to the standard tier with a warning if the tier is not found.
    """
    entry = MODEL_REGISTRY.get(tier)
    if entry:
        return entry.model_id
    logger.warning("model_selector: unknown tier %r — falling back to standard", tier)
    return MODEL_REGISTRY["standard"].model_id


# ---------------------------------------------------------------------------
# Core selection
# ---------------------------------------------------------------------------

def select_model(task_type: str, session_tier: str | None = None) -> str:
    """Return a resolved model_id for the given task type.

    If *session_tier* is provided, it takes priority (resolved through
    resolve_tier → get_model_id).  Otherwise the task-to-tier mapping is used.
    Unknown task types fall back to the standard tier.
    """
    if session_tier:
        canonical = resolve_tier(session_tier)
        return get_model_id(canonical)

    tier = TASK_TIERS.get(task_type, "standard")
    canonical = resolve_tier(tier)
    return get_model_id(canonical)


# ---------------------------------------------------------------------------
# Upgrade triggers — patterns that suggest the user needs a stronger model
# ---------------------------------------------------------------------------

_UPGRADE_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    # (pattern, trigger_name, suggested_tier)
    (re.compile(r"(בנה|תבנה|לבנות|ליצור)\s+(כלי|יכולת|פיצ׳ר|פיצר|skill|tool)", re.IGNORECASE), "build_capability", "powerful"),
    (re.compile(r"(תתכנן|לתכנן|ארכיטקטורה|עיצוב מערכת|system design)", re.IGNORECASE), "planning", "powerful"),
    (re.compile(r"(רגשי|קשה לי|עצוב|מתוסכל|לא טוב לי|מרגיש|מרגישה)", re.IGNORECASE), "emotional", "powerful"),
    (re.compile(r"(נתח|תנתח|ניתוח|אנליזה|analyze|analysis)", re.IGNORECASE), "deep_analysis", "powerful"),
    (re.compile(r"(אסטרטגיה|תכנון ארוך טווח|roadmap|חזון)", re.IGNORECASE), "strategy", "powerful"),
    (re.compile(r"(debug|דיבאג|באג מורכב|תקלה מורכבת)", re.IGNORECASE), "complex_debug", "powerful"),
    (re.compile(r"(שפר|לשפר|אופטימיזציה|optimize|refactor|ריפקטור)", re.IGNORECASE), "optimization", "strong"),
]

# Confirmation keywords (user says yes to upgrade)
_CONFIRM_PATTERNS = re.compile(
    r"^(כן|בטח|יאללה|אישור|yes|sure|ok|אוקיי|בוא נעשה את זה|קדימה)$",
    re.IGNORECASE,
)

# Decline keywords
_DECLINE_PATTERNS = re.compile(
    r"^(לא|לא צריך|no|ביטול|cancel|עזוב|תשאר)$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Upgrade detection
# ---------------------------------------------------------------------------

def detect_upgrade_trigger(message: str) -> tuple[str | None, str | None, str | None]:
    """Check if a message should trigger a model upgrade suggestion.

    Returns (trigger_name, suggested_tier, upgrade_message) or (None, None, None).
    """
    text = (message or "").strip()
    if not text:
        return None, None, None

    for pattern, trigger_name, tier in _UPGRADE_PATTERNS:
        if pattern.search(text):
            entry = MODEL_REGISTRY.get(tier)
            display = entry.display_name if entry else tier
            upgrade_msg = (
                f"🔄 זיהיתי שהבקשה הזו דורשת חשיבה מעמיקה.\n"
                f"רוצה שאעבור למודל חזק יותר ({display})?\n"
                f"תגיד ״כן״ ונמשיך ברמה הגבוהה."
            )
            logger.info("model_selector: upgrade_trigger=%s suggested_tier=%s", trigger_name, tier)
            return trigger_name, tier, upgrade_msg

    return None, None, None


def is_upgrade_confirmation(message: str) -> bool:
    """Check if the message is a 'yes' to a pending model upgrade."""
    return bool(_CONFIRM_PATTERNS.match((message or "").strip()))


def is_upgrade_decline(message: str) -> bool:
    """Check if the message is a 'no' to a pending model upgrade."""
    return bool(_DECLINE_PATTERNS.match((message or "").strip()))


# ---------------------------------------------------------------------------
# Session tier — stored in ConversationState.context["model_tier_override"]
# ---------------------------------------------------------------------------

def get_session_tier(db: Session, member_id: UUID) -> str | None:
    """Read the current model tier override from conversation state."""
    from src.services.conversation_state import get_state
    state = get_state(db, member_id)
    ctx = state.context or {}
    return ctx.get("model_tier_override")


def set_session_tier(db: Session, member_id: UUID, tier: str | None) -> None:
    """Set or clear the model tier override in conversation state."""
    from src.services.conversation_state import get_state
    state = get_state(db, member_id)
    ctx = dict(state.context or {})
    if tier:
        ctx["model_tier_override"] = tier
        logger.info("model_selector: set_session_tier member=%s tier=%s", member_id, tier)
    else:
        ctx.pop("model_tier_override", None)
        logger.info("model_selector: cleared_session_tier member=%s", member_id)
    state.context = ctx
    db.flush()


def clear_session_tier(db: Session, member_id: UUID) -> None:
    """Clear the model tier override (revert to defaults)."""
    set_session_tier(db, member_id, None)


# ---------------------------------------------------------------------------
# Signal-based task tracking (replaces counter-based auto-downgrade)
# ---------------------------------------------------------------------------

def record_task_signal(db: Session, member_id: UUID, signal: str) -> None:
    """Record a task completion signal in ConversationState.context['last_task_signal']."""
    from src.services.conversation_state import get_state
    state = get_state(db, member_id)
    ctx = state.context or {}
    ctx["last_task_signal"] = signal
    state.context = ctx
    db.flush()


def record_intent_group(db: Session, member_id: UUID, intent_group: str) -> None:
    """Store current intent group in context['last_intent_group']."""
    from src.services.conversation_state import get_state
    state = get_state(db, member_id)
    ctx = state.context or {}
    ctx["last_intent_group"] = intent_group
    state.context = ctx
    db.flush()


def record_message_timestamp(db: Session, member_id: UUID) -> None:
    """Store current UTC timestamp in context['last_message_ts']."""
    from src.services.conversation_state import get_state
    from datetime import datetime, timezone
    state = get_state(db, member_id)
    ctx = state.context or {}
    ctx["last_message_ts"] = datetime.now(timezone.utc).isoformat()
    state.context = ctx
    db.flush()


def check_inactivity_timeout(db: Session, member_id: UUID) -> bool:
    """Return True if time since last_message_ts exceeds INACTIVITY_TIMEOUT_MINUTES."""
    from src.services.conversation_state import get_state
    from src.config import INACTIVITY_TIMEOUT_MINUTES
    from datetime import datetime, timezone
    state = get_state(db, member_id)
    ctx = state.context or {}
    last_ts = ctx.get("last_message_ts")
    if not last_ts:
        return False
    try:
        last_dt = datetime.fromisoformat(last_ts)
    except (ValueError, TypeError):
        logger.warning("model_selector: invalid last_message_ts=%s", last_ts)
        return False
    elapsed_minutes = (datetime.now(timezone.utc) - last_dt).total_seconds() / 60
    return elapsed_minutes > INACTIVITY_TIMEOUT_MINUTES


def check_downgrade_signals(db: Session, member_id: UUID) -> bool:
    """Return True if any downgrade signal is active."""
    from src.services.conversation_state import get_state
    state = get_state(db, member_id)
    ctx = state.context or {}
    signal = ctx.get("last_task_signal")
    return signal in {"post_tool_chat", "user_done", "topic_shift"}


def clear_task_tracking(db: Session, member_id: UUID) -> None:
    """Reset task tracking state from context."""
    from src.services.conversation_state import get_state
    state = get_state(db, member_id)
    ctx = state.context or {}
    ctx.pop("last_task_signal", None)
    ctx.pop("last_intent_group", None)
    state.context = ctx
    db.flush()
