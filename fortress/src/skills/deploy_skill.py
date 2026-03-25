"""Fortress Skills Engine — deploy skill: remote update & restart via WhatsApp.

Architecture:
- The Fortress app runs INSIDE Docker.
- A lightweight deploy_listener.py runs on the Mac Mini HOST (127.0.0.1:9111).
- This skill sends HTTP requests to the listener, which runs git pull / docker compose.
- Parent role required. Token from config, never hardcoded.
"""

from __future__ import annotations

import logging
import re

import httpx
from sqlalchemy.orm import Session

from src import config
from src.models.schema import FamilyMember
from src.prompts.personality import TEMPLATES
from src.skills.base_skill import BaseSkill, Command, Result

logger = logging.getLogger(__name__)


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
            (re.compile(r"^(עדכן מערכת|deploy|עדכון|פרוס)$", re.IGNORECASE), "deploy"),
            (re.compile(r"^(ריסטארט|restart|הפעל מחדש)$", re.IGNORECASE), "restart"),
            (re.compile(r"^(סטטוס מערכת|status)$", re.IGNORECASE), "status"),
        ]

    def execute(self, db: Session, member: FamilyMember, command: Command) -> Result:
        # Parent-only check
        if member.role != "parent":
            return Result(success=False, message="רק הורים יכולים לעדכן את המערכת 🔒")

        # Fail closed if secret not configured
        if not config.DEPLOY_SECRET:
            return Result(success=False, message=TEMPLATES["deploy_not_configured"])

        action = command.action
        return self._call_listener(action)

    def verify(self, db: Session, result: Result) -> bool:
        return result.success

    def get_help(self) -> str:
        return (
            "עדכן מערכת — git pull + rebuild + restart\n"
            "ריסטארט — הפעלה מחדש של פורטרס\n"
            "סטטוס מערכת — בדיקת סטטוס הקונטיינרים"
        )

    def _call_listener(self, action: str) -> Result:
        """Send HTTP request to the deploy listener on the host."""
        try:
            resp = httpx.post(
                config.DEPLOY_LISTENER_URL,
                json={"token": config.DEPLOY_SECRET, "action": action},
                headers={"Content-Type": "application/json"},
                timeout=20.0,
            )

            if resp.status_code == 429:
                return Result(success=False, message=TEMPLATES["deploy_rate_limited"])

            if resp.status_code == 403:
                return Result(
                    success=False,
                    message=TEMPLATES["deploy_failed"].format(details="אימות נכשל"),
                )

            body = resp.json()

            if action == "status":
                output = body.get("output", "אין מידע")
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

            # deploy
            return Result(
                success=True,
                message=TEMPLATES["deploy_started"],
                action="deploy",
                data={"async": True},
            )

        except httpx.ConnectError:
            logger.exception("Deploy listener unreachable")
            return Result(
                success=False,
                message=TEMPLATES["deploy_failed"].format(details="לא ניתן להתחבר לשרת העדכון"),
            )
        except Exception as e:
            logger.exception("Deploy request failed")
            return Result(
                success=False,
                message=TEMPLATES["deploy_failed"].format(details=str(e)),
            )
