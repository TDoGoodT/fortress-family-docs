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
REPO_DIR = os.getenv("FORTRESS_REPO_DIR", str(Path(__file__).parent.parent.parent))
DEPLOY_SCRIPT = Path(__file__).parent / "deploy.sh"
VALID_ACTIONS = ("deploy", "restart", "status")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("deploy-listener")

# ── Rate limiting: 1 deploy per 10 minutes ──────────────────────
RATE_LIMIT = 1
RATE_WINDOW = 600
_request_log: list[float] = []


def _check_rate_limit() -> bool:
    now = time.time()
    _request_log[:] = [t for t in _request_log if now - t < RATE_WINDOW]
    if len(_request_log) >= RATE_LIMIT:
        return False
    _request_log.append(now)
    return True


_FORBIDDEN    = json.dumps({"error": "Forbidden"}).encode()
_RATE_LIMITED = json.dumps({"error": "Too many deploy requests. Wait 10 minutes."}).encode()


def _get_commit_hash() -> str:
    try:
        result = subprocess.run(
            ["git", "-C", REPO_DIR, "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


class DeployHandler(http.server.BaseHTTPRequestHandler):

    def do_GET(self):    self._reject("non-POST method: GET")
    def do_PUT(self):    self._reject("non-POST method: PUT")
    def do_DELETE(self): self._reject("non-POST method: DELETE")
    def do_PATCH(self):  self._reject("non-POST method: PATCH")

    def do_POST(self):
        client_ip = self.client_address[0]

        if self.headers.get("Content-Type", "") != "application/json":
            self._reject("wrong content-type", client_ip=client_ip)
            return

        try:
            content_len = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_len)) if content_len else {}
        except (json.JSONDecodeError, ValueError):
            self._reject("invalid JSON", client_ip=client_ip)
            return

        token = body.get("token", "")
        if not SECRET or token != SECRET:
            self._reject("token mismatch", client_ip=client_ip)
            return

        action = body.get("action", "")
        if action not in VALID_ACTIONS:
            self._reject("invalid action", client_ip=client_ip)
            return

        # status is exempt from rate limiting
        if action != "status" and not _check_rate_limit():
            logger.warning("Deploy REJECTED: ip=%s reason=rate_limited", client_ip)
            self._send_json(429, _RATE_LIMITED)
            return

        sender = body.get("sender", "unknown")
        logger.info("Deploy request: action=%s sender=%s ip=%s", action, sender, client_ip)

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
                target=self._run_deploy, args=(action, sender), daemon=True
            ).start()
            self._send_json(202, json.dumps({
                "status": "accepted",
                "message": f"{action} started",
            }).encode())

    def _reject(self, reason: str, *, client_ip=None):
        ip = client_ip or self.client_address[0]
        logger.warning("Deploy REJECTED: ip=%s reason=%s", ip, reason)
        self._send_json(403, _FORBIDDEN)

    def _send_json(self, code: int, data: bytes):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def _run_deploy(self, action: str, sender: str):
        commit_before = _get_commit_hash()
        try:
            result = subprocess.run(
                ["bash", str(DEPLOY_SCRIPT), action],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode == 0:
                commit_after = _get_commit_hash()
                now = time.strftime("%H:%M")
                logger.info(
                    "%s completed: sender=%s commit=%s->%s",
                    action, sender, commit_before, commit_after,
                )
                if action == "deploy":
                    self._sync_self()
                    msg = f"✅ Deploy הושלם\nCommit: {commit_after}\nTime: {now}"
                else:
                    msg = f"✅ {action} הושלם\nTime: {now}"
                self._notify(msg)
            else:
                logger.error("%s failed: sender=%s error=%s", action, sender, result.stderr[-300:])
                self._notify(f"❌ {action} נכשל:\n{result.stderr[-200:]}")
        except Exception:
            logger.exception("%s crashed: sender=%s", action, sender)
            self._notify(f"❌ {action} קרסה")

    def _sync_self(self):
        """Copy updated scripts from repo to scripts dir after deploy."""
        try:
            repo_dir = os.getenv("FORTRESS_REPO_DIR", "")
            if not repo_dir:
                return
            import shutil
            scripts_dir = Path(__file__).parent
            for script in ["deploy_listener.py", "deploy.sh"]:
                src = Path(repo_dir) / "fortress" / "scripts" / script
                dst = scripts_dir / script
                if src.exists() and src.resolve() != dst.resolve():
                    shutil.copy2(src, dst)
                    logger.info("Synced %s from repo", script)
        except Exception:
            logger.exception("Failed to sync scripts")

    def _notify(self, message: str):
        import urllib.request
        try:
            admin_phone = os.getenv("ADMIN_PHONE", "")
            waha_url = os.getenv("WAHA_URL", "http://localhost:3000")
            waha_key = os.getenv("WAHA_API_KEY", "")
            if not admin_phone:
                logger.warning("Notify skipped: ADMIN_PHONE not set")
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
            resp = urllib.request.urlopen(req, timeout=10)
            logger.info("Notify sent: phone=%s status=%s", admin_phone, resp.status)
        except Exception:
            logger.exception("Failed to send deploy notification")

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    if not SECRET:
        logger.error("DEPLOY_SECRET not set. Exiting.")
        raise SystemExit(1)

    # Sync deploy.sh from repo on startup
    repo_dir = os.getenv("FORTRESS_REPO_DIR", "")
    if repo_dir:
        import shutil
        src = Path(repo_dir) / "fortress" / "scripts" / "deploy.sh"
        dst = Path(__file__).parent / "deploy.sh"
        if src.exists() and src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
            logger.info("Synced deploy.sh from repo on startup")

    server = http.server.HTTPServer(("127.0.0.1", PORT), DeployHandler)
    logger.info("Deploy listener running on 127.0.0.1:%d repo=%s", PORT, REPO_DIR)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down")
        server.shutdown()
