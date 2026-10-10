"""The catalog: hub.yml and every skill's frontmatter as one versioned dict."""

from pathlib import Path

from skill_hub.config import REQUIRED_HUB_KEYS, HubConfig, check_hub
from skill_hub.frontmatter import split_frontmatter
from skill_hub.qa import SKILL_FILE, SRC_DIR, run_qa
from skill_hub.releases import check_release
from skill_hub.yamlutil import load_yaml

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


def _skill_dirs(root: Path) -> list[Path]:
    # The skills run_qa checks: real directories directly under src/, without dot-entries or symlinks.
    return [
        entry
        for entry in (root / SRC_DIR).iterdir()
        if not entry.name.startswith(".") and not entry.is_symlink() and entry.is_dir()
    ]


def _frontmatter(skill_dir: Path) -> dict:
    text = (skill_dir / SKILL_FILE).read_bytes().decode("utf-8")
    return load_yaml(split_frontmatter(text).frontmatter).data  # QA passed, so this is a mapping


def build_catalog(root: Path, config: HubConfig) -> dict:
    """The catalog of a hub that passed QA (see require_clean_qa)."""
    repo = config.repo_url.rstrip("/")
    skill_dirs = _skill_dirs(root)
    _, released, _ = check_release(root, [skill_dir.name for skill_dir in skill_dirs])
    skills = []
    for skill_dir in skill_dirs:
        frontmatter = _frontmatter(skill_dir)
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
                "source": f"{repo}/tree/HEAD/{SRC_DIR}/{name}",
                "changelog": f"{repo}/blob/HEAD/{SRC_DIR}/{name}/{CHANGELOG_FILE}" if has_changelog else None,
                "release": f"{repo}/releases/tag/{name}-v{released[name]}" if name in released else None,
            },
        })
    skills.sort(key=lambda skill: skill["name"])
    return {
        "schema_version": SCHEMA_VERSION,
        "hub": {key: getattr(config, key) for key in REQUIRED_HUB_KEYS},
        "skills": skills,
    }
