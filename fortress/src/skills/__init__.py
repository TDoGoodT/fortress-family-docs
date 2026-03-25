"""Fortress Skills — registers built-in skills at import time."""

from src.skills.registry import registry
from src.skills.system_skill import SystemSkill
from src.skills.task_skill import TaskSkill
from src.skills.document_skill import DocumentSkill
from src.skills.bug_skill import BugSkill
from src.skills.chat_skill import ChatSkill

# MVP skills — deterministic, zero LLM
registry.register(SystemSkill())    # MVP ✅
registry.register(TaskSkill())      # MVP ✅

doc_skill = DocumentSkill()
registry.register(doc_skill)        # MVP ✅ (save only)
registry._skills["media"] = doc_skill  # dual registration: "document" + "media"

registry.register(BugSkill())       # MVP ✅
registry.register(ChatSkill())      # MVP ✅ (greet only — deterministic)

# TEMPORARILY DISABLED — re-enable after MVP is stable
# from src.skills.recurring_skill import RecurringSkill
# from src.skills.memory_skill import MemorySkill
# from src.skills.morning_skill import MorningSkill
# registry.register(RecurringSkill())
# registry.register(MemorySkill())
# registry.register(MorningSkill())
