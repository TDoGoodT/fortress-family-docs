"""Fortress Skills Engine — deterministic command parser. Zero LLM calls."""

from __future__ import annotations

import re
import logging

from src.skills.base_skill import Command
from src.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)

# Hebrew cancel patterns — whole-message match
CANCEL_PATTERNS: list[re.Pattern] = [
    re.compile(r"^(לא|עזוב|תעזוב|בטל|תבטל|ביטול|cancel)$", re.IGNORECASE),
]

# Hebrew confirmation patterns — whole-message match
CONFIRM_PATTERNS: list[re.Pattern] = [
    re.compile(r"^(כן|yes|אישור|אשר|ok|בטח|אוקיי|אוקי)$", re.IGNORECASE),
]


def parse_command(
    message: str | None,
    skill_registry: SkillRegistry,
    *,
    has_media: bool = False,
    media_file_path: str | None = None,
) -> Command | None:
    """Match message against skill patterns. Returns Command or None for LLM fallback.

    Priority order:
    1. Media messages
    2. Cancel patterns
    3. Confirmation patterns
    4. Skill command patterns (from registry)
    5. None (LLM fallback)
    """
    # 1. Media — highest priority
    if has_media:
        logger.info(
            "parse_command: media route selected has_media=%s media_file_path_present=%s",
            has_media,
            bool(media_file_path),
        )
        return Command(
            skill="document",
            action="save",
            params={"media_file_path": media_file_path},
        )

    if not isinstance(message, str):
        return None

    stripped = message.strip()

    # 2. Cancel
    for pattern in CANCEL_PATTERNS:
        if pattern.match(stripped):
            return Command(skill="system", action="cancel")

    # 3. Confirm
    for pattern in CONFIRM_PATTERNS:
        if pattern.match(stripped):
            return Command(skill="system", action="confirm")

    # 4. Skill command patterns
    for pattern, action_name, skill in skill_registry.all_commands():
        m = pattern.search(stripped)
        if m:
            params = {k: v for k, v in m.groupdict().items() if v is not None}
            logger.info(
                "parse_command: matched skill=%s action=%s text=%s",
                skill.name,
                action_name,
                stripped[:120],
            )
            return Command(skill=skill.name, action=action_name, params=params, raw_text=stripped)

    # 5. LLM fallback
    return None
