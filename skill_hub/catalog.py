"""The catalog: hub.yml and every skill's frontmatter as one versioned dict."""

from pathlib import Path

from skill_hub.config import REQUIRED_HUB_KEYS, HubConfig, check_hub
from skill_hub.qa import run_qa
from skill_hub.releases import check_release
from skill_hub.skills import SKILLS_DIR, read_frontmatter, skill_dirs

SCHEMA_VERSION = 1
CHANGELOG_FILE = "CHANGELOG.md"


class BuildError(Exception):
    """A refusal; str() is the fixed message shown to the user."""


def require_clean_qa(root: Path) -> HubConfig:
    """The hub's config, or BuildError when QA reports any error. Warnings do not block."""
    errors = len(run_qa(root).errors)
    if errors:
        raise BuildError(f"QA found {errors} error{'' if errors == 1 else 's'}; run `skill-hub qa` and fix them first")
    return check_hub(root)[1]


def build_catalog(root: Path, config: HubConfig) -> dict:
    """The catalog of a hub that passed QA (see require_clean_qa)."""
    repo = config.repo_url.rstrip("/")
    dirs = skill_dirs(root)
    _, released, _ = check_release(root, [skill_dir.name for skill_dir in dirs])
    skills = []
    for skill_dir in dirs:
        frontmatter = read_frontmatter(skill_dir)
        name = frontmatter["name"]
        changelog = skill_dir / CHANGELOG_FILE
        has_changelog = changelog.is_file() and not changelog.is_symlink()
        skills.append({
            "name": name,
            "description": frontmatter["description"],
            "version": frontmatter["metadata"]["version"],
            "license": frontmatter.get("license"),
            "compatibility": frontmatter.get("compatibility"),
            "links": {
                "source": f"{repo}/tree/HEAD/{SKILLS_DIR}/{name}",
                "changelog": f"{repo}/blob/HEAD/{SKILLS_DIR}/{name}/{CHANGELOG_FILE}" if has_changelog else None,
                "release": f"{repo}/releases/tag/{name}-v{released[name]}" if name in released else None,
            },
        })
    skills.sort(key=lambda skill: skill["name"])
    return {
        "schema_version": SCHEMA_VERSION,
        "hub": {key: getattr(config, key) for key in REQUIRED_HUB_KEYS},
        "skills": skills,
    }
