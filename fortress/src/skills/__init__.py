"""Fortress Skills — registers built-in skills at import time."""

from src.skills.registry import registry
from src.skills.system_skill import SystemSkill
from src.skills.task_skill import TaskSkill
from src.skills.document_skill import DocumentSkill
from src.skills.bug_skill import BugSkill
from src.skills.chat_skill import ChatSkill
from src.skills.deploy_skill import DeploySkill

# MVP skills — deterministic, zero LLM
registry.register(DeploySkill())    # Remote deploy — must be before TaskSkill (exact trigger priority)
registry.register(SystemSkill())    # MVP ✅
registry.register(TaskSkill())      # MVP ✅

doc_skill = DocumentSkill()
registry.register(doc_skill)        # MVP ✅ (save only)
registry._skills["media"] = doc_skill  # dual registration: "document" + "media"

registry.register(BugSkill())       # MVP ✅
registry.register(ChatSkill())      # MVP ✅ (greet only — deterministic)

from src.skills.recurring_skill import RecurringSkill
from src.skills.morning_skill import MorningSkill
from src.skills.memory_skill import MemorySkill
from src.skills.fact_skill import FactSkill
registry.register(RecurringSkill())
registry.register(MorningSkill())
registry.register(MemorySkill())
registry.register(FactSkill())
