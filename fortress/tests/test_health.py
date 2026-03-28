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


def _mock_bedrock_available():
    """Patch BedrockClient so __init__ is a no-op and is_available returns connected."""
    mock_cls = patch("src.routers.health.BedrockClient")

    def _setup(mock):
        instance = mock.return_value
        instance.is_available = AsyncMock(return_value=(True, "lite"))
        return mock

    class _Ctx:
        def __enter__(self_):
            self_.mock = mock_cls.__enter__()
            _setup(self_.mock)
            return self_.mock

        def __exit__(self_, *args):
            return mock_cls.__exit__(*args)

    return _Ctx()


def _mock_bedrock_unavailable():
    """Patch BedrockClient so __init__ is a no-op and is_available returns disconnected."""
    mock_cls = patch("src.routers.health.BedrockClient")

    def _setup(mock):
        instance = mock.return_value
        instance.is_available = AsyncMock(return_value=(False, None))
        return mock

    class _Ctx:
        def __enter__(self_):
            self_.mock = mock_cls.__enter__()
            _setup(self_.mock)
            return self_.mock

        def __exit__(self_, *args):
            return mock_cls.__exit__(*args)

    return _Ctx()


def test_health_returns_200(client: TestClient) -> None:
    """GET /health should return HTTP 200."""
    with patch("src.routers.health.test_connection", return_value=True), \
         _mock_ollama_available(), _mock_bedrock_available():
        response = client.get("/health")
    assert response.status_code == 200


def test_health_response_body(client: TestClient) -> None:
    """GET /health should contain status, service, and version fields."""
    with patch("src.routers.health.test_connection", return_value=True), \
         _mock_ollama_available(), _mock_bedrock_available():
        data = client.get("/health").json()
    assert data["status"] == "ok"
    assert data["service"] == "fortress"
    assert data["version"] == "2.0.0"


def test_health_database_connected(client: TestClient) -> None:
    """When the DB is reachable, /health should report 'connected'."""
    with patch("src.routers.health.test_connection", return_value=True), \
         _mock_ollama_available(), _mock_bedrock_available():
        data = client.get("/health").json()
    assert data["database"] == "connected"


def test_health_database_disconnected(client: TestClient) -> None:
    """When the DB is unreachable, /health should report 'disconnected'."""
    with patch("src.routers.health.test_connection", return_value=False), \
         _mock_ollama_available(), _mock_bedrock_available():
        data = client.get("/health").json()
    assert data["database"] == "disconnected"


def test_health_ollama_connected(client: TestClient) -> None:
    """When Ollama is reachable with model, /health should report 'connected'."""
    with patch("src.routers.health.test_connection", return_value=True), \
         _mock_ollama_available(), _mock_bedrock_available():
        data = client.get("/health").json()
    assert data["ollama"] == "connected"
    assert data["ollama_model"] == "llama3.1:8b"


def test_health_ollama_disconnected(client: TestClient) -> None:
    """When Ollama is unreachable, /health should report 'disconnected'."""
    with patch("src.routers.health.test_connection", return_value=True), \
         _mock_ollama_unavailable(), _mock_bedrock_available():
        data = client.get("/health").json()
    assert data["ollama"] == "disconnected"
    assert data["ollama_model"] == "not loaded"


def test_health_bedrock_connected(client: TestClient) -> None:
    """When Bedrock is reachable, /health should report 'connected'."""
    with patch("src.routers.health.test_connection", return_value=True), \
         _mock_ollama_available(), _mock_bedrock_available():
        data = client.get("/health").json()
    assert data["bedrock"] == "connected"
    assert data["bedrock_model"] == "lite"


def test_health_bedrock_disconnected(client: TestClient) -> None:
    """When Bedrock is unreachable, /health should report 'disconnected'."""
    with patch("src.routers.health.test_connection", return_value=True), \
         _mock_ollama_unavailable(), _mock_bedrock_unavailable():
        data = client.get("/health").json()
    assert data["bedrock"] == "disconnected"
    assert data["bedrock_model"] == "not available"
