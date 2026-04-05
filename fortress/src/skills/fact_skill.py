"""Fortress Skills Engine — canonical personal + household facts."""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from src.models.schema import CanonicalFact, FamilyMember
from src.services.fact_policy import can_read_category
from src.services.fact_service import (
    get_latest_household_fact,
    get_latest_person_fact,
    parse_birth_store,
    parse_building_code_store,
    parse_id_store,
    resolve_person_reference,
    upsert_household_fact,
    upsert_person_fact,
)
from src.skills.base_skill import BaseSkill, Command, Result


class FactSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "fact"

    @property
    def description(self) -> str:
        return "עובדות אישיות ועובדות בית"

    @property
    def commands(self) -> list[tuple[re.Pattern, str]]:
        return [
            (re.compile(r"(?:נולד|נולדה|was born|born on)", re.IGNORECASE), "store_birth_date"),
            (re.compile(r"(?:תעודת זהות|\bID\b).*(?:של|of)?", re.IGNORECASE), "store_or_query_id"),
            (re.compile(r"(?:when was i born|מתי נולדתי|מתי נולדתי\?)", re.IGNORECASE), "query_self_birth"),
            (re.compile(r"(?:מתי .*נולד|תאריך לידה|date of birth)", re.IGNORECASE), "query_birth"),
            (re.compile(r"(?:building code|קוד בניין|קוד כניסה|מה הקוד של)", re.IGNORECASE), "store_or_query_building_code"),
        ]

    def execute(self, db: Session, member: FamilyMember, command: Command) -> Result:
        action = command.action
        text = command.raw_text or command.params.get("raw_text") or command.params.get("_original_message", "")

        if action == "store_birth_date":
            parsed = parse_birth_store(text)
            if parsed is None:
                return self._query_birth(db, member, text)
            name_ref, birth_date = parsed
            resolved = resolve_person_reference(db, member, name_ref)
            if resolved is None:
                return Result(success=False, message="לא זיהיתי על מי מדובר.")
            fact = upsert_person_fact(
                db,
                actor=member,
                subject_member_id=resolved.member_id,
                fact_key="birth_date",
                fact_value=birth_date,
                category="basic_personal",
            )
            return Result(success=True, message=f"שמרתי את תאריך הלידה של {resolved.display_name} ✅", entity_type="fact", entity_id=fact.id, action="stored")

        if action == "store_or_query_id":
            parsed = parse_id_store(text)
            if parsed is not None:
                name_ref, id_number = parsed
                resolved = resolve_person_reference(db, member, name_ref)
                if resolved is None:
                    return Result(success=False, message="לא זיהיתי על מי מדובר.")
                fact = upsert_person_fact(
                    db,
                    actor=member,
                    subject_member_id=resolved.member_id,
                    fact_key="id_number",
                    fact_value=id_number,
                    category="basic_personal",
                )
                return Result(success=True, message=f"שמרתי את מספר הזהות של {resolved.display_name} ✅", entity_type="fact", entity_id=fact.id, action="stored")
            return self._query_id(db, member, text)

        if action == "query_self_birth":
            return self._query_birth(db, member, "אני")

        if action == "query_birth":
            return self._query_birth(db, member, text)

        if action == "store_or_query_building_code":
            parsed = parse_building_code_store(text)
            if parsed is not None:
                location, code = parsed
                fact = upsert_household_fact(
                    db,
                    actor=member,
                    location_key=location.lower(),
                    fact_key="building_code",
                    fact_value=code,
                    category="household_access",
                )
                return Result(success=True, message=f"שמרתי את קוד הבניין של {location} ✅", entity_type="fact", entity_id=fact.id, action="stored")
            return self._query_building_code(db, member, text)

        return Result(success=False, message="לא הבנתי את הבקשה.")

    def _query_birth(self, db: Session, member: FamilyMember, text: str) -> Result:
        resolved = self._resolve_query_target(db, member, text)
        if resolved is None:
            return Result(success=False, message="לא זיהיתי על מי מדובר.")
        fact = get_latest_person_fact(db, resolved.member_id, "birth_date")
        if fact is None:
            return Result(success=True, message="אין לי תאריך לידה שמור כרגע.")
        if not can_read_category(member, fact.category):
            return Result(success=False, message="אין לך הרשאה לזה 🔒")
        return Result(success=True, message=f"תאריך הלידה של {resolved.display_name}: {fact.fact_value}")

    def _query_id(self, db: Session, member: FamilyMember, text: str) -> Result:
        resolved = self._resolve_query_target(db, member, text)
        if resolved is None:
            return Result(success=False, message="לא זיהיתי על מי מדובר.")
        fact = get_latest_person_fact(db, resolved.member_id, "id_number")
        if fact is None:
            return Result(success=True, message="אין לי מספר זהות שמור כרגע.")
        if not can_read_category(member, fact.category):
            return Result(success=False, message="אין לך הרשאה לזה 🔒")
        return Result(success=True, message=f"מספר הזהות של {resolved.display_name}: {fact.fact_value}")

    def _query_building_code(self, db: Session, member: FamilyMember, text: str) -> Result:
        # tolerate variants like "Ahud Manor" / "אחוד מנור"
        lowered = text.lower()
        location = "ahud manor" if "ahud" in lowered else text
        fact = get_latest_household_fact(db, location.lower().strip(), "building_code")
        if fact is None and "ahud" in lowered:
            fact = get_latest_household_fact(db, "ahud manor", "building_code")
        if fact is None:
            return Result(success=True, message="אין לי קוד בניין שמור למיקום הזה כרגע.")
        if not can_read_category(member, fact.category):
            return Result(success=False, message="אין לך הרשאה לזה 🔒")
        place = fact.location_key or "המיקום"
        return Result(success=True, message=f"קוד הבניין של {place}: {fact.fact_value}")

    def _resolve_query_target(self, db: Session, member: FamilyMember, text: str):
        lowered = text.lower()
        if any(token in lowered for token in ["i ", " i", "אני", "שלי", "נולדתי", "my id", "תז שלי"]):
            return resolve_person_reference(db, member, "אני")

        name_match = re.search(r"(?:of|של)\s+([\wא-ת]+)", text, flags=re.IGNORECASE)
        if name_match:
            return resolve_person_reference(db, member, name_match.group(1))

        words = re.findall(r"[\wא-ת]+", text)
        for token in words:
            resolved = resolve_person_reference(db, member, token)
            if resolved is not None:
                return resolved

        return resolve_person_reference(db, member, "אני")

    def verify(self, db: Session, result: Result) -> bool:
        if result.action == "stored" and result.entity_id is not None:
            row = db.query(CanonicalFact).filter(CanonicalFact.id == result.entity_id).first()
            return row is not None
        return True

    def get_help(self) -> str:
        return 'אפשר לשמור ולשלוף תאריך לידה, ת"ז וקודי בניין.'
