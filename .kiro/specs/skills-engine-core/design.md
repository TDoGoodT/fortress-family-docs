# Design Document: Skills Engine Core

## Overview

The Skills Engine replaces the LLM-first message processing pipeline with a deterministic, regex-based command dispatch system. Instead of routing every WhatsApp message through an LLM for intent detection, the engine matches messages against registered skill patterns and executes them directly via database operations and personality templates.

The pipeline flow is: **auth → parse → execute → verify → state update → audit → format → respond**.

Messages that don't match any skill pattern fall back to the existing LLM pipeline (`workflow_engine.run_workflow`). The old pipeline files are preserved but no longer imported by the new message handler.

### Key Design Decisions

1. **Dataclasses over dicts**: `Command` and `Result` are typed dataclasses, not raw dicts. This gives us IDE support, type checking, and clear contracts.
2. **Singleton registry**: Skills register at import time into a module-level singleton. No DI framework needed.
3. **Sync execute, async handler**: Skill `execute()` methods are synchronous (DB operations only). The message handler remains async to match the existing FastAPI signature and LLM fallback path.
4. **Verify after execute**: Every successful skill execution with an entity_id is verified against the DB before returning. This catches silent write failures.
5. **No property-based tests**: Per project constraints, all tests are unit tests with specific examples and edge cases.

## Architecture

The system introduces two new packages under `fortress/src/`:

```
fortress/src/
├── skills/                    # Skill definitions
│   ├── __init__.py            # Registers SystemSkill into registry
│   ├── base_skill.py          # Command, Result, BaseSkill ABC
│   ├── registry.py            # SkillRegistry singleton
│   └── system_skill.py        # cancel/confirm/help skill
├── engine/                    # Processing pipeline
│   ├── __init__.py            # Empty package init
│   ├── command_parser.py      # Regex matching, priority ordering
│   ├── executor.py            # dispatch → verify → state → audit
│   └── response_formatter.py  # WhatsApp truncation
└── services/
    └── message_handler.py     # Updated: auth → parse → execute → format
```

### Data Flow

```
WhatsApp message
    │
    ▼
message_handler.handle_incoming_message(db, phone, text, msg_id, has_media, media_path)
    │
    ├─ auth: get_family_member_by_phone(db, phone)
    │   ├─ None → return TEMPLATES["unknown_member"]
    │   └─ inactive → return TEMPLATES["inactive_member"]
    │
    ├─ parse: parse_command(text, registry, has_media)
    │   ├─ has_media → Command(skill="media", action="save")
    │   ├─ cancel pattern → Command(skill="system", action="cancel")
    │   ├─ confirm pattern → Command(skill="system", action="confirm")
    │   ├─ skill pattern → Command(skill=X, action=Y, params={...})
    │   └─ no match → None (LLM fallback)
    │
    ├─ if Command:
    │   ├─ execute: executor.execute(db, member, command)
    │   │   ├─ registry.get(command.skill).execute(db, member, command)
    │   │   ├─ verify (if entity_id): skill.verify(db, result)
    │   │   ├─ state: update_state / clear_state
    │   │   └─ audit: log_action (if entity_id)
    │   └─ format: format_response(result) → truncate if >3500 chars
    │
    ├─ if None:
    │   └─ fallback: run_workflow(db, member, phone, text, ...)
    │
    └─ save: Conversation(member_id, text, response, intent)
```

## Components and Interfaces

### 1. `src/skills/base_skill.py` — Command, Result, BaseSkill

```python
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
    """Abstract base class that all skills must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique string identifier for this skill."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of this skill."""
        ...

    @property
    @abstractmethod
    def commands(self) -> list[tuple[re.Pattern, str]]:
        """List of (compiled_regex, action_name) tuples this skill handles."""
        ...

    @abstractmethod
    def execute(self, db: Session, member: FamilyMember, command: Command) -> Result:
        """Execute the command and return a Result. Synchronous — DB ops only."""
        ...

    @abstractmethod
    def verify(self, db: Session, result: Result) -> bool:
        """Verify the action persisted in the database. Return True if OK."""
        ...

    @abstractmethod
    def get_help(self) -> str:
        """Return a Hebrew help string describing available commands."""
        ...
```

### 2. `src/skills/registry.py` — SkillRegistry

```python
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
        """Register a skill indexed by its name."""
        self._skills[skill.name] = skill

    def get(self, name: str) -> BaseSkill | None:
        """Return the skill for the given name, or None."""
        return self._skills.get(name)

    def all_commands(self) -> list[tuple[re.Pattern, str, BaseSkill]]:
        """Flat list of (pattern, action_name, skill) across all skills."""
        result = []
        for skill in self._skills.values():
            for pattern, action in skill.commands:
                result.append((pattern, action, skill))
        return result

    def list_skills(self) -> list[BaseSkill]:
        """Return all registered skill instances."""
        return list(self._skills.values())


# Module-level singleton
registry = SkillRegistry()
```

### 3. `src/engine/command_parser.py` — Deterministic Command Parser

```python
from __future__ import annotations

import re

from src.skills.base_skill import Command
from src.skills.registry import SkillRegistry

# Hebrew cancel patterns — matched as whole-message (stripped, case-insensitive)
CANCEL_PATTERNS: list[re.Pattern] = [
    re.compile(r"^(לא|עזוב|תעזוב|בטל|תבטל|ביטול|cancel)$", re.IGNORECASE),
]

# Hebrew confirmation patterns
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
    4. Skill command patterns
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

    # 4. Skill command patterns (from registry)
    for pattern, action_name, skill in skill_registry.all_commands():
        m = pattern.search(stripped)
        if m:
            params = {k: v for k, v in m.groupdict().items() if v is not None}
            return Command(skill=skill.name, action=action_name, params=params)

    # 5. LLM fallback
    return None
```

### 4. `src/engine/executor.py` — Executor

```python
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from src.models.schema import FamilyMember
from src.prompts.personality import TEMPLATES as PERSONALITY_TEMPLATES
from src.services.audit import log_action
from src.services.conversation_state import (
    clear_state,
    resolve_pending,
    update_state,
)
from src.skills.base_skill import Command, Result
from src.skills.registry import registry

logger = logging.getLogger(__name__)


def execute(db: Session, member: FamilyMember, command: Command) -> Result:
    """Execute a parsed command through the skill pipeline.

    Pipeline: dispatch → verify → state update → audit → result
    """
    try:
        # 1. Look up skill
        skill = registry.get(command.skill)
        if skill is None:
            return Result(
                success=False,
                message=PERSONALITY_TEMPLATES["error_fallback"],
            )

        # 2. Handle confirmation re-dispatch
        if command.action == "confirm":
            return _handle_confirm(db, member, skill, command)

        # 3. Execute
        result = skill.execute(db, member, command)

        # 4. Cancel → clear state
        if command.action == "cancel":
            clear_state(db, member.id)
            return result

        # 5. Verify (if successful with entity_id)
        if result.success and result.entity_id is not None:
            verified = skill.verify(db, result)
            if not verified:
                result = Result(
                    success=False,
                    message=PERSONALITY_TEMPLATES["verification_failed"],
                    entity_type=result.entity_type,
                    entity_id=result.entity_id,
                    action=result.action,
                )
                return result

        # 6. Update state
        if result.success:
            update_state(
                db,
                member.id,
                intent=command.skill,
                entity_type=result.entity_type,
                entity_id=result.entity_id,
                action=result.action,
            )

        # 7. Audit (if entity_id)
        if result.success and result.entity_id is not None:
            log_action(
                db,
                actor_id=member.id,
                action=result.action or command.action,
                resource_type=result.entity_type,
                resource_id=result.entity_id,
            )

        return result

    except Exception:
        logger.exception(
            "Executor error: skill=%s action=%s member=%s",
            command.skill,
            command.action,
            member.name,
        )
        db.rollback()
        return Result(
            success=False,
            message=PERSONALITY_TEMPLATES["error_fallback"],
        )


def _handle_confirm(
    db: Session, member: FamilyMember, skill, command: Command
) -> Result:
    """Handle confirmation by resolving pending action and re-dispatching."""
    pending = resolve_pending(db, member.id)
    if pending is None:
        return Result(
            success=False,
            message="אין פעולה ממתינה לאישור 🤷",
        )

    # The system skill returns the pending data; the executor re-dispatches
    result = skill.execute(db, member, command)

    # If the result contains pending data, re-dispatch to the target skill
    if result.data and "pending_action" in result.data:
        pending_data = result.data["pending_action"]
        action_type = pending_data.get("type", "")
        target_skill = registry.get(action_type.split("_")[0] if "_" in action_type else action_type)
        if target_skill:
            redispatch_command = Command(
                skill=target_skill.name,
                action=action_type,
                params=pending_data.get("data", {}),
            )
            return execute(db, member, redispatch_command)

    return result
```

### 5. `src/engine/response_formatter.py` — Response Formatter

```python
from __future__ import annotations

from src.skills.base_skill import Result

WHATSAPP_CHAR_LIMIT = 3500
TRUNCATION_INDICATOR = "\n\n... (הודעה קוצרה)"


def format_response(result: Result) -> str:
    """Format a Result into a WhatsApp-safe string.

    Truncates at ~3500 characters if needed.
    """
    message = result.message

    if len(message) > WHATSAPP_CHAR_LIMIT:
        return message[:WHATSAPP_CHAR_LIMIT] + TRUNCATION_INDICATOR

    return message
```

### 6. `src/skills/system_skill.py` — System Skill

```python
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from src.models.schema import FamilyMember
from src.prompts.personality import TEMPLATES as PERSONALITY_TEMPLATES
from src.services.conversation_state import clear_state, get_state, resolve_pending
from src.skills.base_skill import BaseSkill, Command, Result


class SystemSkill(BaseSkill):
    """Built-in skill for cancel, confirm, and help commands."""

    @property
    def name(self) -> str:
        return "system"

    @property
    def description(self) -> str:
        return "פקודות מערכת: ביטול, אישור, עזרה"

    @property
    def commands(self) -> list[tuple[re.Pattern, str]]:
        # Cancel/confirm are handled by command_parser priority patterns,
        # not by skill-level regex. Help is matched here.
        return [
            (re.compile(r"^(עזרה|help|פקודות)$", re.IGNORECASE), "help"),
        ]

    def execute(self, db: Session, member: FamilyMember, command: Command) -> Result:
        if command.action == "cancel":
            return self._cancel(db, member)
        elif command.action == "confirm":
            return self._confirm(db, member)
        elif command.action == "help":
            return self._help()
        return Result(success=False, message=PERSONALITY_TEMPLATES["error_fallback"])

    def verify(self, db: Session, result: Result) -> bool:
        # System commands don't create DB entities
        return True

    def get_help(self) -> str:
        return "ביטול — ביטול פעולה ממתינה\nאישור — אישור פעולה ממתינה\nעזרה — הצגת פקודות זמינות"

    def _cancel(self, db: Session, member: FamilyMember) -> Result:
        clear_state(db, member.id)
        return Result(
            success=True,
            message=PERSONALITY_TEMPLATES["cancelled"],
            action="cancel",
        )

    def _confirm(self, db: Session, member: FamilyMember) -> Result:
        state = get_state(db, member.id)
        if not state.pending_confirmation:
            return Result(
                success=False,
                message="אין פעולה ממתינה לאישור 🤷",
            )
        pending = resolve_pending(db, member.id)
        return Result(
            success=True,
            message="",  # Executor will re-dispatch
            action="confirm",
            data={"pending_action": pending},
        )

    def _help(self) -> Result:
        from src.skills.registry import registry

        lines = ["📋 פקודות זמינות:\n"]
        for skill in registry.list_skills():
            lines.append(f"▸ {skill.description}")
            lines.append(f"  {skill.get_help()}\n")
        return Result(success=True, message="\n".join(lines), action="help")
```

### 7. `src/services/message_handler.py` — Updated Message Handler

```python
"""Fortress message handler — auth → parse → execute → format."""

import logging

from sqlalchemy.orm import Session

from src.models.schema import Conversation
from src.prompts.personality import TEMPLATES as PERSONALITY_TEMPLATES
from src.services.auth import get_family_member_by_phone
from src.engine.command_parser import parse_command
from src.engine.executor import execute
from src.engine.response_formatter import format_response
from src.skills.registry import registry

logger = logging.getLogger(__name__)


async def handle_incoming_message(
    db: Session,
    phone: str,
    message_text: str,
    message_id: str,
    *,
    has_media: bool = False,
    media_file_path: str | None = None,
) -> str:
    """Authenticate sender and process via Skills Engine or LLM fallback."""
    member = get_family_member_by_phone(db, phone)

    if member is None:
        response = PERSONALITY_TEMPLATES["unknown_member"]
        _save_conversation(db, None, message_text, response, "unknown_sender")
        return response

    if not member.is_active:
        response = PERSONALITY_TEMPLATES["inactive_member"]
        _save_conversation(db, member.id, message_text, response, "inactive_member")
        return response

    # Parse
    command = parse_command(
        message_text, registry, has_media=has_media, media_file_path=media_file_path
    )

    if command is not None:
        # Skills Engine path
        result = execute(db, member, command)
        response = format_response(result)
        intent = f"{command.skill}.{command.action}"
    else:
        # LLM fallback — delegate to existing workflow engine
        from src.services.workflow_engine import run_workflow

        response = await run_workflow(
            db, member, phone, message_text,
            has_media=has_media, media_file_path=media_file_path,
        )
        intent = "llm_fallback"

    _save_conversation(db, member.id, message_text, response, intent)
    return response


def _save_conversation(
    db: Session,
    member_id,
    message_in: str,
    message_out: str,
    intent: str,
) -> None:
    """Save the conversation exchange to the database."""
    conv = Conversation(
        family_member_id=member_id,
        message_in=message_in,
        message_out=message_out,
        intent=intent,
    )
    db.add(conv)
    db.commit()
```

### 8. Package Init Files

**`src/skills/__init__.py`**:
```python
"""Skills package — registers built-in skills at import time."""

from src.skills.registry import registry
from src.skills.system_skill import SystemSkill

# Register built-in skills
registry.register(SystemSkill())
```

**`src/engine/__init__.py`**:
```python
# Engine package
```

## Data Models

No new database tables are introduced. The Skills Engine uses the existing schema:

| Model | Usage in Skills Engine |
|-------|----------------------|
| `FamilyMember` | Passed to `skill.execute()` as the authenticated user |
| `ConversationState` | Read/written by executor via `conversation_state` service |
| `Conversation` | Written by message handler for every exchange |
| `AuditLog` | Written by executor via `audit.log_action` for entity-creating actions |

### New Dataclasses (not ORM — in-memory only)

| Dataclass | Fields | Purpose |
|-----------|--------|---------|
| `Command` | `skill: str`, `action: str`, `params: dict` | Parsed user message ready for dispatch |
| `Result` | `success: bool`, `message: str`, `entity_type: str?`, `entity_id: UUID?`, `action: str?`, `data: dict?` | Skill execution outcome |

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

Since this project uses unit tests only (no property-based testing), the properties below are validated through specific example-based unit tests rather than randomized input generation.

### Property 1: Cancel keywords always produce system.cancel

For any message that is exactly one of the cancel keywords (לא, עזוב, תעזוב, בטל, תבטל, ביטול, cancel), the command parser shall return `Command(skill="system", action="cancel")`.

**Validates: Requirements 3.3**

### Property 2: Confirmation keywords always produce system.confirm

For any message that is exactly one of the confirmation keywords (כן, yes, אישור, אשר, ok, בטח, אוקיי, אוקי), the command parser shall return `Command(skill="system", action="confirm")`.

**Validates: Requirements 3.4**

### Property 3: Media messages take highest priority

For any message where `has_media=True`, regardless of message text content, the command parser shall return `Command(skill="media", action="save")`.

**Validates: Requirements 3.2, 3.5**

### Property 4: Unmatched messages return None

For any message that does not match any registered pattern and has no media, the command parser shall return `None`.

**Validates: Requirements 3.1, 3.6**

### Property 5: Regex named groups populate params

For any skill pattern containing named groups, when a message matches that pattern, the resulting Command's `params` dict shall contain all named group values.

**Validates: Requirements 3.8**

### Property 6: Successful execution with entity_id triggers verify

For any skill execution that returns `Result(success=True, entity_id=<non-None>)`, the executor shall call `skill.verify(db, result)` before returning.

**Validates: Requirements 4.3**

### Property 7: Verification failure replaces result message

For any skill execution where `verify()` returns `False`, the executor shall return a Result with `success=False` and `message=TEMPLATES["verification_failed"]`.

**Validates: Requirements 4.4**

### Property 8: Exceptions trigger rollback and error result

For any skill execution that raises an exception, the executor shall call `db.rollback()` and return `Result(success=False, message=TEMPLATES["error_fallback"])`.

**Validates: Requirements 4.8**

### Property 9: Cancel action clears conversation state

For any cancel command execution, the executor shall call `clear_state(db, member.id)`.

**Validates: Requirements 4.6, 5.2**

### Property 10: Successful execution updates conversation state

For any successful skill execution, the executor shall call `update_state` with the command's skill name as intent, and the result's entity_type, entity_id, and action.

**Validates: Requirements 4.5, 5.1**

### Property 11: Successful execution with entity_id writes audit log

For any successful skill execution with a non-None entity_id, the executor shall call `log_action` with the member's id, the action, entity_type, and entity_id.

**Validates: Requirements 4.7**

### Property 12: Confirmation with no pending action returns informative message

For any confirm command when no pending action exists, the executor shall return a Result indicating nothing to confirm.

**Validates: Requirements 5.4, 8.4**

### Property 13: Messages over 3500 chars are truncated

For any Result whose message exceeds 3500 characters, `format_response` shall return a string of at most 3500 + truncation indicator length, ending with the truncation indicator.

**Validates: Requirements 6.1**

### Property 14: Messages within limit pass through unchanged

For any Result whose message is ≤3500 characters, `format_response` shall return the message unchanged.

**Validates: Requirements 6.2**

### Property 15: Unknown/inactive members get personality template responses

For any phone number not in the database, the message handler returns `TEMPLATES["unknown_member"]`. For any inactive member, it returns `TEMPLATES["inactive_member"]`.

**Validates: Requirements 7.1**

### Property 16: Every message exchange is saved to conversations table

For any incoming message (whether handled by skills engine or LLM fallback), the message handler shall create a Conversation record with the message text, response, and intent.

**Validates: Requirements 7.6**

### Property 17: SystemSkill.verify always returns True

For any Result passed to `SystemSkill.verify()`, it shall return `True`.

**Validates: Requirements 8.6**

## Error Handling

| Scenario | Handler | Behavior |
|----------|---------|----------|
| Unknown phone number | `message_handler` | Return `TEMPLATES["unknown_member"]`, save conversation |
| Inactive member | `message_handler` | Return `TEMPLATES["inactive_member"]`, save conversation |
| Skill not found in registry | `executor` | Return `Result(success=False, message=TEMPLATES["error_fallback"])` |
| Skill.execute() raises exception | `executor` | `db.rollback()`, log exception, return `Result(success=False, message=TEMPLATES["error_fallback"])` |
| Verify returns False | `executor` | Return `Result(success=False, message=TEMPLATES["verification_failed"])` |
| Confirm with no pending action | `executor` / `system_skill` | Return `Result(success=False, message="אין פעולה ממתינה לאישור 🤷")` |
| Response too long for WhatsApp | `response_formatter` | Truncate at 3500 chars + Hebrew truncation indicator |

All error messages use personality templates to maintain consistent Hebrew tone.

## Testing Strategy

All tests are unit tests using `pytest` with `unittest.mock`. No property-based testing library is used per project constraints.

### Test Files

| File | Tests | Covers |
|------|-------|--------|
| `test_base_skill.py` | Command/Result construction, BaseSkill ABC enforcement | Req 1 |
| `test_registry.py` | register, get, all_commands, list_skills, singleton | Req 2 |
| `test_command_parser.py` | All cancel/confirm keywords, media priority, skill patterns, named groups, LLM fallback | Req 3 |
| `test_executor.py` | Success + verify + state + audit, verify failure, exception rollback, cancel, confirm flows | Req 4, 5 |
| `test_response_formatter.py` | Truncation, passthrough | Req 6 |
| `test_system_skill.py` | cancel ± pending, confirm ± pending, help listing, verify=True | Req 8 |
| `test_message_handler.py` | Auth flows, skills path, LLM fallback, conversation saving, media forwarding | Req 7 |

### Test Approach

- Each test file uses `unittest.mock.MagicMock` for DB sessions, skills, and services
- Tests use the existing `conftest.py` fixtures (`mock_db`, `sample_family_member`)
- Cancel/confirm tests iterate over all Hebrew keywords to ensure complete coverage
- Executor tests mock `conversation_state` and `audit` service functions
- Message handler tests mock `parse_command`, `execute`, `format_response`, and `run_workflow`
- All existing tests in `fortress/tests/` must continue to pass without modification
