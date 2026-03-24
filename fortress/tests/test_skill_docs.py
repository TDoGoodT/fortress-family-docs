"""Tests for SKILL.md documentation files — S2 feature."""

import os
import glob


_SKILLS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "src", "skills")

# Expected SKILL_*.md files (one per registered skill)
_EXPECTED_SKILLS = [
    "SKILL_task.md",
    "SKILL_recurring.md",
    "SKILL_document.md",
    "SKILL_bug.md",
    "SKILL_chat.md",
    "SKILL_memory.md",
    "SKILL_morning.md",
    "SKILL_system.md",
]


def test_all_skill_docs_exist() -> None:
    """Every registered skill has a corresponding SKILL_*.md file."""
    for filename in _EXPECTED_SKILLS:
        path = os.path.join(_SKILLS_DIR, filename)
        assert os.path.isfile(path), f"Missing skill doc: {filename}"


def test_skill_docs_have_yaml_frontmatter() -> None:
    """Each SKILL_*.md starts with YAML frontmatter (--- delimiters)."""
    for filename in _EXPECTED_SKILLS:
        path = os.path.join(_SKILLS_DIR, filename)
        with open(path, encoding="utf-8") as f:
            content = f.read()
        assert content.startswith("---"), f"{filename} missing YAML frontmatter"
        # Must have closing ---
        parts = content.split("---")
        assert len(parts) >= 3, f"{filename} missing closing --- in frontmatter"


def test_skill_docs_contain_commands_section() -> None:
    """Each SKILL_*.md contains a commands/פקודות section."""
    for filename in _EXPECTED_SKILLS:
        path = os.path.join(_SKILLS_DIR, filename)
        with open(path, encoding="utf-8") as f:
            content = f.read()
        assert "פקודות" in content or "commands" in content.lower(), (
            f"{filename} missing commands section"
        )


def test_skill_docs_contain_description() -> None:
    """Each SKILL_*.md contains a description/תיאור section."""
    for filename in _EXPECTED_SKILLS:
        path = os.path.join(_SKILLS_DIR, filename)
        with open(path, encoding="utf-8") as f:
            content = f.read()
        assert "תיאור" in content or "description" in content.lower(), (
            f"{filename} missing description section"
        )


def test_skill_docs_have_name_in_frontmatter() -> None:
    """Each SKILL_*.md frontmatter contains a 'name' field."""
    for filename in _EXPECTED_SKILLS:
        path = os.path.join(_SKILLS_DIR, filename)
        with open(path, encoding="utf-8") as f:
            content = f.read()
        # Extract frontmatter
        parts = content.split("---")
        frontmatter = parts[1] if len(parts) >= 3 else ""
        assert "name:" in frontmatter, f"{filename} missing 'name' in frontmatter"


def test_no_orphan_skill_docs() -> None:
    """No SKILL_*.md files exist for non-existent skills."""
    actual_files = glob.glob(os.path.join(_SKILLS_DIR, "SKILL_*.md"))
    actual_names = {os.path.basename(f) for f in actual_files}
    expected_names = set(_EXPECTED_SKILLS)
    orphans = actual_names - expected_names
    assert not orphans, f"Orphan skill docs found: {orphans}"
