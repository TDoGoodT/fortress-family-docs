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

# Exact trigger phrases — no fuzzy matching, no LLM interpretation
_DEPLOY_TRIGGER  = re.compile(r"^פורטרס שדרג מערכת$")
_RESTART_TRIGGER = re.compile(r"^פורטרס הפעל מחדש$")
_STATUS_TRIGGER  = re.compile(r"^פורטרס סטטוס$")


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
            (_DEPLOY_TRIGGER,  "deploy"),
            (_RESTART_TRIGGER, "restart"),
            (_STATUS_TRIGGER,  "status"),
        ]

    def execute(self, db: Session, member: FamilyMember, command: Command) -> Result:
        if member.role != "parent":
            return Result(success=False, message="רק הורים יכולים לעדכן את המערכת 🔒")

        if not config.DEPLOY_SECRET:
            return Result(success=False, message=TEMPLATES["deploy_not_configured"])

        logger.info("Deploy action=%s requested by member=%s phone=%s", command.action, member.name, member.phone)
        return self._call_listener(command.action, sender=member.name)

    def verify(self, db: Session, result: Result) -> bool:
        return result.success

    def get_help(self) -> str:
        return (
            "פורטרס שדרג מערכת — git pull + rebuild + restart\n"
            "פורטרס הפעל מחדש — הפעלה מחדש של פורטרס\n"
            "פורטרס סטטוס — בדיקת סטטוס הקונטיינרים"
        )

    def _call_listener(self, action: str, sender: str = "") -> Result:
        """Send HTTP request to the deploy listener on the host."""
        try:
            resp = httpx.post(
                config.DEPLOY_LISTENER_URL,
                json={"token": config.DEPLOY_SECRET, "action": action, "sender": sender},
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
