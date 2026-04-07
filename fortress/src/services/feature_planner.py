"""Fortress Feature Planner — LLM-powered implementation planning.

Receives a natural-language feature request, performs gap analysis against
the Codebase_Index, and produces a structured Plan with source attribution.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.services.bedrock_client import BedrockClient
from src.services.codebase_indexer import (
    build_index,
    is_stale,
    load_index,
    retrieve_relevant_context,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class AttributedClaim:
    """A single claim tagged with its source attribution."""
    text: str
    attribution: str  # "indexed_fact" | "inferred_pattern" | "llm_assumption"
    source_path: str | None = None


@dataclass
class Plan:
    """Structured implementation plan produced by the Planner."""
    request_summary: str
    relevant_components: list[AttributedClaim] = field(default_factory=list)
    missing_components: list[AttributedClaim] = field(default_factory=list)
    files_to_modify: list[AttributedClaim] = field(default_factory=list)
    breaking_change_risks: list[AttributedClaim] = field(default_factory=list)
    development_tasks: list[AttributedClaim] = field(default_factory=list)
    created_at: str = ""  # ISO 8601


VALID_ATTRIBUTIONS = {"indexed_fact", "inferred_pattern", "llm_assumption"}

# Plans output directory
_PLANS_DIR = Path("fortress/data/plans")


def _resolve_plans_dir() -> Path:
    """Return the plans directory, creating it if needed."""
    cwd = Path.cwd()
    if (cwd / "data").is_dir():
        out = cwd / "data" / "plans"
    elif (cwd / "fortress" / "data").is_dir():
        out = cwd / "fortress" / "data" / "plans"
    else:
        out = _PLANS_DIR
    out.mkdir(parents=True, exist_ok=True)
    return out


# ---------------------------------------------------------------------------
# Planning prompt
# ---------------------------------------------------------------------------

_PLANNING_SYSTEM_PROMPT = """\
You are a senior software architect analyzing the Fortress codebase.
Given a feature request and relevant codebase context, produce a structured implementation plan.

You MUST respond with valid JSON matching this exact schema:
{
  "request_summary": "Brief summary of the feature request",
  "relevant_components": [
    {"text": "description", "attribution": "indexed_fact|inferred_pattern|llm_assumption", "source_path": "path/or/null"}
  ],
  "missing_components": [
    {"text": "description", "attribution": "indexed_fact|inferred_pattern|llm_assumption", "source_path": null}
  ],
  "files_to_modify": [
    {"text": "description", "attribution": "indexed_fact|inferred_pattern|llm_assumption", "source_path": "path/or/null"}
  ],
  "breaking_change_risks": [
    {"text": "description", "attribution": "indexed_fact|inferred_pattern|llm_assumption", "source_path": null}
  ],
  "development_tasks": [
    {"text": "description", "attribution": "indexed_fact|inferred_pattern|llm_assumption", "source_path": null}
  ]
}

Attribution rules:
- "indexed_fact": claim is directly supported by the provided codebase index data
- "inferred_pattern": claim is based on patterns you observe across the codebase data
- "llm_assumption": claim is not grounded in the provided data

Every claim MUST have an attribution. Use source_path when referencing a specific file.
Respond ONLY with the JSON object, no markdown fences or extra text."""


# ---------------------------------------------------------------------------
# Core planner logic
# ---------------------------------------------------------------------------

def _parse_claims(raw_list: list[dict[str, Any]]) -> list[AttributedClaim]:
    """Parse a list of raw claim dicts into AttributedClaim objects."""
    claims: list[AttributedClaim] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", ""))
        attribution = str(item.get("attribution", "llm_assumption"))
        if attribution not in VALID_ATTRIBUTIONS:
            attribution = "llm_assumption"
        source_path = item.get("source_path")
        if source_path is not None:
            source_path = str(source_path)
            if source_path.lower() in ("null", "none", ""):
                source_path = None
        claims.append(AttributedClaim(
            text=text,
            attribution=attribution,
            source_path=source_path,
        ))
    return claims


def _parse_plan_response(response_text: str, feature_request: str) -> Plan:
    """Parse the LLM JSON response into a Plan dataclass."""
    # Strip markdown fences if present
    cleaned = response_text.strip()
    if cleaned.startswith("```"):
        # Remove opening fence (```json or ```)
        first_newline = cleaned.index("\n")
        cleaned = cleaned[first_newline + 1:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].rstrip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("Failed to parse LLM plan response as JSON, using fallback")
        return Plan(
            request_summary=feature_request,
            development_tasks=[AttributedClaim(
                text=response_text[:500],
                attribution="llm_assumption",
            )],
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    return Plan(
        request_summary=str(data.get("request_summary", feature_request)),
        relevant_components=_parse_claims(data.get("relevant_components", [])),
        missing_components=_parse_claims(data.get("missing_components", [])),
        files_to_modify=_parse_claims(data.get("files_to_modify", [])),
        breaking_change_risks=_parse_claims(data.get("breaking_change_risks", [])),
        development_tasks=_parse_claims(data.get("development_tasks", [])),
        created_at=datetime.now(timezone.utc).isoformat(),
    )


async def generate_plan(feature_request: str) -> Plan:
    """Generate an implementation plan for a feature request.

    1. Ensures the codebase index is fresh (re-indexes if stale/missing)
    2. Retrieves relevant context entries via keyword matching
    3. Calls BedrockClient.converse() with context + planning prompt
    4. Parses the LLM response into a structured Plan
    """
    # Ensure index is fresh
    if is_stale():
        try:
            build_index()
            logger.info("Auto re-indexed before planning")
        except Exception:
            logger.warning("Auto re-index failed, proceeding with existing index")

    # Retrieve relevant context subset
    context_entries = retrieve_relevant_context(feature_request, max_entries=20)

    # Build context string for the LLM
    context_text = json.dumps(context_entries, indent=2, ensure_ascii=False) if context_entries else "No index data available."

    # Call Bedrock
    client = BedrockClient()
    messages = [
        {
            "role": "user",
            "content": [
                {"text": f"Codebase context (subset of index):\n{context_text}\n\nFeature request: {feature_request}"},
            ],
        }
    ]

    response = await client.converse(
        messages=messages,
        system_prompt=_PLANNING_SYSTEM_PROMPT,
        model="us.anthropic.claude-haiku-4-5-20251001-v1:0",
        max_tokens=4096,
    )

    response_text = response.text or "{}"
    plan = _parse_plan_response(response_text, feature_request)
    return plan


# ---------------------------------------------------------------------------
# Plan persistence (Task 6.2)
# ---------------------------------------------------------------------------

def _render_claims_markdown(claims: list[AttributedClaim], header: str) -> str:
    """Render a list of claims as a Markdown section."""
    if not claims:
        return ""
    lines = [f"## {header}\n"]
    for claim in claims:
        source = f" (`{claim.source_path}`)" if claim.source_path else ""
        lines.append(f"- {claim.text}{source} _[{claim.attribution}]_")
    lines.append("")
    return "\n".join(lines)


def save_plan_markdown(plan: Plan, feature_request: str) -> Path:
    """Save a Plan as a Markdown file in the plans directory.

    Returns the path to the saved file.
    """
    plans_dir = _resolve_plans_dir()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    # Sanitize feature name for filename
    safe_name = re.sub(r"[^\w\s-]", "", feature_request[:40]).strip().replace(" ", "_")
    if not safe_name:
        safe_name = "plan"
    filename = f"{timestamp}_{safe_name}.md"
    file_path = plans_dir / filename

    sections = [
        f"# Feature Plan: {plan.request_summary}\n",
        f"_Created: {plan.created_at}_\n",
        _render_claims_markdown(plan.relevant_components, "Relevant Components"),
        _render_claims_markdown(plan.missing_components, "Missing Components"),
        _render_claims_markdown(plan.files_to_modify, "Files to Modify"),
        _render_claims_markdown(plan.breaking_change_risks, "Breaking Change Risks"),
        _render_claims_markdown(plan.development_tasks, "Development Tasks"),
    ]

    content = "\n".join(s for s in sections if s)
    file_path.write_text(content, encoding="utf-8")
    logger.info("Plan saved to %s", file_path)
    return file_path


def plan_summary(plan: Plan) -> str:
    """Generate a concise WhatsApp-friendly summary of a Plan."""
    lines = [
        f"📋 *תכנית פיצ׳ר:* {plan.request_summary}",
        "",
        f"🔍 רכיבים קיימים: {len(plan.relevant_components)}",
        f"🆕 רכיבים חסרים: {len(plan.missing_components)}",
        f"📝 קבצים לשינוי: {len(plan.files_to_modify)}",
        f"⚠️ סיכוני שבירה: {len(plan.breaking_change_risks)}",
        f"📌 משימות פיתוח: {len(plan.development_tasks)}",
    ]
    return "\n".join(lines)
