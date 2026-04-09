"""Agent permission matrix — controls which agents can access which data.

Each agent has a role. Each role has table-level permissions.
"read" = can see full records. "metadata" = can see existence + type/date/vendor only.
"write" = can create/update records. None = no access.
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class AccessLevel(str, Enum):
    NONE = "none"
    METADATA = "metadata"
    READ = "read"
    WRITE = "write"
    READ_WRITE = "read_write"


# Table names that agents can request access to
PROTECTED_TABLES = {
    "documents", "document_facts", "salary_slips", "utility_bills",
    "contracts", "insurance_policies", "tasks", "memories",
    "family_members", "conversations",
}

# Permission matrix: role → table → access level
_PERMISSION_MATRIX: dict[str, dict[str, AccessLevel]] = {
    "librarian": {
        "documents": AccessLevel.READ_WRITE,
        "document_facts": AccessLevel.READ_WRITE,
        "salary_slips": AccessLevel.READ,
        "utility_bills": AccessLevel.READ,
        "contracts": AccessLevel.READ,
        "insurance_policies": AccessLevel.READ,
        "tasks": AccessLevel.READ_WRITE,
        "memories": AccessLevel.READ_WRITE,
        "family_members": AccessLevel.METADATA,
        "conversations": AccessLevel.NONE,
    },
    "finance_agent": {
        "documents": AccessLevel.READ,
        "document_facts": AccessLevel.READ,
        "salary_slips": AccessLevel.READ,
        "utility_bills": AccessLevel.READ,
        "contracts": AccessLevel.READ,
        "insurance_policies": AccessLevel.NONE,
        "tasks": AccessLevel.READ,
        "memories": AccessLevel.NONE,
        "family_members": AccessLevel.METADATA,
        "conversations": AccessLevel.NONE,
    },
    "insurance_agent": {
        "documents": AccessLevel.READ,
        "document_facts": AccessLevel.READ,
        "salary_slips": AccessLevel.NONE,
        "utility_bills": AccessLevel.NONE,
        "contracts": AccessLevel.READ,
        "insurance_policies": AccessLevel.READ,
        "tasks": AccessLevel.READ,
        "memories": AccessLevel.NONE,
        "family_members": AccessLevel.METADATA,
        "conversations": AccessLevel.NONE,
    },
    "orchestrator": {
        "documents": AccessLevel.METADATA,
        "document_facts": AccessLevel.METADATA,
        "salary_slips": AccessLevel.METADATA,
        "utility_bills": AccessLevel.METADATA,
        "contracts": AccessLevel.METADATA,
        "insurance_policies": AccessLevel.METADATA,
        "tasks": AccessLevel.READ_WRITE,
        "memories": AccessLevel.READ,
        "family_members": AccessLevel.METADATA,
        "conversations": AccessLevel.READ,
    },
}


def check_access(agent_role: str, table: str, required: AccessLevel) -> bool:
    """Check if an agent role has the required access level for a table."""
    role_perms = _PERMISSION_MATRIX.get(agent_role)
    if role_perms is None:
        logger.warning("permissions: unknown agent_role=%s", agent_role)
        return False

    granted = role_perms.get(table, AccessLevel.NONE)

    if required == AccessLevel.NONE:
        return True
    if required == AccessLevel.METADATA:
        return granted in (AccessLevel.METADATA, AccessLevel.READ, AccessLevel.WRITE, AccessLevel.READ_WRITE)
    if required == AccessLevel.READ:
        return granted in (AccessLevel.READ, AccessLevel.READ_WRITE)
    if required == AccessLevel.WRITE:
        return granted in (AccessLevel.WRITE, AccessLevel.READ_WRITE)
    if required == AccessLevel.READ_WRITE:
        return granted == AccessLevel.READ_WRITE

    return False


def get_accessible_tables(agent_role: str, min_level: AccessLevel = AccessLevel.METADATA) -> list[str]:
    """Return list of tables the agent role can access at the given minimum level."""
    role_perms = _PERMISSION_MATRIX.get(agent_role, {})
    return [table for table, level in role_perms.items() if check_access(agent_role, table, min_level)]


def get_role_permissions(agent_role: str) -> dict[str, str]:
    """Return the full permission map for a role (for introspection)."""
    role_perms = _PERMISSION_MATRIX.get(agent_role, {})
    return {table: level.value for table, level in role_perms.items()}
