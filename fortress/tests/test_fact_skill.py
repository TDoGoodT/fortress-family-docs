"""Tests for canonical person/household fact flows."""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from sqlalchemy.orm import Session

from src.engine.command_parser import parse_command
from src.models.schema import FamilyMember
from src.services.message_handler import _should_prefer_structured_path
from src.skills.base_skill import Command
from src.skills.fact_skill import FactSkill
from src.skills.registry import registry


def _member(name: str = "Segev", role: str = "parent") -> MagicMock:
    m = MagicMock(spec=FamilyMember)
    m.id = uuid.uuid4()
    m.name = name
    m.phone = "+972501234567"
    m.role = role
    m.is_active = True
    return m


def test_parse_command_routes_fact_flows() -> None:
    cmd = parse_command("Chen was born on 30.12.1994", registry)
    assert cmd is not None
    assert cmd.skill == "fact"

    cmd = parse_command("when was I born?", registry)
    assert cmd is not None
    assert cmd.skill == "fact"


def test_fact_flows_prefer_structured_path() -> None:
    assert _should_prefer_structured_path("when was I born?") is True
    assert _should_prefer_structured_path("Ahud Manor building code is 7788") is True


def test_store_birth_then_query_self() -> None:
    db = MagicMock(spec=Session)
    skill = FactSkill()
    segev = _member("Segev")

    chen_resolved = SimpleNamespace(member_id=uuid.uuid4(), display_name="Chen")
    chen_birth_fact = SimpleNamespace(category="basic_personal", fact_value="30.12.1994")

    with patch("src.skills.fact_skill.parse_birth_store", return_value=("Chen", "30.12.1994")), \
         patch("src.skills.fact_skill.resolve_person_reference", side_effect=[chen_resolved, chen_resolved]), \
         patch("src.skills.fact_skill.upsert_person_fact", return_value=SimpleNamespace(id=uuid.uuid4())), \
         patch("src.skills.fact_skill.get_latest_person_fact", return_value=chen_birth_fact):
        store_cmd = Command(skill="fact", action="store_birth_date", raw_text="Chen was born on 30.12.1994")
        store_result = skill.execute(db, segev, store_cmd)
        assert store_result.success is True
        assert "שמרתי" in store_result.message

        query_cmd = Command(skill="fact", action="query_birth", raw_text="When was Chen born?")
        query_result = skill.execute(db, segev, query_cmd)
        assert query_result.success is True
        assert "30.12.1994" in query_result.message


def test_self_query_resolves_by_sender_identity() -> None:
    db = MagicMock(spec=Session)
    skill = FactSkill()
    chen = _member("Chen")

    chen_resolved = SimpleNamespace(member_id=chen.id, display_name="Chen")
    chen_birth_fact = SimpleNamespace(category="basic_personal", fact_value="30.12.1994")

    with patch("src.skills.fact_skill.resolve_person_reference", return_value=chen_resolved), \
         patch("src.skills.fact_skill.get_latest_person_fact", return_value=chen_birth_fact):
        cmd = Command(skill="fact", action="query_self_birth", raw_text="when was I born?")
        result = skill.execute(db, chen, cmd)

    assert result.success is True
    assert "30.12.1994" in result.message


def test_id_is_allowed_for_identified_users() -> None:
    db = MagicMock(spec=Session)
    skill = FactSkill()
    chen = _member("Chen", role="child")

    chen_resolved = SimpleNamespace(member_id=chen.id, display_name="Chen")
    chen_id_fact = SimpleNamespace(category="basic_personal", fact_value="123456789")

    with patch("src.skills.fact_skill.resolve_person_reference", return_value=chen_resolved), \
         patch("src.skills.fact_skill.get_latest_person_fact", return_value=chen_id_fact):
        cmd = Command(skill="fact", action="store_or_query_id", raw_text="what is Chen ID?")
        result = skill.execute(db, chen, cmd)

    assert result.success is True
    assert "123456789" in result.message


def test_building_code_store_and_query() -> None:
    db = MagicMock(spec=Session)
    skill = FactSkill()
    segev = _member("Segev")

    stored = SimpleNamespace(id=uuid.uuid4())
    loaded = SimpleNamespace(category="household_access", fact_value="7788", location_key="ahud manor")

    with patch("src.skills.fact_skill.parse_building_code_store", return_value=("Ahud Manor", "7788")), \
         patch("src.skills.fact_skill.upsert_household_fact", return_value=stored):
        store_cmd = Command(skill="fact", action="store_or_query_building_code", raw_text="Ahud Manor building code is 7788")
        store_result = skill.execute(db, segev, store_cmd)
        assert store_result.success is True
        assert "שמרתי" in store_result.message

    with patch("src.skills.fact_skill.parse_building_code_store", return_value=None), \
         patch("src.skills.fact_skill.get_latest_household_fact", return_value=loaded):
        query_cmd = Command(skill="fact", action="store_or_query_building_code", raw_text="what is Ahud Manor building code?")
        query_result = skill.execute(db, segev, query_cmd)
        assert query_result.success is True
        assert "7788" in query_result.message
