"""Fortress Skills Engine — central skill registry."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.skills.base_skill import BaseSkill


class SkillRegistry:
    """Singleton holding all registered skill instances."""

    def __init__(self) -> None:
        self._skills: dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill) -> None:
        self._skills[skill.name] = skill

    def get(self, name: str) -> BaseSkill | None:
        return self._skills.get(name)

    def all_commands(self) -> list[tuple[re.Pattern, str, BaseSkill]]:
        """Flat list of (pattern, action_name, skill) across all skills."""
        result: list[tuple[re.Pattern, str, BaseSkill]] = []
        for skill in self._skills.values():
            for pattern, action in skill.commands:
                result.append((pattern, action, skill))
        return result

    def list_skills(self) -> list[BaseSkill]:
        return list(self._skills.values())


# Module-level singleton
registry = SkillRegistry()
