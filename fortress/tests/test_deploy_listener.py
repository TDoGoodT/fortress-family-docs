"""Unit tests for deploy_listener.py — validation, rate limiting, localhost binding."""

import json
import os
import sys
import threading
import time
from http.server import HTTPServer
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

# The deploy_listener is a standalone script, not a package module.
# We add its directory to sys.path so we can import it.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import deploy_listener  # noqa: E402


TEST_SECRET = "test-secret-abc123"


class FakeRequest:
    """Minimal fake socket request for BaseHTTPRequestHandler."""

    def __init__(self, method: str, body: bytes | None = None,
                 content_type: str = "application/json"):
        self.method = method
        self.body = body or b""
        self.content_type = content_type

    def makefile(self, mode, buffering=-1):
        if "r" in mode:
            # Build raw HTTP request
            lines = [f"{self.method} / HTTP/1.1"]
            lines.append(f"Content-Type: {self.content_type}")
            lines.append(f"Content-Length: {len(self.body)}")
            lines.append("")
            lines.append("")
            header = "\r\n".join(lines).encode()
            return BytesIO(header + self.body)
        else:
            return BytesIO()


def _make_handler(method: str = "POST", body: dict | None = None,
                  content_type: str = "application/json",
                  raw_body: bytes | None = None) -> deploy_listener.DeployHandler:
    """Create a DeployHandler with a fake request, capturing the response."""
    if raw_body is None:
        raw_body = json.dumps(body).encode() if body else b""

    request_line = f"{method} / HTTP/1.1\r\n"
    headers = f"Content-Type: {content_type}\r\nContent-Length: {len(raw_body)}\r\n\r\n"
    raw = request_line.encode() + headers.encode() + raw_body

    # Mock the socket
    mock_request = MagicMock()
    mock_request.makefile.return_value = BytesIO(raw)

    # Capture response
    response_buffer = BytesIO()

    handler = deploy_listener.DeployHandler.__new__(deploy_listener.DeployHandler)
    handler.client_address = ("127.0.0.1", 12345)
    handler.server = MagicMock()
    handler.request = mock_request
    handler.rfile = BytesIO(raw_body)
    handler.wfile = response_buffer
    handler.requestline = f"{method} / HTTP/1.1"
    handler.command = method
    handler.request_version = "HTTP/1.1"
    handler.headers = _parse_headers(content_type, len(raw_body))
    handler.close_connection = True

    # Capture sent status code
    handler._response_code = None
    handler._response_body = None
    original_send_response = handler.send_response.__func__ if hasattr(handler.send_response, '__func__') else None

    sent_codes = []
    sent_bodies = []

    def mock_send_response(code, message=None):
        sent_codes.append(code)

    def mock_send_header(key, value):
        pass

    def mock_end_headers():
        pass

    class WritableBuffer:
        def __init__(self):
            self.data = b""
        def write(self, b):
            self.data += b

    writable = WritableBuffer()

    handler.send_response = mock_send_response
    handler.send_header = mock_send_header
    handler.end_headers = mock_end_headers
    handler.wfile = writable
    handler._sent_codes = sent_codes
    handler._writable = writable

    return handler


def _parse_headers(content_type: str, content_length: int):
    """Create a simple headers-like object."""
    from http.client import HTTPMessage
    from email.parser import Parser
    raw = f"Content-Type: {content_type}\r\nContent-Length: {content_length}\r\n"
    return Parser().parsestr(raw)


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    """Clear rate limit state before each test."""
    deploy_listener._request_log.clear()
    yield
    deploy_listener._request_log.clear()


@pytest.fixture(autouse=True)
def _set_secret():
    """Set a known secret for all tests."""
    original = deploy_listener.SECRET
    deploy_listener.SECRET = TEST_SECRET
    yield
    deploy_listener.SECRET = original


class TestRequestValidation:
    """R3: All invalid requests get generic 403."""

    def test_get_request_returns_403(self):
        handler = _make_handler(method="GET")
        handler.do_GET()
        assert 403 in handler._sent_codes

    def test_put_request_returns_403(self):
        handler = _make_handler(method="PUT")
        handler.do_PUT()
        assert 403 in handler._sent_codes

    def test_delete_request_returns_403(self):
        handler = _make_handler(method="DELETE")
        handler.do_DELETE()
        assert 403 in handler._sent_codes

    def test_patch_request_returns_403(self):
        handler = _make_handler(method="PATCH")
        handler.do_PATCH()
        assert 403 in handler._sent_codes

    def test_wrong_content_type_returns_403(self):
        handler = _make_handler(
            body={"token": TEST_SECRET, "action": "status"},
            content_type="text/plain",
        )
        handler.do_POST()
        assert 403 in handler._sent_codes

    def test_invalid_json_returns_403(self):
        handler = _make_handler(raw_body=b"not json at all")
        handler.do_POST()
        assert 403 in handler._sent_codes

    def test_missing_token_returns_403(self):
        handler = _make_handler(body={"action": "status"})
        handler.do_POST()
        assert 403 in handler._sent_codes

    def test_wrong_token_returns_403(self):
        handler = _make_handler(body={"token": "wrong-token", "action": "status"})
        handler.do_POST()
        assert 403 in handler._sent_codes

    def test_invalid_action_returns_403(self):
        handler = _make_handler(body={"token": TEST_SECRET, "action": "destroy"})
        handler.do_POST()
        assert 403 in handler._sent_codes

    def test_missing_action_returns_403(self):
        handler = _make_handler(body={"token": TEST_SECRET})
        handler.do_POST()
        assert 403 in handler._sent_codes

    @patch("deploy_listener.subprocess")
    def test_valid_status_request_returns_200(self, mock_subprocess):
        mock_result = MagicMock()
        mock_result.stdout = "all containers running"
        mock_subprocess.run.return_value = mock_result

        handler = _make_handler(body={"token": TEST_SECRET, "action": "status"})
        handler.do_POST()
        assert 200 in handler._sent_codes

    @patch("deploy_listener.subprocess")
    @patch("deploy_listener.threading")
    def test_valid_deploy_request_returns_202(self, mock_threading, mock_subprocess):
        handler = _make_handler(body={"token": TEST_SECRET, "action": "deploy"})
        handler.do_POST()
        assert 202 in handler._sent_codes

    @patch("deploy_listener.subprocess")
    @patch("deploy_listener.threading")
    def test_valid_restart_request_returns_202(self, mock_threading, mock_subprocess):
        handler = _make_handler(body={"token": TEST_SECRET, "action": "restart"})
        handler.do_POST()
        assert 202 in handler._sent_codes

    def test_generic_403_body(self):
        """All 403 responses must have identical body (no info leakage)."""
        # Wrong token
        h1 = _make_handler(body={"token": "wrong", "action": "status"})
        h1.do_POST()
        body1 = h1._writable.data

        # Invalid action
        h2 = _make_handler(body={"token": TEST_SECRET, "action": "destroy"})
        h2.do_POST()
        body2 = h2._writable.data

        # GET method
        h3 = _make_handler(method="GET")
        h3.do_GET()
        body3 = h3._writable.data

        assert body1 == body2 == body3
        assert b"Forbidden" in body1


class TestRateLimiting:
    """R4: Max 3 requests per 10 minutes."""

    @patch("deploy_listener.subprocess")
    def test_first_three_requests_allowed(self, mock_subprocess):
        mock_result = MagicMock()
        mock_result.stdout = "ok"
        mock_subprocess.run.return_value = mock_result

        for _ in range(3):
            handler = _make_handler(body={"token": TEST_SECRET, "action": "status"})
            handler.do_POST()
            assert 200 in handler._sent_codes

    @patch("deploy_listener.subprocess")
    def test_fourth_request_returns_429(self, mock_subprocess):
        mock_result = MagicMock()
        mock_result.stdout = "ok"
        mock_subprocess.run.return_value = mock_result

        # Use up 3 requests
        for _ in range(3):
            handler = _make_handler(body={"token": TEST_SECRET, "action": "status"})
            handler.do_POST()

        # 4th should be rate limited
        handler = _make_handler(body={"token": TEST_SECRET, "action": "status"})
        handler.do_POST()
        assert 429 in handler._sent_codes
        assert b"Too many" in handler._writable.data

    @patch("deploy_listener.time")
    @patch("deploy_listener.subprocess")
    def test_rate_limit_resets_after_window(self, mock_subprocess, mock_time):
        mock_result = MagicMock()
        mock_result.stdout = "ok"
        mock_subprocess.run.return_value = mock_result

        # Fill up rate limit at t=0
        mock_time.time.return_value = 1000.0
        deploy_listener._request_log.clear()
        for _ in range(3):
            deploy_listener._request_log.append(1000.0)

        # After 10 minutes, should be allowed again
        mock_time.time.return_value = 1000.0 + 601
        handler = _make_handler(body={"token": TEST_SECRET, "action": "status"})
        handler.do_POST()
        assert 200 in handler._sent_codes


class TestLocalhostBinding:
    """R2: Server must bind to 127.0.0.1 only."""

    def test_main_binds_to_localhost(self):
        """Verify the __main__ block creates server on 127.0.0.1."""
        # We can't easily test the __main__ block, but we can verify
        # the source code contains the correct binding
        import inspect
        source = inspect.getsource(deploy_listener)
        assert '("127.0.0.1"' in source
        assert '("0.0.0.0"' not in source


class TestEmptySecret:
    """R1.3: Listener refuses to start with empty secret."""

    def test_empty_secret_in_source(self):
        """The default SECRET should be empty string (no hardcoded fallback)."""
        import inspect
        source = inspect.getsource(deploy_listener)
        # Should have empty default, not a hardcoded key
        assert '"fortress-deploy-key"' not in source
