"""Create a skill under src/ from the built-in template: `skill-hub new-skill`."""

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from skill_hub.config import HUB_FILE
from skill_hub.contract import NAME_RULE, SCAFFOLD_DESCRIPTION, is_valid_name
from skill_hub.qa import SKILL_FILE, SRC_DIR
from skill_hub.releases import RELEASE_CONFIG

TEMPLATE = """\
---
name: "{name}"
description: "{description}"
metadata:
  version: "0.1.0" # x-release-please-version
---

# {title}

Replace this paragraph with what the skill is for and the outcome it produces.

## Steps

1. Replace these steps with the instructions an agent should follow, one action per step.

## Example

Replace this with a short example of the skill's input and output.
"""


class ScaffoldError(Exception):
    """A refusal; str() is the fixed message shown to the user."""


@dataclass(frozen=True)
class Created:
    path: str  # the new SKILL.md, relative to the hub root
    registered: bool  # False when the hub has no release config (opted out of releases)


def _read_release_config(path: Path) -> tuple[dict, bytes] | None:
    """The parsed release config and its original bytes, or None when the hub has none."""
    try:
        if not path.exists() and not path.is_symlink():
            return None
        original = path.read_bytes()
    except OSError:
        raise ScaffoldError(f"could not read {RELEASE_CONFIG}") from None
    try:
        config = json.loads(original.decode("utf-8"))
    except ValueError:
        config = None
    if not isinstance(config, dict) or not isinstance(config.get("packages"), dict):
        raise ScaffoldError(f"{RELEASE_CONFIG} is not a valid release config; fix it or run skill-hub qa")
    return config, original


def render_skill(name: str) -> str:
    title = " ".join(word.capitalize() for word in name.split("-"))
    return TEMPLATE.format(name=name, description=SCAFFOLD_DESCRIPTION, title=title)


def create_skill(root: Path, name: str) -> Created:
    """Write src/<name>/SKILL.md under root, register it for release, and report what was done."""
    if not is_valid_name(name):
        raise ScaffoldError(NAME_RULE)
    rel = f"{SRC_DIR}/{name}/{SKILL_FILE}"
    already = f"{SRC_DIR}/{name} already exists; choose another name or remove it"
    src = root / SRC_DIR
    skill_dir = src / name
    try:
        if not root.is_dir():
            raise ScaffoldError("--root is not a directory")
        if not (root / HUB_FILE).is_file():
            raise ScaffoldError(f"{HUB_FILE} not found; run this from your hub's root or pass --root")
        if (src.exists() or src.is_symlink()) and not src.is_dir():
            raise ScaffoldError(f"{SRC_DIR} is not a directory")
        release = _read_release_config(root / RELEASE_CONFIG)
        src.mkdir(exist_ok=True)
        skill_dir.mkdir()  # refuses any existing entry: folder, file or broken symlink
    except FileExistsError:
        raise ScaffoldError(already) from None
    except OSError:
        raise ScaffoldError(f"could not write {rel}") from None
    try:
        (skill_dir / SKILL_FILE).write_text(render_skill(name), encoding="utf-8", newline="\n")
    except OSError:
        shutil.rmtree(skill_dir, ignore_errors=True)
        raise ScaffoldError(f"could not write {rel}") from None
    if release is None:
        return Created(rel, registered=False)
    config, original = release
    config["packages"][f"{SRC_DIR}/{name}"] = {"component": name, "extra-files": [SKILL_FILE]}
    config_path = root / RELEASE_CONFIG
    try:
        config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    except OSError:
        try:
            config_path.write_bytes(original)
        except OSError:
            pass  # nothing more to try; the error below still reports the failure
        shutil.rmtree(skill_dir, ignore_errors=True)
        raise ScaffoldError(f"could not write {RELEASE_CONFIG}") from None
    return Created(rel, registered=True)
