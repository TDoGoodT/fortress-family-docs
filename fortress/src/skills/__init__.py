"""Fortress Skills — registers built-in skills at import time."""

from src.skills.registry import registry
from src.skills.system_skill import SystemSkill
from src.skills.task_skill import TaskSkill
from src.skills.recurring_skill import RecurringSkill
from src.skills.document_skill import DocumentSkill
from src.skills.bug_skill import BugSkill
from src.skills.chat_skill import ChatSkill
from src.skills.memory_skill import MemorySkill
from src.skills.morning_skill import MorningSkill

# Register built-in skills
registry.register(SystemSkill())
registry.register(TaskSkill())
registry.register(RecurringSkill())

doc_skill = DocumentSkill()
registry.register(doc_skill)
registry._skills["media"] = doc_skill  # dual registration: "document" + "media"

registry.register(BugSkill())
registry.register(ChatSkill())
registry.register(MemorySkill())
registry.register(MorningSkill())
