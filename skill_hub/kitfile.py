"""`.skill-hub/kit.yml`: which kit release a hub was last brought up to."""

from dataclasses import dataclass
from pathlib import Path

from skill_hub.contract import KIT_FILE, is_valid_commit, is_valid_kit_repo, parse_version, type_name
from skill_hub.yamlutil import load_yaml

_HEADER = (
    "# Records which skill-hub kit release this hub was last updated to.\n"
    "# `skill-hub update` rewrites it; edit it by hand only to point at a different kit.\n"
)


class KitFileError(Exception):
    """Fixed message only: never echoes a value from the file."""


@dataclass(frozen=True)
class KitFile:
    repo: str
    version: str
    commit: str = ""
    workflows_version: str = ""
    workflows_commit: str = ""

    @property
    def pending(self) -> bool:
        """True when a kit update held back the workflow files."""
        return self.workflows_version != ""


def _text(data: dict, key: str, valid, message: str, required: bool) -> str:
    if key not in data or (data[key] == "" and not required):
        if required:
            raise KitFileError(f"kit.yml {key} is missing")
        return ""
    value = data[key]
    if not isinstance(value, str) or not valid(value):
        raise KitFileError(f"kit.yml {key} {message}")
    return value


def read_kit_file(root: Path) -> KitFile:
    try:
        text = (root / KIT_FILE).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        raise KitFileError("kit.yml could not be read") from None
    loaded = load_yaml(text)
    if loaded.error is not None:
        raise KitFileError("kit.yml is not valid YAML")
    data = loaded.data
    if not isinstance(data, dict):
        raise KitFileError(f"kit.yml must be a mapping, found {type_name(data)}")
    def is_version(value: str) -> bool:
        return parse_version(value) is not None

    repo = _text(data, "repo", is_valid_kit_repo, "must be an https:// or file:// URL", True)
    version = _text(data, "version", is_version, "must be a quoted X.Y.Z version", True)
    commit = _text(data, "commit", is_valid_commit, "must be empty or 40 lowercase hex characters", False)
    workflows_version = _text(
        data, "workflows_version", is_version, "must be empty or a quoted X.Y.Z version", False
    )
    workflows_commit = _text(
        data, "workflows_commit", is_valid_commit, "must be empty or 40 lowercase hex characters", False
    )
    if bool(workflows_version) != bool(workflows_commit):
        raise KitFileError("kit.yml workflows_version and workflows_commit must be set together")
    return KitFile(repo, version, commit, workflows_version, workflows_commit)


def render_kit_file(kit: KitFile) -> str:
    # Every value is quoted (L73); Release Please bumps the version through the marker comment.
    return (
        f"{_HEADER}"
        f'repo: "{kit.repo}"\n'
        f'version: "{kit.version}" # x-release-please-version\n'
        f'commit: "{kit.commit}"\n'
        f'workflows_version: "{kit.workflows_version}"\n'
        f'workflows_commit: "{kit.workflows_commit}"\n'
    )


def write_kit_file(root: Path, kit: KitFile) -> None:
    path = root / KIT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_kit_file(kit), encoding="utf-8")
