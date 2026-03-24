"""Tests for SOUL.md personality loading — S2 feature."""

import os
import tempfile
from unittest.mock import patch

from src.prompts.personality import _DEFAULT_PERSONALITY, _load_soul


def test_load_soul_returns_default_when_file_missing() -> None:
    """When SOUL.md doesn't exist, _load_soul returns the hardcoded default."""
    with patch("src.config.SOUL_MD_PATH", "/nonexistent/SOUL.md"):
        result = _load_soul()
    assert result == _DEFAULT_PERSONALITY


def test_load_soul_reads_file_when_present() -> None:
    """When SOUL.md exists, _load_soul returns its content."""
    custom = "# Custom Soul\nאני בוט מותאם אישית"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(custom)
        f.flush()
        path = f.name
    try:
        with patch("src.config.SOUL_MD_PATH", path):
            result = _load_soul()
        assert result == custom
    finally:
        os.unlink(path)


def test_load_soul_falls_back_on_empty_file() -> None:
    """When SOUL.md exists but is empty, _load_soul returns the default."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write("")
        f.flush()
        path = f.name
    try:
        with patch("src.config.SOUL_MD_PATH", path):
            result = _load_soul()
        assert result == _DEFAULT_PERSONALITY
    finally:
        os.unlink(path)


def test_default_personality_contains_hebrew() -> None:
    """The default personality string contains Hebrew content."""
    assert "אני פורטרס" in _DEFAULT_PERSONALITY
    assert "# מי אני" in _DEFAULT_PERSONALITY


def test_personality_module_exports_personality_string() -> None:
    """The PERSONALITY module-level variable is a non-empty string."""
    from src.prompts.personality import PERSONALITY
    assert isinstance(PERSONALITY, str)
    assert len(PERSONALITY) > 0


def test_soul_md_file_exists() -> None:
    """The config/SOUL.md file exists in the project."""
    # Check relative to the fortress directory
    soul_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "SOUL.md")
    assert os.path.isfile(soul_path), f"SOUL.md not found at {soul_path}"


def test_soul_md_content_matches_default() -> None:
    """The SOUL.md file content matches the default personality structure."""
    soul_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "SOUL.md")
    with open(soul_path, encoding="utf-8") as f:
        content = f.read()
    assert "# מי אני" in content
    assert "פורטרס" in content
    assert "# איך אני מדבר" in content
