# tests/conftest.py
from pathlib import Path

from skill_hub.config import check_hub
from skill_hub.manifests import render_manifests, write_manifests
from skill_hub.skills import SKILLS_DIR

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
    skill_dir = root / SKILLS_DIR / dirname
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(skill_md(dirname) if text is None else text, encoding="utf-8")
    return skill_dir


def ids(findings) -> list[str]:
    return sorted(finding.check_id for finding in findings)


def make_theme(root: Path, name: str = "theme", index: str = "<p>{{ catalog.hub.display_name }}</p>\n") -> Path:
    theme = root / name
    theme.mkdir(parents=True, exist_ok=True)
    (theme / "index.html.j2").write_text(index, encoding="utf-8")
    return theme


def sync_manifests(root: Path) -> None:
    """Write the hub's marketplace manifests, as `skill-hub manifests` does, so QA check R7 passes."""
    write_manifests(root, render_manifests(root, check_hub(root)[1]))


S3_DEPLOY = """\
deploy:
  target: s3
  s3:
    bucket: acme-skills
    endpoint: ""
    region: us-east-1
"""

RSYNC_DEPLOY = """\
deploy:
  target: rsync
  rsync:
    host: web1.example.com
    user: deploy
    path: /var/www/skills
"""


def make_deploy_workflow(root: Path, target: str) -> Path:
    """A stand-in .github/workflows/deploy-<target>.yml, so QA check H16 finds the target's workflow."""
    folder = root / ".github" / "workflows"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"deploy-{target}.yml"
    path.write_text("on: workflow_call\n", encoding="utf-8")
    return path
