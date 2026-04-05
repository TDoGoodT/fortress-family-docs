from __future__ import annotations

"""Category-based access policy for canonical facts."""

from src.models.schema import FamilyMember

ALLOWED_FACT_CATEGORIES: set[str] = {
    "basic_personal",
    "household_access",
    "financial",
    "health",
}


def can_read_category(actor: FamilyMember, category: str) -> bool:
    """Return True when *actor* may read the requested fact *category*."""
    if category in {"basic_personal", "household_access"}:
        return True
    if category in {"financial", "health"}:
        return actor.role == "parent"
    return False
