from __future__ import annotations
"""Fortress Skills Engine — deploy skill: remote update & restart via WhatsApp.

Architecture:
- The Fortress app runs INSIDE Docker.
- A lightweight deploy_listener.py runs on the Mac Mini HOST (127.0.0.1:9111).
- This skill sends HTTP requests to the listener, which runs git pull / docker compose.
- Parent role required. Token from config, never hardcoded.

Security model:
- Exact trigger phrase required (no fuzzy matching)
- Token-based auth to the listener
- Cooldown enforced on the listener side (1 deploy / 10 min)
- Sender identity logged on every request
"""

import logging
import re

import httpx
from sqlalchemy.orm import Session

from src import config
from src.models.schema import FamilyMember
from src.prompts.personality import TEMPLATES
from src.skills.base_skill import BaseSkill, Command, Result

logger = logging.getLogger(__name__)

# Exact trigger phrases — no fuzzy matching, no LLM interpretation
_DEPLOY_APP_TRIGGER = re.compile(r"^פורטרס תתחדש\s*APP$", re.IGNORECASE)
_DEPLOY_DB_TRIGGER  = re.compile(r"^פורטרס תתחדש\s*DB$", re.IGNORECASE)
_DEPLOY_ALL_TRIGGER = re.compile(r"^פורטרס תתחדש\s*ALL$", re.IGNORECASE)
_DEPLOY_TRIGGER     = re.compile(r"^פורטרס תתחדש$")
_RESTART_TRIGGER    = re.compile(r"^(פורטרס הפעל מחדש|restart)$", re.IGNORECASE)
_STATUS_TRIGGER     = re.compile(r"^(פורטרס סטטוס|status)$", re.IGNORECASE)


class DeploySkill(BaseSkill):
    """Parent-only skill to pull, rebuild, and restart Fortress from WhatsApp."""

    @property
    def name(self) -> str:
        return "deploy"

    @property
    def description(self) -> str:
        return "עדכון ופריסה מרחוק (הורים בלבד)"

    @property
    def commands(self) -> list[tuple[re.Pattern, str]]:
        return [
            (_DEPLOY_APP_TRIGGER, "deploy_app"),
            (_DEPLOY_DB_TRIGGER,  "deploy_db"),
            (_DEPLOY_ALL_TRIGGER, "deploy_all"),
            (_DEPLOY_TRIGGER,     "deploy_all"),
            (_RESTART_TRIGGER,    "restart"),
            (_STATUS_TRIGGER,     "status"),
        ]

    def execute(self, db: Session, member: FamilyMember, command: Command) -> Result:
        if not member.is_admin:
            return Result(success=False, message="רק מנהל המערכת יכול לעדכן את המערכת 🔒")

        if not config.DEPLOY_SECRET:
            return Result(success=False, message=TEMPLATES["deploy_not_configured"])

        logger.info("Deploy action=%s requested by member=%s phone=%s", command.action, member.name, member.phone)
        return self._call_listener(command.action, sender=member.name)

    def verify(self, db: Session, result: Result) -> bool:
        return result.success

    def get_help(self) -> str:
        return (
            "פורטרס תתחדש — עדכון מלא (קוד + DB)\n"
            "פורטרס תתחדש APP — עדכון קוד בלבד (~30 שניות)\n"
            "פורטרס תתחדש DB — הרצת migrations בלבד\n"
            "פורטרס תתחדש ALL — עדכון מלא\n"
            "פורטרס הפעל מחדש — הפעלה מחדש של פורטרס\n"
            "פורטרס סטטוס — בדיקת סטטוס הקונטיינרים"
        )

    def _call_listener(self, action: str, sender: str = "") -> Result:
        """Send HTTP request to the deploy listener on the host."""
        _STARTED_TEMPLATES = {
            "deploy_app": "deploy_app_started",
            "deploy_db": "deploy_db_started",
            "deploy_all": "deploy_all_started",
        }
        try:
            resp = httpx.post(
                config.DEPLOY_LISTENER_URL,
                json={"token": config.DEPLOY_SECRET, "action": action, "sender": sender},
                headers={"Content-Type": "application/json"},
                timeout=45.0,
            )

            if resp.status_code == 429:
                return Result(success=False, message=TEMPLATES["deploy_rate_limited"])

            if resp.status_code == 403:
                return Result(
                    success=False,
                    message=TEMPLATES["deploy_failed"].format(details="אימות נכשל"),
                )

            body = self._safe_json(resp)

            if action == "status":
                output = body.get("output", "אין מידע")
                status_label = body.get("status")
                errors = body.get("errors") or []
                if isinstance(errors, list) and errors:
                    error_text = "\n".join(f"• {err}" for err in errors)
                    output = f"{output}\n\n⚠️ בדיקות חלקיות נכשלו:\n{error_text}"
                if status_label == "partial":
                    output = f"{output}\n\nℹ️ הסטטוס חלקי — בדוק לוגים אם צריך."
                return Result(
                    success=True,
                    message=TEMPLATES["deploy_status"].format(status=output),
                    action="status",
                )

            if action == "restart":
                return Result(
                    success=True,
                    message=TEMPLATES["deploy_restarted"],
                    action="restart",
                    data={"async": True},
                )

            template_key = _STARTED_TEMPLATES.get(action, "deploy_started")

            # Post-deploy hook: re-index codebase after successful deploy
            if action in ("deploy_app", "deploy_all"):
                self._post_deploy_reindex()

            return Result(
                success=True,
                message=TEMPLATES[template_key],
                action=action,
                data={"async": True},
            )

        except httpx.ConnectError:
            logger.exception("Deploy listener unreachable")
            return Result(
                success=False,
                message=TEMPLATES["deploy_failed"].format(details="לא ניתן להתחבר לשרת העדכון"),
            )
        except httpx.TimeoutException:
            logger.exception("Deploy listener timed out")
            return Result(
                success=False,
                message=TEMPLATES["deploy_failed"].format(
                    details="בדיקת הסטטוס לקחה יותר מדי זמן. נסה שוב בעוד כמה שניות"
                ),
            )
        except httpx.HTTPError:
            logger.exception("Deploy listener HTTP error")
            return Result(
                success=False,
                message=TEMPLATES["deploy_failed"].format(details="שגיאת תקשורת מול שרת העדכון"),
            )
        except Exception as e:
            logger.exception("Deploy request failed")
            return Result(
                success=False,
                message=TEMPLATES["deploy_failed"].format(details=str(e)),
            )

    def _post_deploy_reindex(self) -> None:
        """Post-deploy hook placeholder. Codebase indexer was removed."""
        pass

    @staticmethod
    def _safe_json(resp: httpx.Response) -> dict:
        """Parse listener JSON safely without crashing status flow."""
        try:
            body = resp.json()
            return body if isinstance(body, dict) else {"output": str(body)}
        except ValueError:
            text = (resp.text or "").strip()
            return {"output": text or "אין מידע"}
