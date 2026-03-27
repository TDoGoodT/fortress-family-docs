#!/usr/bin/env python3
"""
Fortress Deploy Listener — lightweight HTTP server running on the Mac Mini HOST.
Listens for deploy/restart commands from the Fortress container.

Usage:
    DEPLOY_SECRET=<secret> python3 deploy_listener.py

Runs on port 9111, localhost only.
"""

import http.server
import json
import logging
import os
import subprocess
import threading
import time
from pathlib import Path

PORT = int(os.getenv("DEPLOY_LISTENER_PORT", "9111"))
SECRET = os.getenv("DEPLOY_SECRET", "")
DEPLOY_SCRIPT = Path(__file__).parent / "deploy.sh"
VALID_ACTIONS = ("deploy", "restart", "status")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("deploy-listener")

# ── Rate limiting ────────────────────────────────────────────────
RATE_LIMIT = 3
RATE_WINDOW = 600  # 10 minutes in seconds
_request_log: list[float] = []


def _check_rate_limit() -> bool:
    """Return True if request is allowed, False if rate-limited."""
    now = time.time()
    _request_log[:] = [t for t in _request_log if now - t < RATE_WINDOW]
    if len(_request_log) >= RATE_LIMIT:
        return False
    _request_log.append(now)
    return True


# ── Generic error responses ──────────────────────────────────────
_FORBIDDEN = json.dumps({"error": "Forbidden"}).encode()
_RATE_LIMITED = json.dumps({"error": "Too many deploy requests. Wait 10 minutes."}).encode()


class DeployHandler(http.server.BaseHTTPRequestHandler):
    """Hardened deploy request handler with validation and rate limiting."""

    # Reject all non-POST methods with generic 403
    def do_GET(self):
        self._reject("non-POST method: GET")

    def do_PUT(self):
        self._reject("non-POST method: PUT")

    def do_DELETE(self):
        self._reject("non-POST method: DELETE")

    def do_PATCH(self):
        self._reject("non-POST method: PATCH")

    def do_POST(self):
        client_ip = self.client_address[0]

        # Validate Content-Type
        content_type = self.headers.get("Content-Type", "")
        if content_type != "application/json":
            self._reject("wrong content-type", client_ip=client_ip)
            return

        # Parse JSON body
        try:
            content_len = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_len)) if content_len else {}
        except (json.JSONDecodeError, ValueError):
            self._reject("invalid JSON", client_ip=client_ip)
            return

        # Validate token
        token = body.get("token", "")
        if not SECRET or token != SECRET:
            self._reject("token mismatch", client_ip=client_ip)
            return

        # Validate action
        action = body.get("action", "")
        if action not in VALID_ACTIONS:
            self._reject("invalid action", client_ip=client_ip)
            return

        # Rate limit check
        if not _check_rate_limit():
            logger.warning("Deploy request REJECTED: ip=%s reason=rate_limited", client_ip)
            self._send_json(429, _RATE_LIMITED)
            return

        # Valid request
        logger.info("Deploy request: action=%s ip=%s valid=True", action, client_ip)

        if action == "status":
            result = subprocess.run(
                ["bash", str(DEPLOY_SCRIPT), "status"],
                capture_output=True, text=True, timeout=15,
            )
            self._send_json(200, json.dumps({
                "status": "ok",
                "output": result.stdout.strip(),
            }).encode())
        else:
            threading.Thread(
                target=self._run_deploy, args=(action,), daemon=True
            ).start()
            self._send_json(202, json.dumps({
                "status": "accepted",
                "message": f"{action} started",
            }).encode())

    def _reject(self, reason: str, *, client_ip=None):
        """Return generic 403 and log the internal reason."""
        ip = client_ip or self.client_address[0]
        logger.warning("Deploy request REJECTED: ip=%s reason=%s", ip, reason)
        self._send_json(403, _FORBIDDEN)

    def _send_json(self, code: int, data: bytes):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def _run_deploy(self, action: str):
        try:
            result = subprocess.run(
                ["bash", str(DEPLOY_SCRIPT), action],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode == 0:
                logger.info("%s completed successfully", action)
                # After deploy, sync self from repo
                if action == "deploy":
                    self._sync_self()
                self._notify(f"✅ {action} הושלם בהצלחה")
            else:
                logger.error("%s failed: %s", action, result.stderr)
                self._notify(f"❌ {action} נכשל:\n{result.stderr[-200:]}")
        except Exception:
            logger.exception("%s crashed", action)
            self._notify(f"❌ {action} קרסה")

    def _sync_self(self):
        """Copy updated deploy_listener.py from repo to ~/fortress-scripts/."""
        try:
            repo_dir = os.getenv("FORTRESS_REPO_DIR", "")
            if not repo_dir:
                return
            src = os.path.join(repo_dir, "fortress", "scripts", "deploy_listener.py")
            dst = os.path.expanduser("~/fortress-scripts/deploy_listener.py")
            if os.path.exists(src):
                import shutil
                shutil.copy2(src, dst)
                logger.info("Synced deploy_listener.py from repo")
        except Exception:
            logger.exception("Failed to sync deploy_listener.py")

    def _notify(self, message: str):
        """Send WhatsApp notification via fortress-app."""
        import urllib.request
        try:
            admin_phone = os.getenv("ADMIN_PHONE", "")
            waha_url = os.getenv("WAHA_URL", "http://localhost:3000")
            waha_key = os.getenv("WAHA_API_KEY", "")
            if not admin_phone:
                return
            payload = json.dumps({
                "chatId": f"{admin_phone}@c.us",
                "text": message,
                "session": "default",
            }).encode()
            req = urllib.request.Request(
                f"{waha_url}/api/sendText",
                data=payload,
                headers={"Content-Type": "application/json", "X-Api-Key": waha_key},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            logger.exception("Failed to send deploy notification")

    def log_message(self, format, *args):
        """Suppress default BaseHTTPRequestHandler logging (we use our own)."""
        pass


if __name__ == "__main__":
    if not SECRET:
        logger.error("DEPLOY_SECRET not set. Exiting.")
        raise SystemExit(1)

    # SECURITY: Listen on localhost only.
    # Only fortress-app container (via Docker network / host.docker.internal) can reach this.
    # External access is blocked.
    server = http.server.HTTPServer(("127.0.0.1", PORT), DeployHandler)
    logger.info("Deploy listener running on 127.0.0.1:%d", PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down")
        server.shutdown()
