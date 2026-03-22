"""Unit tests for RoutingPolicy."""

import pytest

from src.services.routing_policy import (
    SENSITIVITY_MAP,
    get_route,
    get_sensitivity,
)


def test_greeting_is_low_sensitivity():
    assert get_sensitivity("greeting") == "low"


@pytest.mark.parametrize("intent", ["list_tasks", "create_task", "complete_task", "list_documents", "unknown", "delete_task"])
def test_medium_sensitivity_intents(intent: str):
    assert get_sensitivity(intent) == "medium"


@pytest.mark.parametrize("intent", ["ask_question", "upload_document"])
def test_high_sensitivity_intents(intent: str):
    assert get_sensitivity(intent) == "high"


def test_unknown_intent_defaults_to_high():
    """Unrecognized intents default to 'high' (fail-safe)."""
    assert get_sensitivity("totally_new_intent") == "high"


def test_greeting_route_starts_with_openrouter():
    route = get_route("greeting")
    assert route == ["openrouter", "bedrock", "ollama"]


def test_list_tasks_route():
    route = get_route("list_tasks")
    assert route == ["openrouter", "bedrock", "ollama"]


def test_ask_question_route_no_openrouter():
    route = get_route("ask_question")
    assert route == ["bedrock", "ollama"]
    assert "openrouter" not in route


def test_upload_document_route_no_openrouter():
    route = get_route("upload_document")
    assert route == ["bedrock", "ollama"]
    assert "openrouter" not in route


def test_high_sensitivity_routes_never_contain_openrouter():
    """All high sensitivity intents must exclude openrouter."""
    for intent, sensitivity in SENSITIVITY_MAP.items():
        if sensitivity == "high":
            route = get_route(intent)
            assert "openrouter" not in route, f"{intent} route should not contain openrouter"


def test_every_known_intent_has_sensitivity():
    """Every intent in the map returns a valid sensitivity level."""
    for intent in SENSITIVITY_MAP:
        level = get_sensitivity(intent)
        assert level in ("low", "medium", "high")


def test_get_route_returns_copy():
    """get_route returns a new list each time (not a reference to the internal map)."""
    route1 = get_route("greeting")
    route2 = get_route("greeting")
    assert route1 == route2
    assert route1 is not route2
