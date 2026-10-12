"""Where a hub's skills live, and reading them once QA has passed."""

from pathlib import Path

from skill_hub.frontmatter import split_frontmatter
from skill_hub.yamlutil import load_yaml

SKILLS_DIR = "skills"
SKILL_FILE = "SKILL.md"


def skill_dirs(root: Path) -> list[Path]:
    """The skills QA checks: real directories directly under skills/, without dot-entries or symlinks, sorted."""
    entries = (root / SKILLS_DIR).iterdir()
    return sorted(
        entry for entry in entries if not entry.name.startswith(".") and not entry.is_symlink() and entry.is_dir()
    )


def read_frontmatter(skill_dir: Path) -> dict:
    """A skill's frontmatter mapping. Only call it for a hub that passed QA."""
    text = (skill_dir / SKILL_FILE).read_bytes().decode("utf-8")
    return load_yaml(split_frontmatter(text).frontmatter).data
