"""Coding Agent Bridge — translates Plans into Task_Prompts.

Phase C1: prompt generation only.
Phase C2 (deferred): Codex CLI execution.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.config import CODEX_PROMPT_MAX_CHARS  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class PromptResult:
    """Result of prompt generation."""
    success: bool
    prompt_path: Path | None       # path to saved Task_Prompt file
    message: str                   # human-readable summary for WhatsApp
    files_embedded: int            # count of source files embedded in prompt
    files_missing: int             # count of referenced files not found on disk


@dataclass
class ExecutionResult:
    """Result of Codex CLI execution (Phase C2 stub)."""
    success: bool
    exit_code: int | None
    log_path: Path | None          # path to saved execution log
    message: str                   # human-readable summary for WhatsApp
    stdout_excerpt: str            # first N chars of stdout
    stderr_excerpt: str            # first N chars of stderr


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

_PROMPTS_DIR = Path("fortress/data/prompts")


def _resolve_prompts_dir() -> Path:
    """Return the prompts directory, creating it if needed."""
    cwd = Path.cwd()
    if (cwd / "data").is_dir():
        out = cwd / "data" / "prompts"
    elif (cwd / "fortress" / "data").is_dir():
        out = cwd / "fortress" / "data" / "prompts"
    else:
        out = _PROMPTS_DIR
    out.mkdir(parents=True, exist_ok=True)
    return out


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _sanitize_feature_name(plan_filename: str) -> str:
    """Strip timestamp prefix (YYYYMMDD_HHMMSS_) and .md suffix from plan filename."""
    name = plan_filename
    # Strip .md suffix
    if name.endswith(".md"):
        name = name[:-3]
    # Strip timestamp prefix: 8 digits + _ + 6 digits + _
    name = re.sub(r"^\d{8}_\d{6}_", "", name)
    # Replace non-word chars with underscores and strip
    name = re.sub(r"[^\w]", "_", name).strip("_")
    return name or "feature"


def _read_source_file(file_path: str, max_lines: int = 500) -> tuple[str, bool]:
    """Read a source file, returning (content, was_truncated).

    Returns ("[CONTEXT UNAVAILABLE]", False) on any read error.
    Truncates to max_lines if the file exceeds that length.
    """
    try:
        path = Path(file_path)
        content = path.read_text(encoding="utf-8")
    except (OSError, FileNotFoundError):
        return ("[CONTEXT UNAVAILABLE]", False)

    lines = content.splitlines()
    if len(lines) > max_lines:
        truncated_content = "\n".join(lines[:max_lines])
        return (truncated_content, True)
    return (content, False)


def _load_project_structure() -> str:
    """Load the modules layer from codebase_index.json.

    Returns "[CONTEXT UNAVAILABLE]" if the index is missing or unreadable.
    """
    cwd = Path.cwd()
    # Try both container and repo-root layouts
    candidates = [
        cwd / "data" / "codebase_index.json",
        cwd / "fortress" / "data" / "codebase_index.json",
    ]
    index_path: Path | None = None
    for candidate in candidates:
        if candidate.is_file():
            index_path = candidate
            break

    if index_path is None:
        return "[CONTEXT UNAVAILABLE]"

    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "[CONTEXT UNAVAILABLE]"

    modules = data.get("layers", {}).get("modules", [])
    if not modules:
        return "[CONTEXT UNAVAILABLE]"

    lines: list[str] = []
    for mod in modules:
        file_path = mod.get("file_path", "")
        classes = [c.get("name", "") for c in mod.get("classes", [])]
        functions = mod.get("functions", [])
        parts = []
        if classes:
            parts.append(f"classes: {', '.join(classes)}")
        if functions:
            parts.append(f"functions: {', '.join(functions)}")
        suffix = f" — {'; '.join(parts)}" if parts else ""
        lines.append(f"- {file_path}{suffix}")

    return "\n".join(lines)


def _assemble_prompt(
    plan: "Plan",  # type: ignore[name-defined]  # noqa: F821
    plan_filename: str,
    file_contents: dict[str, str | None],
    project_structure: str,
    max_chars: int,
) -> str:
    """Build the full Task_Prompt Markdown string from a structured Plan."""
    from src.services.feature_planner import Plan  # local import to avoid circular

    feature_name = _sanitize_feature_name(plan_filename)
    timestamp = datetime.now(timezone.utc).isoformat()

    # --- Header ---
    header = (
        f"# Task Prompt: {feature_name}\n\n"
        f"_Generated: {timestamp}_\n"
        f"_Source Plan: {plan_filename}_\n"
    )

    # --- Feature Request ---
    feature_request_section = (
        f"\n## Feature Request\n\n{plan.request_summary}\n"
    )

    # --- Project Structure ---
    project_structure_section = (
        f"\n## Project Structure\n\n{project_structure}\n"
    )

    # --- Files to Modify ---
    files_to_modify_lines: list[str] = ["\n## Files to Modify\n"]
    for claim in plan.files_to_modify:
        sp = claim.source_path
        if sp is None:
            continue
        content = file_contents.get(sp)
        if content is None:
            content = "[CONTEXT UNAVAILABLE]"
        # Detect language from extension
        ext = Path(sp).suffix.lstrip(".")
        lang = ext if ext else "text"
        files_to_modify_lines.append(f"\n### {sp}\n")
        files_to_modify_lines.append(f"**Planned changes:** {claim.text}\n")
        files_to_modify_lines.append(f"```{lang}\n{content}\n```\n")
    files_to_modify_section = "\n".join(files_to_modify_lines)

    # --- New Files to Create ---
    new_files_lines: list[str] = ["\n## New Files to Create\n"]
    for claim in plan.missing_components:
        if claim.source_path is None:
            new_files_lines.append(f"- {claim.text} _[{claim.attribution}]_")
    new_files_section = "\n".join(new_files_lines)

    # --- Development Tasks ---
    dev_tasks_lines: list[str] = ["\n## Development Tasks\n"]
    for i, task in enumerate(plan.development_tasks, 1):
        dev_tasks_lines.append(f"{i}. {task.text} _[{task.attribution}]_")
    dev_tasks_section = "\n".join(dev_tasks_lines)

    # --- Constraints and Risks ---
    risks_lines: list[str] = ["\n## Constraints and Risks\n"]
    for risk in plan.breaking_change_risks:
        risks_lines.append(f"- {risk.text} _[{risk.attribution}]_")
    risks_section = "\n".join(risks_lines)

    # --- Test Requirements ---
    test_requirements_section = (
        "\n## Test Requirements\n\n"
        "- Write tests for all new public functions\n"
        "- Ensure existing tests still pass\n"
        "- Follow the project's pytest + Hypothesis testing patterns\n"
    )

    # --- Instructions ---
    instructions_section = (
        f"\n## Instructions\n\n"
        f"- Create a new git branch named `feature/{feature_name}`\n"
        f"- Make all changes described above\n"
        f"- Attempt to create a **draft** pull request if the environment supports it — never merge, never deploy\n"
        f"- Do not modify files outside the scope of this plan\n"
        f"- Do not commit secrets, API keys, or credentials\n\n"
        f"> Note: PR creation is best-effort and depends on your git configuration and GitHub access.\n"
        f"> If draft PR creation is not available, create a regular PR and mark it as draft manually.\n"
    )

    # Assemble full prompt
    full_prompt = (
        header
        + feature_request_section
        + project_structure_section
        + files_to_modify_section
        + new_files_section
        + dev_tasks_section
        + risks_section
        + test_requirements_section
        + instructions_section
    )

    # Progressive truncation if over max_chars
    if len(full_prompt) > max_chars and file_contents:
        # Reduce each file's content progressively
        truncation_factor = 0.5
        while len(full_prompt) > max_chars and truncation_factor > 0.05:
            truncated_contents: dict[str, str | None] = {}
            for path_key, content in file_contents.items():
                if content and content != "[CONTEXT UNAVAILABLE]":
                    lines = content.splitlines()
                    keep = max(1, int(len(lines) * truncation_factor))
                    truncated_contents[path_key] = "\n".join(lines[:keep]) + "\n... [truncated]"
                else:
                    truncated_contents[path_key] = content
            # Rebuild files_to_modify_section with truncated contents
            files_to_modify_lines = ["\n## Files to Modify\n"]
            for claim in plan.files_to_modify:
                sp = claim.source_path
                if sp is None:
                    continue
                content = truncated_contents.get(sp)
                if content is None:
                    content = "[CONTEXT UNAVAILABLE]"
                ext = Path(sp).suffix.lstrip(".")
                lang = ext if ext else "text"
                files_to_modify_lines.append(f"\n### {sp}\n")
                files_to_modify_lines.append(f"**Planned changes:** {claim.text}\n")
                files_to_modify_lines.append(f"```{lang}\n{content}\n```\n")
            files_to_modify_section = "\n".join(files_to_modify_lines)
            full_prompt = (
                header
                + feature_request_section
                + project_structure_section
                + files_to_modify_section
                + new_files_section
                + dev_tasks_section
                + risks_section
                + test_requirements_section
                + instructions_section
            )
            truncation_factor *= 0.5

    return full_prompt


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_prompt(plan: "Plan", plan_filename: str) -> PromptResult:  # type: ignore[name-defined]  # noqa: F821
    """Generate a Task_Prompt Markdown file from a Plan object.

    Reads source files referenced in the plan, assembles the prompt,
    and writes it to the prompts directory.
    """
    from src.services.feature_planner import Plan  # noqa: F401 (used for type)

    # Collect unique source paths from files_to_modify and relevant_components
    source_paths: list[str] = []
    seen: set[str] = set()
    for claim in list(plan.files_to_modify) + list(plan.relevant_components):
        sp = claim.source_path
        if sp is not None and sp not in seen:
            seen.add(sp)
            source_paths.append(sp)

    # Read each source file
    file_contents: dict[str, str | None] = {}
    files_embedded = 0
    files_missing = 0
    for sp in source_paths:
        content, _truncated = _read_source_file(sp)
        if content == "[CONTEXT UNAVAILABLE]":
            files_missing += 1
            file_contents[sp] = None
        else:
            files_embedded += 1
            file_contents[sp] = content

    # Load project structure
    project_structure = _load_project_structure()

    # Assemble prompt
    prompt_text = _assemble_prompt(
        plan=plan,
        plan_filename=plan_filename,
        file_contents=file_contents,
        project_structure=project_structure,
        max_chars=CODEX_PROMPT_MAX_CHARS,
    )

    # Write to prompts directory
    feature_name = _sanitize_feature_name(plan_filename)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    prompt_filename = f"{timestamp}_{feature_name}.md"

    try:
        prompts_dir = _resolve_prompts_dir()
        prompt_path = prompts_dir / prompt_filename
        prompt_path.write_text(prompt_text, encoding="utf-8")
    except OSError as exc:
        logger.error("Failed to write prompt file: %s", exc)
        return PromptResult(
            success=False,
            prompt_path=None,
            message=f"שגיאה בשמירת קובץ: {exc}",
            files_embedded=files_embedded,
            files_missing=files_missing,
        )

    message = (
        f"✅ פרומפט נוצר: {prompt_filename}\n"
        f"📁 קבצים מוטמעים: {files_embedded} | חסרים: {files_missing}\n"
        f"📄 הפרומפט נשמר ב: {prompt_path}\n"
        f"▶️ להפעלה: העבר את הפרומפט ל-Codex CLI ידנית, או בקש 'הפעל codex' (כשיופעל)."
    )

    return PromptResult(
        success=True,
        prompt_path=prompt_path,
        message=message,
        files_embedded=files_embedded,
        files_missing=files_missing,
    )
