# tests/conftest.py
from pathlib import Path

GOOD_HUB = """\
hub:
  name: acme-skills
  display_name: Acme Skills
  owner: Acme Platform Team
  description: Skills for Acme engineers.
  repo_url: https://github.com/acme/skills
qa:
  allow_keys: []
"""

DEFAULT_BODY = """
# Changelog formatter

1. Read the merged changes since the last release.
2. Group them under Added, Changed and Fixed.
3. Write one line per change, in the imperative mood.
"""


def write_hub(root: Path, text: str = GOOD_HUB) -> Path:
    path = root / "hub.yml"
    path.write_text(text, encoding="utf-8")
    return path


def skill_md(
    name: str = "changelog-formatter",
    extra_frontmatter: str = "",
    body: str = DEFAULT_BODY,
    version: str = '"1.0.0"',
) -> str:
    return (
        "---\n"
        f"name: {name}\n"
        'description: "Formats changelog entries. Use when the user asks to write or tidy a changelog."\n'
        "metadata:\n"
        f"  version: {version}\n"
        f"{extra_frontmatter}"
        "---\n"
        f"{body}"
    )


def make_skill(root: Path, dirname: str = "changelog-formatter", text: str | None = None) -> Path:
    skill_dir = root / "src" / dirname
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(skill_md(dirname) if text is None else text, encoding="utf-8")
    return skill_dir


def ids(findings) -> list[str]:
    return sorted(finding.check_id for finding in findings)
