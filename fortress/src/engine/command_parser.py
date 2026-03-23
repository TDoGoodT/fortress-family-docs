"""Fortress Skills Engine — deterministic command parser. Zero LLM calls."""

from __future__ import annotations

import re

from src.skills.base_skill import Command
from src.skills.registry import SkillRegistry

# Hebrew cancel patterns — whole-message match
CANCEL_PATTERNS: list[re.Pattern] = [
    re.compile(r"^(לא|עזוב|תעזוב|בטל|תבטל|ביטול|cancel)$", re.IGNORECASE),
]

# Hebrew confirmation patterns — whole-message match
CONFIRM_PATTERNS: list[re.Pattern] = [
    re.compile(r"^(כן|yes|אישור|אשר|ok|בטח|אוקיי|אוקי)$", re.IGNORECASE),
]


def parse_command(
    message: str,
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
        return Command(
            skill="media",
            action="save",
            params={"media_file_path": media_file_path},
        )

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
            return Command(skill=skill.name, action=action_name, params=params)

    # 5. LLM fallback
    return None
