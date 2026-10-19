"""Marketplace manifests: the client files that list each skill as an installable plugin (QA check R7)."""

import codecs
import json
import os
from pathlib import Path

from skill_hub.config import HubConfig, check_hub
from skill_hub.findings import ERROR, Finding
from skill_hub.skills import SKILLS_DIR, read_frontmatter, skill_dirs

MANIFEST_PATHS = (".claude-plugin/marketplace.json", ".cursor-plugin/marketplace.json")
_RERUN = "run `skill-hub manifests`"


class ManifestError(Exception):
    """A refusal; str() is the fixed message shown to the user."""


def render_manifests(root: Path, config: HubConfig) -> dict[str, str]:
    """Each manifest's path, relative to root, mapped to its exact text. Only call it for a hub that passed QA."""
    plugins = []
    for skill_dir in skill_dirs(root):
        frontmatter = read_frontmatter(skill_dir)
        name = frontmatter["name"]
        plugins.append({"name": name, "source": f"./{SKILLS_DIR}/{name}", "description": frontmatter["description"]})
    plugins.sort(key=lambda plugin: plugin["name"])
    manifest = {
        "name": config.name,
        "owner": {"name": config.owner},
        "description": config.description,
        "plugins": plugins,
    }
    text = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    return dict.fromkeys(MANIFEST_PATHS, text)


def write_manifests(root: Path, rendered: dict[str, str]) -> None:
    """Write each manifest through a temp file and a rename, so a failure never leaves a half-written file."""
    for rel, text in rendered.items():
        path = root / rel
        temp = path.with_name(f".{path.name}.tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp.write_text(text, encoding="utf-8", newline="\n")
            os.replace(temp, path)
        except (OSError, UnicodeEncodeError):
            temp.unlink(missing_ok=True)
            raise ManifestError(f"could not write {rel}") from None


def update_manifests(root: Path) -> int:
    """Regenerate both marketplace manifests and return the skill count. Raises ManifestError."""
    from skill_hub.qa import run_qa  # imported here: qa imports this module for check_manifests

    result = run_qa(root)
    blocking = len([f for f in result.errors if f.check_id != "R7"])
    if blocking:
        errors = "error" if blocking == 1 else "errors"
        raise ManifestError(f"QA found {blocking} {errors}; run `skill-hub qa` and fix them first")
    write_manifests(root, render_manifests(root, check_hub(root)[1]))
    return result.skill_count


def check_manifests(root: Path, config: HubConfig) -> list[Finding]:
    """R7: each committed manifest equals a fresh render. Run it only when QA found no other error."""
    findings = []
    for rel, expected in render_manifests(root, config).items():
        try:
            raw = (root / rel).read_bytes()
        except FileNotFoundError:
            findings.append(Finding(ERROR, "R7", rel, f"not found; {_RERUN}"))
            continue
        except OSError:
            findings.append(Finding(ERROR, "R7", rel, f"could not be read; {_RERUN}"))
            continue
        try:
            actual = raw.removeprefix(codecs.BOM_UTF8).decode("utf-8").replace("\r\n", "\n")
        except UnicodeDecodeError:
            findings.append(Finding(ERROR, "R7", rel, f"could not be read; {_RERUN}"))
            continue
        if actual != expected:
            findings.append(Finding(ERROR, "R7", rel, f"out of date; {_RERUN}"))
    return findings
