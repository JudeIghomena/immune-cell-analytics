"""Validate the YAML frontmatter of every crew agent definition.

The agent files under .claude/agents are configuration, not Python, so the
normal gates do not cover them. A single unquoted colon in a description once
broke an agent at load time. This test parses every agent's frontmatter so that
class of error cannot reach main again.
"""

from pathlib import Path

import pytest
import yaml

AGENTS_DIR = Path(__file__).resolve().parents[1] / ".claude" / "agents"
AGENT_FILES = sorted(AGENTS_DIR.rglob("*.md"))


def test_agents_directory_has_files() -> None:
    assert AGENT_FILES, f"no agent files found under {AGENTS_DIR}"


@pytest.mark.parametrize("path", AGENT_FILES, ids=lambda p: p.name)
def test_frontmatter_parses_and_has_required_keys(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path.name} is missing opening frontmatter fence"

    parts = text.split("---\n", 2)
    assert len(parts) == 3, f"{path.name} is missing closing frontmatter fence"

    meta = yaml.safe_load(parts[1])
    assert isinstance(meta, dict), f"{path.name} frontmatter is not a mapping"

    for key in ("name", "description"):
        assert key in meta, f"{path.name} frontmatter is missing '{key}'"
        assert str(meta[key]).strip(), f"{path.name} has an empty '{key}'"
