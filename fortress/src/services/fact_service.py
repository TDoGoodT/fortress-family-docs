from __future__ import annotations

"""Canonical fact storage and identity resolution for household knowledge."""

import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from src.models.schema import CanonicalFact, FamilyMember


@dataclass
class ResolvedPerson:
    member_id: UUID
    display_name: str


_HEBREW_ALIAS_MAP: dict[str, str] = {
    "chen": "חן",
    "segev": "שגב",
}


_BASIC_PERSONAL_KEYS: set[str] = {"birth_date", "id_number", "gender", "spouse"}


def _normalize_name(text: str) -> str:
    cleaned = (text or "").strip().lower()
    if not cleaned:
        return ""
    return _HEBREW_ALIAS_MAP.get(cleaned, cleaned)


def _all_active_members(db: Session) -> list[FamilyMember]:
    return db.query(FamilyMember).filter(FamilyMember.is_active == True).all()  # noqa: E712


def resolve_person_reference(db: Session, actor: FamilyMember, reference: str) -> ResolvedPerson | None:
    """Resolve a person mention (self/name/relation) to a canonical family member."""
    ref = _normalize_name(reference)
    if not ref:
        return None

    self_refs = {"i", "me", "my", "myself", "אני", "עצמי", "שלי", "נולדתי"}
    if ref in self_refs:
        return ResolvedPerson(member_id=actor.id, display_name=actor.name)

    members = _all_active_members(db)
    for member in members:
        member_norm = _normalize_name(member.name)
        if ref == member_norm:
            return ResolvedPerson(member_id=member.id, display_name=member.name)

    # Relationship reference: my wife / אשתי / spouse
    if ref in {"my wife", "wife", "אשתי", "spouse", "בן הזוג שלי", "בת הזוג שלי"}:
        spouse_fact = (
            db.query(CanonicalFact)
            .filter(
                CanonicalFact.subject_member_id == actor.id,
                CanonicalFact.fact_key == "spouse",
                CanonicalFact.category == "basic_personal",
                CanonicalFact.is_active == True,  # noqa: E712
            )
            .order_by(CanonicalFact.created_at.desc())
            .first()
        )
        if spouse_fact:
            spouse = resolve_person_reference(db, actor, spouse_fact.fact_value)
            if spouse:
                return spouse

    return None


def infer_category_for_key(fact_key: str) -> str:
    if fact_key in _BASIC_PERSONAL_KEYS:
        return "basic_personal"
    if fact_key == "building_code":
        return "household_access"
    if fact_key.startswith("health_"):
        return "health"
    if fact_key.startswith("financial_"):
        return "financial"
    return "basic_personal"


def upsert_person_fact(
    db: Session,
    *,
    actor: FamilyMember,
    subject_member_id: UUID,
    fact_key: str,
    fact_value: str,
    category: str | None = None,
) -> CanonicalFact:
    cat = category or infer_category_for_key(fact_key)
    record = CanonicalFact(
        subject_member_id=subject_member_id,
        location_key=None,
        fact_key=fact_key,
        fact_value=fact_value,
        category=cat,
        created_by=actor.id,
    )
    db.add(record)
    db.flush()
    return record


def upsert_household_fact(
    db: Session,
    *,
    actor: FamilyMember,
    location_key: str,
    fact_key: str,
    fact_value: str,
    category: str | None = None,
) -> CanonicalFact:
    cat = category or infer_category_for_key(fact_key)
    record = CanonicalFact(
        subject_member_id=None,
        location_key=location_key,
        fact_key=fact_key,
        fact_value=fact_value,
        category=cat,
        created_by=actor.id,
    )
    db.add(record)
    db.flush()
    return record


def get_latest_person_fact(db: Session, subject_member_id: UUID, fact_key: str) -> CanonicalFact | None:
    return (
        db.query(CanonicalFact)
        .filter(
            CanonicalFact.subject_member_id == subject_member_id,
            CanonicalFact.fact_key == fact_key,
            CanonicalFact.is_active == True,  # noqa: E712
        )
        .order_by(CanonicalFact.created_at.desc())
        .first()
    )


def get_latest_household_fact(db: Session, location_key: str, fact_key: str) -> CanonicalFact | None:
    return (
        db.query(CanonicalFact)
        .filter(
            CanonicalFact.location_key == location_key,
            CanonicalFact.fact_key == fact_key,
            CanonicalFact.is_active == True,  # noqa: E712
        )
        .order_by(CanonicalFact.created_at.desc())
        .first()
    )


def parse_birth_store(text: str) -> tuple[str, str] | None:
    patterns = [
        r"(?P<name>[\wא-ת]+)\s+(?:was born|נולדה|נולד)\s+(?:on|ב)\s*(?P<date>\d{1,2}[./]\d{1,2}[./]\d{2,4})",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            return m.group("name"), m.group("date")
    return None


def parse_id_store(text: str) -> tuple[str, str] | None:
    m = re.search(r"(?P<name>[\wא-ת]+).{0,12}(?:id|תעודת זהות|תז)\D*(?P<id>\d{5,12})", text, flags=re.IGNORECASE)
    if not m:
        return None
    return m.group("name"), m.group("id")


def parse_building_code_store(text: str) -> tuple[str, str] | None:
    patterns = [
        r"(?P<location>[\wא-ת\s\-']+?)\s+(?:building\s*code|code|קוד כניסה|קוד בניין|קוד)\D*(?P<code>\d{3,10})",
        r"(?:building\s*code|קוד בניין|קוד כניסה)\s+(?:of|for|של)\s+(?P<location>[\wא-ת\s\-']+)\D*(?P<code>\d{3,10})",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            return m.group("location").strip(), m.group("code")
    return None
