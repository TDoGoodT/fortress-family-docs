"""Unit tests for the GET /health endpoint."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


def _mock_ollama_available():
    """Patch OllamaClient.is_available to return connected with model."""
    return patch(
        "src.routers.health.OllamaClient.is_available",
        new_callable=AsyncMock,
        return_value=(True, "llama3.1:8b"),
    )


def _mock_ollama_unavailable():
    """Patch OllamaClient.is_available to return disconnected."""
    return patch(
        "src.routers.health.OllamaClient.is_available",
        new_callable=AsyncMock,
        return_value=(False, None),
    )


def test_health_returns_200(client: TestClient) -> None:
    """GET /health should return HTTP 200."""
    with patch("src.routers.health.test_connection", return_value=True), _mock_ollama_available():
        response = client.get("/health")
    assert response.status_code == 200


def test_health_response_body(client: TestClient) -> None:
    """GET /health should contain status, service, and version fields."""
    with patch("src.routers.health.test_connection", return_value=True), _mock_ollama_available():
        data = client.get("/health").json()
    assert data["status"] == "ok"
    assert data["service"] == "fortress"
    assert data["version"] == "2.0.0"


def test_health_database_connected(client: TestClient) -> None:
    """When the DB is reachable, /health should report 'connected'."""
    with patch("src.routers.health.test_connection", return_value=True), _mock_ollama_available():
        data = client.get("/health").json()
    assert data["database"] == "connected"


def test_health_database_disconnected(client: TestClient) -> None:
    """When the DB is unreachable, /health should report 'disconnected'."""
    with patch("src.routers.health.test_connection", return_value=False), _mock_ollama_available():
        data = client.get("/health").json()
    assert data["database"] == "disconnected"


def test_health_ollama_connected(client: TestClient) -> None:
    """When Ollama is reachable with model, /health should report 'connected'."""
    with patch("src.routers.health.test_connection", return_value=True), _mock_ollama_available():
        data = client.get("/health").json()
    assert data["ollama"] == "connected"
    assert data["ollama_model"] == "llama3.1:8b"


def test_health_ollama_disconnected(client: TestClient) -> None:
    """When Ollama is unreachable, /health should report 'disconnected'."""
    with patch("src.routers.health.test_connection", return_value=True), _mock_ollama_unavailable():
        data = client.get("/health").json()
    assert data["ollama"] == "disconnected"
    assert data["ollama_model"] == "not loaded"
