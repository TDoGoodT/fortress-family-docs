"""Unit tests for the GET /health endpoint."""

from unittest.mock import patch

from fastapi.testclient import TestClient


def test_health_returns_200(client: TestClient) -> None:
    """GET /health should return HTTP 200."""
    with patch("src.routers.health.test_connection", return_value=True):
        response = client.get("/health")
    assert response.status_code == 200


def test_health_response_body(client: TestClient) -> None:
    """GET /health should contain status, service, and version fields."""
    with patch("src.routers.health.test_connection", return_value=True):
        data = client.get("/health").json()
    assert data["status"] == "ok"
    assert data["service"] == "fortress"
    assert data["version"] == "2.0.0"


def test_health_database_connected(client: TestClient) -> None:
    """When the DB is reachable, /health should report 'connected'."""
    with patch("src.routers.health.test_connection", return_value=True):
        data = client.get("/health").json()
    assert data["database"] == "connected"


def test_health_database_disconnected(client: TestClient) -> None:
    """When the DB is unreachable, /health should report 'disconnected'."""
    with patch("src.routers.health.test_connection", return_value=False):
        data = client.get("/health").json()
    assert data["database"] == "disconnected"
