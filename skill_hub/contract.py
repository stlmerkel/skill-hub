"""The skill and hub contract: constants and pure rules shared by every check."""

import datetime
import re

NAME_MAX = 64
DESCRIPTION_MAX = 1024
COMPATIBILITY_MAX = 500

# Agent Skills specification top-level keys (agentskills.io, checked 2026-10-08).
SPEC_KEYS = frozenset({"name", "description", "license", "compatibility", "metadata", "allowed-tools"})

DEFAULT_HUB_NAME = "my-skill-hub"
DEFAULT_REPO_URL = "https://github.com/you/your-hub"

_NAME_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*", re.ASCII)

# Official SemVer 2.0.0 regex from semver.org, without ^/$ (fullmatch anchors it).
# re.ASCII keeps \d to ASCII digits.
_SEMVER_RE = re.compile(
    r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?",
    re.ASCII,
)


def is_valid_name(value: str) -> bool:
    return 1 <= len(value) <= NAME_MAX and _NAME_RE.fullmatch(value) is not None


def is_valid_semver(value: str) -> bool:
    return _SEMVER_RE.fullmatch(value) is not None


def is_blank(value: str) -> bool:
    return value.strip() == ""


def type_name(value: object) -> str:
    """Describe a YAML-produced value's type without echoing the value."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, (datetime.date, datetime.datetime)):
        return "date"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "mapping"
    return type(value).__name__
