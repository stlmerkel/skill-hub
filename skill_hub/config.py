"""Load and check hub.yml (checks H1-H6)."""

from dataclasses import dataclass
from pathlib import Path

from skill_hub.contract import DEFAULT_HUB_NAME, DEFAULT_REPO_URL, is_blank, is_valid_name, type_name
from skill_hub.findings import ERROR, WARNING, Finding
from skill_hub.yamlutil import load_yaml

HUB_FILE = "hub.yml"
REQUIRED_HUB_KEYS = ("name", "display_name", "owner", "description", "repo_url")


@dataclass(frozen=True)
class HubConfig:
    name: str
    display_name: str
    owner: str
    description: str
    repo_url: str
    allow_keys: tuple[str, ...]


def _error(check_id: str, message: str, line: int | None = None) -> Finding:
    return Finding(ERROR, check_id, HUB_FILE, message, line)


def check_hub(root: Path) -> tuple[list[Finding], HubConfig | None]:
    path = root / HUB_FILE
    if not path.exists():
        return [_error("H1", "hub.yml not found at the repository root")], None
    if not path.is_file():
        return [_error("H1", "hub.yml is not a regular file")], None

    try:
        text = path.read_bytes().decode("utf-8").removeprefix("﻿")
    except OSError:
        return [_error("H2", "hub.yml could not be read")], None
    except UnicodeDecodeError:
        return [_error("H2", "hub.yml is not valid UTF-8")], None

    loaded = load_yaml(text)
    if loaded.error is not None:
        return [_error("H2", f"hub.yml {loaded.error.message}", loaded.error.line)], None
    data = loaded.data
    if not isinstance(data, dict):
        return [_error("H2", "hub.yml must be a mapping")], None

    findings: list[Finding] = []
    hub = data.get("hub")
    if not isinstance(hub, dict):
        what = "is missing" if "hub" not in data else f"must be a mapping, found {type_name(hub)}"
        findings.append(_error("H3", f"hub {what}"))
    else:
        for key in REQUIRED_HUB_KEYS:
            value = hub.get(key)
            if key not in hub:
                findings.append(_error("H3", f"hub.{key} is missing"))
            elif not isinstance(value, str):
                findings.append(_error("H3", f"hub.{key} must be a string, found {type_name(value)}; quote it"))
            elif is_blank(value):
                findings.append(_error("H3", f"hub.{key} is empty"))
        name = hub.get("name")
        if isinstance(name, str) and not is_blank(name) and not is_valid_name(name):
            findings.append(_error("H4", "hub.name must be 1-64 characters of a-z, 0-9 and single hyphens, with no leading or trailing hyphen"))
        if name == DEFAULT_HUB_NAME:
            findings.append(Finding(WARNING, "H6", HUB_FILE, f"hub.name is still the default {DEFAULT_HUB_NAME!r}; set your hub's name"))
        if hub.get("repo_url") == DEFAULT_REPO_URL:
            findings.append(Finding(WARNING, "H6", HUB_FILE, "hub.repo_url is still the placeholder; set your repository URL"))

    allow_keys: tuple[str, ...] = ()
    qa = data.get("qa", {})
    if not isinstance(qa, dict):
        findings.append(_error("H5", f"qa must be a mapping, found {type_name(qa)}"))
    else:
        keys = qa.get("allow_keys", [])
        if not isinstance(keys, list) or not all(isinstance(key, str) for key in keys):
            findings.append(_error("H5", "qa.allow_keys must be a list of strings"))
        else:
            allow_keys = tuple(keys)

    if any(finding.level == ERROR for finding in findings):
        return findings, None
    return findings, HubConfig(*(hub[key] for key in REQUIRED_HUB_KEYS), allow_keys=allow_keys)
