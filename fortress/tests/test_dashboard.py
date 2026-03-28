"""Unit tests for the admin dashboard endpoints."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers — mock health checks
# ---------------------------------------------------------------------------

def _mock_all_health_checks():
    """Return context managers that mock all 4 health checks as connected."""
    return (
        patch("src.routers.dashboard.test_connection", return_value=True),
        patch(
            "src.routers.dashboard.OllamaClient.is_available",
            new_callable=AsyncMock,
            return_value=(True, "llama3.1:8b"),
        ),
        _mock_bedrock_available(),
        patch(
            "src.routers.dashboard.check_waha_health",
            new_callable=AsyncMock,
            return_value="connected",
        ),
    )


def _mock_bedrock_available():
    mock_cls = patch("src.routers.dashboard.BedrockClient")

    class _Ctx:
        def __enter__(self_):
            self_.mock = mock_cls.__enter__()
            self_.mock.return_value.is_available = AsyncMock(
                return_value=(True, "lite")
            )
            return self_.mock

        def __exit__(self_, *args):
            return mock_cls.__exit__(*args)

    return _Ctx()


def _setup_db_mock(mock_db: MagicMock) -> None:
    """Configure mock_db to return sensible defaults for all dashboard queries.

    The dashboard router chains: db.query(...).filter(...).scalar() for counts
    and db.query(...).outerjoin(...).order_by(...).limit(...).all() for lists.
    MagicMock auto-chains, so we just need .scalar() and .all() to return values.
    """
    # Every chained call returns the same mock, so .scalar() and .all()
    # are the terminal calls we need to control.
    chain = mock_db.query.return_value
    chain.filter.return_value = chain
    chain.outerjoin.return_value = chain
    chain.order_by.return_value = chain
    chain.limit.return_value = chain

    # Default: all counts return 0, all lists return []
    chain.scalar.return_value = 0
    chain.all.return_value = []


def _patch_start_time():
    """Patch APP_START_TIME to a known past value."""
    return patch("src.main.APP_START_TIME", time.time() - 3600)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_dashboard_data_returns_200(client: TestClient, mock_db: MagicMock) -> None:
    """GET /dashboard/data should return HTTP 200."""
    _setup_db_mock(mock_db)
    db_p, ollama_p, bedrock_p, waha_p = _mock_all_health_checks()
    with db_p, ollama_p, bedrock_p, waha_p, _patch_start_time():
        resp = client.get("/dashboard/data")
    assert resp.status_code == 200


def test_dashboard_data_json_structure(client: TestClient, mock_db: MagicMock) -> None:
    """Response should contain all required top-level keys."""
    _setup_db_mock(mock_db)
    db_p, ollama_p, bedrock_p, waha_p = _mock_all_health_checks()
    with db_p, ollama_p, bedrock_p, waha_p, _patch_start_time():
        data = client.get("/dashboard/data").json()
    for key in ("health", "today", "open_items", "recent_conversations",
                "open_bugs", "family_members", "system"):
        assert key in data, f"Missing key: {key}"


def test_dashboard_health_all_services(client: TestClient, mock_db: MagicMock) -> None:
    """Health object should contain status for all 4 services."""
    _setup_db_mock(mock_db)
    db_p, ollama_p, bedrock_p, waha_p = _mock_all_health_checks()
    with db_p, ollama_p, bedrock_p, waha_p, _patch_start_time():
        health = client.get("/dashboard/data").json()["health"]
    assert health["database"] == "connected"
    assert health["ollama"] == "connected"
    assert health["bedrock"] == "connected"
    assert health["waha"] == "connected"


def test_dashboard_today_counts_are_integers(client: TestClient, mock_db: MagicMock) -> None:
    """Today counts should all be integers."""
    _setup_db_mock(mock_db)
    db_p, ollama_p, bedrock_p, waha_p = _mock_all_health_checks()
    with db_p, ollama_p, bedrock_p, waha_p, _patch_start_time():
        today = client.get("/dashboard/data").json()["today"]
    for key in ("conversations", "tasks_created", "bugs_reported", "errors"):
        assert isinstance(today[key], int), f"{key} should be int"


def test_dashboard_open_items(client: TestClient, mock_db: MagicMock) -> None:
    """Open items should contain open_tasks and open_bugs as integers."""
    _setup_db_mock(mock_db)
    db_p, ollama_p, bedrock_p, waha_p = _mock_all_health_checks()
    with db_p, ollama_p, bedrock_p, waha_p, _patch_start_time():
        items = client.get("/dashboard/data").json()["open_items"]
    assert isinstance(items["open_tasks"], int)
    assert isinstance(items["open_bugs"], int)


def test_dashboard_recent_conversations_is_list(client: TestClient, mock_db: MagicMock) -> None:
    """recent_conversations should be a list."""
    _setup_db_mock(mock_db)
    db_p, ollama_p, bedrock_p, waha_p = _mock_all_health_checks()
    with db_p, ollama_p, bedrock_p, waha_p, _patch_start_time():
        data = client.get("/dashboard/data").json()
    assert isinstance(data["recent_conversations"], list)


def test_dashboard_open_bugs_is_list(client: TestClient, mock_db: MagicMock) -> None:
    """open_bugs should be a list."""
    _setup_db_mock(mock_db)
    db_p, ollama_p, bedrock_p, waha_p = _mock_all_health_checks()
    with db_p, ollama_p, bedrock_p, waha_p, _patch_start_time():
        data = client.get("/dashboard/data").json()
    assert isinstance(data["open_bugs"], list)


def test_dashboard_family_members_is_list(client: TestClient, mock_db: MagicMock) -> None:
    """family_members should be a list."""
    _setup_db_mock(mock_db)
    db_p, ollama_p, bedrock_p, waha_p = _mock_all_health_checks()
    with db_p, ollama_p, bedrock_p, waha_p, _patch_start_time():
        data = client.get("/dashboard/data").json()
    assert isinstance(data["family_members"], list)


def test_dashboard_system_info(client: TestClient, mock_db: MagicMock) -> None:
    """System object should have version, uptime_seconds >= 0, and app_start_time."""
    _setup_db_mock(mock_db)
    db_p, ollama_p, bedrock_p, waha_p = _mock_all_health_checks()
    with db_p, ollama_p, bedrock_p, waha_p, _patch_start_time():
        system = client.get("/dashboard/data").json()["system"]
    assert system["version"] == "2.0.0"
    assert isinstance(system["uptime_seconds"], int)
    assert system["uptime_seconds"] >= 0
    assert "app_start_time" in system


def test_dashboard_uptime_non_negative(client: TestClient, mock_db: MagicMock) -> None:
    """uptime_seconds should be non-negative when APP_START_TIME is in the past."""
    _setup_db_mock(mock_db)
    db_p, ollama_p, bedrock_p, waha_p = _mock_all_health_checks()
    past_time = time.time() - 7200  # 2 hours ago
    with db_p, ollama_p, bedrock_p, waha_p, \
         patch("src.main.APP_START_TIME", past_time):
        system = client.get("/dashboard/data").json()["system"]
    assert system["uptime_seconds"] >= 7200


# ---------------------------------------------------------------------------
# WAHA health check tests
# ---------------------------------------------------------------------------


def test_waha_health_connected(client: TestClient, mock_db: MagicMock) -> None:
    """WAHA health should return 'connected' when sessions endpoint returns 200."""
    _setup_db_mock(mock_db)
    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("src.routers.dashboard.test_connection", return_value=True), \
         patch("src.routers.dashboard.OllamaClient.is_available",
               new_callable=AsyncMock, return_value=(True, "llama3.1:8b")), \
         _mock_bedrock_available(), \
         patch("src.routers.dashboard.httpx.AsyncClient") as mock_httpx, \
         _patch_start_time():
        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.return_value = mock_client_instance
        health = client.get("/dashboard/data").json()["health"]
    assert health["waha"] == "connected"


def test_waha_health_disconnected_non_200(client: TestClient, mock_db: MagicMock) -> None:
    """WAHA health should return 'disconnected' when sessions endpoint returns non-200."""
    _setup_db_mock(mock_db)
    mock_response = MagicMock()
    mock_response.status_code = 500

    with patch("src.routers.dashboard.test_connection", return_value=True), \
         patch("src.routers.dashboard.OllamaClient.is_available",
               new_callable=AsyncMock, return_value=(True, "llama3.1:8b")), \
         _mock_bedrock_available(), \
         patch("src.routers.dashboard.httpx.AsyncClient") as mock_httpx, \
         _patch_start_time():
        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.return_value = mock_client_instance
        health = client.get("/dashboard/data").json()["health"]
    assert health["waha"] == "disconnected"


def test_waha_health_disconnected_error(client: TestClient, mock_db: MagicMock) -> None:
    """WAHA health should return 'disconnected' when connection fails."""
    _setup_db_mock(mock_db)

    with patch("src.routers.dashboard.test_connection", return_value=True), \
         patch("src.routers.dashboard.OllamaClient.is_available",
               new_callable=AsyncMock, return_value=(True, "llama3.1:8b")), \
         _mock_bedrock_available(), \
         patch("src.routers.dashboard.httpx.AsyncClient") as mock_httpx, \
         _patch_start_time():
        mock_client_instance = AsyncMock()
        mock_client_instance.get.side_effect = httpx.ConnectError("Connection refused")
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)
        mock_httpx.return_value = mock_client_instance
        health = client.get("/dashboard/data").json()["health"]
    assert health["waha"] == "disconnected"


def test_dashboard_page_endpoint(client: TestClient) -> None:
    """GET /dashboard should return 200 with HTML content."""
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "Fortress Admin Dashboard" in resp.text
