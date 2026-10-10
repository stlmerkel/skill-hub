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

# Written by `skill-hub new-skill` and flagged by QA check S14 until replaced.
SCAFFOLD_DESCRIPTION = "TODO: say what this skill does and when an agent should use it."

NAME_RULE = "name must be 1-64 characters of a-z, 0-9 and single hyphens, with no leading or trailing hyphen"

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


_HEX_COLOUR_RE = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})", re.ASCII)
_URL_SCHEME_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:", re.ASCII)
_HTTPS = "https://"


def is_hex_colour(value: str) -> bool:
    return _HEX_COLOUR_RE.fullmatch(value) is not None


def is_safe_logo_url(value: str) -> bool:
    """An https:// URL or a relative path: never a script-capable, plain-http or protocol-relative URL."""
    # Browsers strip leading whitespace and control characters and read a backslash as a slash.
    if "\\" in value or any(ord(char) <= 0x20 or ord(char) == 0x7F for char in value):
        return False
    if value.startswith(_HTTPS):
        return len(value) > len(_HTTPS)
    return not value.startswith("//") and _URL_SCHEME_RE.match(value) is None
