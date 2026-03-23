"""Fortress Skills — registers built-in skills at import time."""

from src.skills.registry import registry
from src.skills.system_skill import SystemSkill

# Register built-in skills
registry.register(SystemSkill())

# Future skills will be registered here:
# from src.skills.task_skill import TaskSkill
# registry.register(TaskSkill())
