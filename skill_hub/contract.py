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


def is_utf8_encodable(value: str) -> bool:
    """False for a string holding a lone surrogate, which cannot be written to a UTF-8 file."""
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


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


# Marketplace names Claude Code refuses, from code.claude.com/docs/en/plugins/marketplace-reference#reserved-names
# (checked 2026-10-10). Compared lowercased; hub.name is already lowercase kebab-case (H4).
RESERVED_MARKETPLACE_NAMES = frozenset({
    "claude-code-marketplace", "claude-code-plugins", "claude-plugins-official", "anthropic-marketplace",
    "anthropic-plugins", "agent-skills", "anthropic-agent-skills", "life-sciences", "knowledge-work-plugins",
    "claude-for-legal", "claude-for-financial-services", "financial-services-plugins", "first-party-plugins",
    "claude-tag-plugins", "claude-community", "claude-plugins-community", "healthcare",
    "anthropic-plugin-directory", "claude-plugin-directory", "inline", "builtin", "skills-dir", "synced",
    "claude-plugin-test", "npm", "pip", "uv", "cargo", "github", "gh", "constructor", "hasownproperty",
    "isprototypeof", "propertyisenumerable", "tolocalestring", "tostring", "valueof",
})
RESERVED_MARKETPLACE_PREFIX = "claudeai-"

# Plugin names Claude Code refuses as passing for Anthropic's own, from
# code.claude.com/docs/en/plugins/manifest-reference#name (checked 2026-10-10).
_RESERVED_PLUGIN_NAMES = frozenset({"claude", "anthropic", "anthropics", "claude-code", "claude-mods"})
_RESERVED_PLUGIN_PREFIXES = ("claude-", "anthropic-", "anthropics-", "cc-plugin-")
_OFFICIAL_NEIGHBOURS = frozenset({"claude", "anthropic"})

_GITHUB_REPO_RE = re.compile(r"https://github\.com/([A-Za-z0-9-]+)/([A-Za-z0-9._-]+?)(?:\.git)?/?", re.ASCII)


def is_reserved_marketplace_name(value: str) -> bool:
    lowered = value.lower()
    return lowered in RESERVED_MARKETPLACE_NAMES or lowered.startswith(RESERVED_MARKETPLACE_PREFIX)


def is_reserved_plugin_name(value: str) -> bool:
    lowered = value.lower()
    if lowered in _RESERVED_PLUGIN_NAMES or lowered.startswith(_RESERVED_PLUGIN_PREFIXES):
        return True
    words = lowered.split("-")
    return any(
        "official" in pair and pair & _OFFICIAL_NEIGHBOURS
        for pair in (set(words[i : i + 2]) for i in range(len(words) - 1))
    )


def github_repo(repo_url: str) -> str | None:
    """`owner/repo` for an exact https://github.com/<owner>/<repo> URL (trailing .git or / allowed), else None."""
    match = _GITHUB_REPO_RE.fullmatch(repo_url)
    if match is None or match[2] in {".", ".."}:
        return None
    return f"{match[1]}/{match[2]}"
