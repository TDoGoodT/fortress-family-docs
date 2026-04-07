"""Fortress Skills Engine — DevSkill: codebase intelligence and feature planning.

Admin-only skill that exposes codebase indexing, querying, and planning
via WhatsApp. All operations require ``member.is_admin == True``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from src.models.schema import FamilyMember
from src.services import audit
from src.services.codebase_indexer import (
    build_index,
    ensure_fresh,
    is_stale,
    load_index,
    retrieve_relevant_context,
)
from src.skills.base_skill import BaseSkill, Command, Result

logger = logging.getLogger(__name__)

# Maximum WhatsApp message length before saving to file
_MAX_WHATSAPP_CHARS = 500

# Data output directory for long responses
_DEV_OUTPUTS_DIR = Path("fortress/data/dev_outputs")


def _resolve_dev_outputs_dir() -> Path:
    """Return the dev_outputs directory, creating it if needed."""
    cwd = Path.cwd()
    if (cwd / "data").is_dir():
        out = cwd / "data" / "dev_outputs"
    elif (cwd / "fortress" / "data").is_dir():
        out = cwd / "fortress" / "data" / "dev_outputs"
    else:
        out = _DEV_OUTPUTS_DIR
    out.mkdir(parents=True, exist_ok=True)
    return out


def _reconstruct_plan_from_markdown(markdown_text: str) -> "Any":
    """Reconstruct a Plan object from a saved plan Markdown file.

    Parses the Markdown sections back into AttributedClaim lists.
    Falls back to a minimal Plan if parsing fails.
    """
    from src.services.feature_planner import AttributedClaim, Plan

    # Extract request_summary from the title line
    request_summary = ""
    for line in markdown_text.splitlines():
        if line.startswith("# Feature Plan:"):
            request_summary = line[len("# Feature Plan:"):].strip()
            break
        if line.startswith("# "):
            request_summary = line[2:].strip()
            break

    def _parse_section(text: str, header: str) -> list[AttributedClaim]:
        """Extract claims from a Markdown section."""
        claims: list[AttributedClaim] = []
        in_section = False
        for line in text.splitlines():
            if line.startswith(f"## {header}"):
                in_section = True
                continue
            if in_section and line.startswith("## "):
                break
            if in_section and line.startswith("- "):
                # Parse: "- claim text (`source_path`) _[attribution]_"
                content = line[2:]
                # Extract attribution
                attribution = "llm_assumption"
                attr_match = re.search(r"_\[(\w+)\]_", content)
                if attr_match:
                    attribution = attr_match.group(1)
                    content = content[:attr_match.start()].strip()
                # Extract source_path
                source_path = None
                sp_match = re.search(r"\(`([^`]+)`\)", content)
                if sp_match:
                    source_path = sp_match.group(1)
                    content = content[:sp_match.start()].strip()
                claims.append(AttributedClaim(
                    text=content,
                    attribution=attribution,
                    source_path=source_path,
                ))
        return claims

    return Plan(
        request_summary=request_summary or "Feature plan",
        relevant_components=_parse_section(markdown_text, "Relevant Components"),
        missing_components=_parse_section(markdown_text, "Missing Components"),
        files_to_modify=_parse_section(markdown_text, "Files to Modify"),
        breaking_change_risks=_parse_section(markdown_text, "Breaking Change Risks"),
        development_tasks=_parse_section(markdown_text, "Development Tasks"),
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def _extract_layer_for_query(question: str, index: dict) -> list[dict]:
    """When keyword search returns nothing, check if the query asks about
    an entire layer (all skills, all tools, etc.) and return that layer."""
    q = question.lower()
    layers = index.get("layers", {})

    # Map query keywords to index layers
    layer_keywords = {
        "skills": ("skills", ["name", "description", "commands", "source_file"]),
        "skill": ("skills", ["name", "description", "commands", "source_file"]),
        "tools": ("tools", ["tool_name", "skill", "action", "description"]),
        "tool": ("tools", ["tool_name", "skill", "action", "description"]),
        "services": ("services", ["file_path", "classes", "public_methods"]),
        "service": ("services", ["file_path", "classes", "public_methods"]),
        "models": ("models", ["class_name", "table_name", "columns", "relationships"]),
        "model": ("models", ["class_name", "table_name", "columns", "relationships"]),
        "migrations": ("migrations", ["filename", "description"]),
        "migration": ("migrations", ["filename", "description"]),
    }

    for keyword, (layer_name, _fields) in layer_keywords.items():
        if keyword in q:
            entries = layers.get(layer_name, [])
            if entries:
                return [{"layer": layer_name, **e} for e in entries]

    return []


class DevSkill(BaseSkill):
    """Admin-only skill for codebase intelligence and feature planning."""

    @property
    def name(self) -> str:
        return "dev"

    @property
    def description(self) -> str:
        return "ניתוח קוד, שאילתות מבנה ותכנון פיצ׳רים (מנהל בלבד)"

    @property
    def commands(self) -> list[tuple[re.Pattern, str]]:
        return [
            (re.compile(r"^(אנדקס|index|תאנדקס)$", re.IGNORECASE), "index"),
            (re.compile(r"^dev\s+query\s+(?P<question>.+)$", re.IGNORECASE), "query"),
            (re.compile(r"^dev\s+plan\s+(?P<feature_request>.+)$", re.IGNORECASE), "plan"),
            (re.compile(r"^(צור פרומפט|generate prompt|תייצר prompt)\s*(?P<plan_filename>.+)?$", re.IGNORECASE), "generate_prompt"),
        ]

    def execute(self, db: Session, member: FamilyMember, command: Command) -> Result:
        # Admin-only gate — first check before any action
        if not member.is_admin:
            return Result(
                success=False,
                message="אין לך הרשאה לפקודות פיתוח 🔒",
            )

        dispatch = {
            "index": self._handle_index,
            "query": self._handle_query,
            "plan": self._handle_plan,
            "generate_prompt": self._handle_generate_prompt,
        }
        handler = dispatch.get(command.action)
        if handler is None:
            return Result(success=False, message="פעולה לא מוכרת. נסה: index, query, plan, generate_prompt")
        return handler(db, member, command)

    def verify(self, db: Session, result: Result) -> bool:
        return result.success

    def get_help(self) -> str:
        return (
            "dev index — בניית אינדקס של קוד המקור\n"
            "dev query <שאלה> — שאילתה על מבנה הקוד\n"
            "dev plan <תיאור פיצ׳ר> — תכנון פיצ׳ר חדש"
        )

    # ------------------------------------------------------------------
    # Action: index
    # ------------------------------------------------------------------

    def _handle_index(
        self, db: Session, member: FamilyMember, command: Command
    ) -> Result:
        """Build (or rebuild) the codebase index."""
        try:
            index = build_index(force=True)
        except Exception as exc:
            logger.exception("Index build failed")
            return Result(success=False, message=f"בניית אינדקס נכשלה: {exc}")

        layers = index.get("layers", {})
        summary = (
            f"✅ אינדקס נבנה בהצלחה\n"
            f"📁 מודולים: {len(layers.get('modules', []))}\n"
            f"🎯 Skills: {len(layers.get('skills', []))}\n"
            f"🔧 Tools: {len(layers.get('tools', []))}\n"
            f"⚙️ Services: {len(layers.get('services', []))}\n"
            f"🗄️ Models: {len(layers.get('models', []))}\n"
            f"📋 Migrations: {len(layers.get('migrations', []))}"
        )

        audit.log_action(
            db,
            actor_id=member.id,
            action="index",
            resource_type="dev",
            details={"modules": len(layers.get("modules", []))},
        )

        return Result(
            success=True,
            message=summary,
            action="index",
            data={
                "modules": len(layers.get("modules", [])),
                "skills": len(layers.get("skills", [])),
                "tools": len(layers.get("tools", [])),
                "services": len(layers.get("services", [])),
                "models": len(layers.get("models", [])),
                "migrations": len(layers.get("migrations", [])),
            },
        )

    # ------------------------------------------------------------------
    # Action: query
    # ------------------------------------------------------------------

    def _handle_query(
        self, db: Session, member: FamilyMember, command: Command
    ) -> Result:
        """Answer a question about the codebase using the index + LLM."""
        question = command.params.get("question", command.raw_text).strip()
        if not question:
            return Result(success=False, message="נא לציין שאלה. דוגמה: dev query מה ה-skills שיש?")

        # Ensure index is fresh
        if is_stale():
            try:
                build_index()
            except Exception:
                logger.warning("Auto re-index failed, proceeding with stale/missing index")

        # Retrieve relevant context
        context_entries = retrieve_relevant_context(question)
        if not context_entries:
            # If keyword search found nothing, check if the query is asking
            # about a whole layer (all skills, all tools, etc.) and pass that
            index = load_index()
            if index is None:
                return Result(
                    success=False,
                    message="אין אינדקס זמין. הרץ קודם: dev index",
                )
            context_entries = _extract_layer_for_query(question, index)

        # Build context string for LLM
        context_text = json.dumps(context_entries, indent=2, ensure_ascii=False)

        # Call BedrockClient synchronously
        try:
            response_text = self._query_llm(question, context_text)
        except Exception as exc:
            logger.exception("LLM query failed")
            return Result(success=False, message=f"שאילתת LLM נכשלה: {exc}")

        # Tag with source attribution
        if context_entries:
            response_text += "\n\n---\n_מקורות: indexed_fact (מהאינדקס), inferred_pattern (מסקנות)_"
        else:
            response_text += "\n\n---\n_מקור: llm_assumption (הנחת LLM ללא אינדקס)_"

        # If response is long, save to file
        message = response_text
        if len(response_text) > _MAX_WHATSAPP_CHARS:
            file_path = self._save_dev_output(question, response_text)
            # Send summary only
            summary_cutoff = response_text[:400].rsplit("\n", 1)[0]
            message = f"{summary_cutoff}\n\n📄 תשובה מלאה נשמרה: {file_path.name}"

        audit.log_action(
            db,
            actor_id=member.id,
            action="query",
            resource_type="dev",
            details={"question": question[:200]},
        )

        return Result(success=True, message=message, action="query")

    def _query_llm(self, question: str, context: str) -> str:
        """Call BedrockClient.converse() synchronously for a query."""
        from src.services.bedrock_client import BedrockClient

        client = BedrockClient()
        system_prompt = (
            "You are a codebase analysis assistant for the Fortress project. "
            "Answer the developer's question based on the provided codebase index data. "
            "Tag each claim with its source:\n"
            "- [indexed_fact] for facts directly from the index\n"
            "- [inferred_pattern] for patterns you observe across the data\n"
            "- [llm_assumption] for claims not grounded in the provided data\n"
            "Answer in Hebrew when the question is in Hebrew. Be concise."
        )
        messages = [
            {
                "role": "user",
                "content": [
                    {"text": f"Codebase index context:\n{context}\n\nQuestion: {question}"},
                ],
            }
        ]

        # Run async converse() in sync context via async_bridge
        from src.utils.async_bridge import run_async
        from src.services.model_selector import select_model
        model_id = select_model("chat_question")  # strong tier for queries

        response = run_async(client.converse(
            messages=messages,
            system_prompt=system_prompt,
            model=model_id,
            max_tokens=2048,
        ), timeout=60)

        return response.text or "לא הצלחתי לייצר תשובה."

    # ------------------------------------------------------------------
    # Action: plan
    # ------------------------------------------------------------------

    def _handle_plan(
        self, db: Session, member: FamilyMember, command: Command
    ) -> Result:
        """Invoke the feature planner to generate an implementation plan."""
        feature_request = command.params.get("feature_request", command.raw_text).strip()
        if not feature_request:
            return Result(success=False, message="נא לתאר את הפיצ׳ר הרצוי.")

        try:
            from src.services.feature_planner import (
                generate_plan,
                plan_summary,
                save_plan_markdown,
            )

            # Run async generate_plan() in sync context via async_bridge
            from src.utils.async_bridge import run_async
            plan = run_async(generate_plan(feature_request), timeout=120)

            # Save plan as Markdown
            saved_path = save_plan_markdown(plan, feature_request)

            # Build WhatsApp summary
            summary = plan_summary(plan)
            message = f"{summary}\n\n📄 תכנית מלאה נשמרה: {saved_path.name}"

        except Exception as exc:
            logger.exception("Feature planning failed")
            return Result(success=False, message=f"תכנון פיצ׳ר נכשל: {exc}")

        audit.log_action(
            db,
            actor_id=member.id,
            action="plan",
            resource_type="dev",
            details={"feature_request": feature_request[:200]},
        )

        return Result(success=True, message=message, action="plan")

    # ------------------------------------------------------------------
    # Action: generate_prompt
    # ------------------------------------------------------------------

    def _handle_generate_prompt(
        self, db: Session, member: FamilyMember, command: Command
    ) -> Result:
        """Generate a Task_Prompt from a saved Plan."""
        from src.services import coding_agent_bridge
        from src.services.feature_planner import _parse_plan_response

        # Determine plan filename
        plan_filename = command.params.get("plan_filename", "").strip()
        if not plan_filename and command.raw_text:
            # Try to extract from raw text after the trigger phrase
            raw = command.raw_text.strip()
            for trigger in ("צור פרומפט", "generate prompt", "תייצר prompt"):
                if raw.lower().startswith(trigger.lower()):
                    plan_filename = raw[len(trigger):].strip()
                    break

        # If still no filename, find the most recent .md in plans dir
        if not plan_filename:
            from src.services.feature_planner import _resolve_plans_dir
            plans_dir = _resolve_plans_dir()
            md_files = sorted(plans_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not md_files:
                return Result(success=False, message="לא נמצאו קבצי תכנית. הרץ קודם: dev plan <תיאור>")
            plan_filename = md_files[0].name

        # Locate the plan file
        from src.services.feature_planner import _resolve_plans_dir
        plans_dir = _resolve_plans_dir()
        plan_path = plans_dir / plan_filename
        if not plan_path.exists():
            return Result(success=False, message=f"קובץ תכנית לא נמצא: {plan_filename}")

        # Read and parse the plan Markdown back into a Plan object
        try:
            plan_text = plan_path.read_text(encoding="utf-8")
        except OSError as exc:
            return Result(success=False, message=f"שגיאה בקריאת קובץ תכנית: {exc}")

        # Reconstruct Plan from the saved Markdown using _parse_plan_response
        # The saved Markdown is not JSON, so we use a best-effort reconstruction
        plan = _reconstruct_plan_from_markdown(plan_text)

        # Delegate to bridge
        try:
            result = coding_agent_bridge.generate_prompt(plan, plan_filename)
        except Exception as exc:
            logger.exception("generate_prompt failed")
            return Result(success=False, message=f"יצירת פרומפט נכשלה: {exc}")

        # Audit log
        audit.log_action(
            db,
            actor_id=member.id,
            action="generate_prompt",
            resource_type="dev",
            details={
                "plan_filename": plan_filename,
                "prompt_filename": result.prompt_path.name if result.prompt_path else None,
            },
        )

        return Result(
            success=result.success,
            message=result.message,
            action="generate_prompt",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _save_dev_output(question: str, content: str) -> Path:
        """Save a long response as Markdown in the dev_outputs directory."""
        out_dir = _resolve_dev_outputs_dir()
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        # Sanitize question for filename
        safe_name = re.sub(r"[^\w\s-]", "", question[:40]).strip().replace(" ", "_")
        filename = f"{timestamp}_{safe_name}.md"
        file_path = out_dir / filename
        file_path.write_text(
            f"# Dev Query: {question}\n\n{content}\n",
            encoding="utf-8",
        )
        return file_path
