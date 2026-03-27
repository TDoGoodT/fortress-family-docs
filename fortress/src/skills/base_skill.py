"""Fortress Skills Engine — base skill interface, Command and Result dataclasses."""

from __future__ import annotations

import re
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from src.models.schema import FamilyMember


@dataclass
class Command:
    """A parsed user message ready for skill dispatch."""

    skill: str
    action: str
    params: dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""


@dataclass
class Result:
    """The outcome of a skill execution."""

    success: bool
    message: str
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
    action: str | None = None
    data: dict[str, Any] | None = None


class BaseSkill(ABC):
    """Abstract base class that all Fortress skills must implement."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    @abstractmethod
    def commands(self) -> list[tuple[re.Pattern, str]]: ...

    @abstractmethod
    def execute(self, db: Session, member: FamilyMember, command: Command) -> Result: ...

    @abstractmethod
    def verify(self, db: Session, result: Result) -> bool: ...

    @abstractmethod
    def get_help(self) -> str: ...
