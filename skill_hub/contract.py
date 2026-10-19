"""The skill and hub contract: constants and pure rules shared by every check."""

from collections.abc import Callable
import datetime
import re

NAME_MAX = 64
DESCRIPTION_MAX = 1024
COMPATIBILITY_MAX = 500

# Agent Skills specification top-level keys (agentskills.io, checked 2026-10-08).
SPEC_KEYS = frozenset({"name", "description", "license", "compatibility", "metadata", "allowed-tools"})

DEFAULT_HUB_NAME = "my-skill-hub"
DEFAULT_REPO_URL = "https://github.com/you/your-hub"

HUB_FILE = "hub.yml"

# Template updates: the file that records a hub's kit release, and the kit's release-tag shape.
KIT_FILE = ".skill-hub/kit.yml"
KIT_TAG_PREFIX = "kit-v"
WORKFLOWS_DIR = ".github/workflows/"

# Paths a hub owns: an update never touches them. A trailing "/" marks a folder.
HUB_OWNED_PATHS: tuple[str, ...] = (
    "README.md",
    "skills/",
    "release-please-config.json",
    ".release-please-manifest.json",
    ".claude-plugin/marketplace.json",
    ".cursor-plugin/marketplace.json",
)
# The kit's own Release Please stream (kit-owned, never copied into a hub).
KIT_RELEASE_CONFIG = "kit-release-please-config.json"
KIT_RELEASE_MANIFEST = ".kit-release-please-manifest.json"
# Regenerated from other files, never merged.
DERIVED_PATHS = frozenset({"uv.lock"})
# Skill names the kit keeps for itself: `kit` would collide with the kit's own release tags.
RESERVED_SKILL_NAMES = frozenset({"kit"})

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


def is_hub_owned(path: str) -> bool:
    return any(
        path.startswith(owned) if owned.endswith("/") else path == owned for owned in HUB_OWNED_PATHS
    )


_PLAIN_VERSION_RE = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", re.ASCII)


def parse_version(value: str) -> tuple[int, int, int] | None:
    """`X.Y.Z` with no leading zeros and no suffix, as a tuple, else None."""
    match = _PLAIN_VERSION_RE.fullmatch(value)
    return None if match is None else (int(match[1]), int(match[2]), int(match[3]))


def parse_kit_tag(tag: str) -> tuple[int, int, int] | None:
    return parse_version(tag[len(KIT_TAG_PREFIX) :]) if tag.startswith(KIT_TAG_PREFIX) else None


def is_valid_kit_repo(value: str) -> bool:
    """An https:// or file:// location: never an option-like string, and no whitespace, control, quote or backslash."""
    if '"' in value or "\\" in value or any(ord(char) <= 0x20 or ord(char) == 0x7F for char in value):
        return False
    return any(value.startswith(scheme) and len(value) > len(scheme) for scheme in (_HTTPS, "file://"))


_COMMIT_RE = re.compile(r"[0-9a-f]{40}", re.ASCII)


def is_valid_commit(value: str) -> bool:
    return _COMMIT_RE.fullmatch(value) is not None


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

# Deploy targets the kit ships a workflow for, and the hub.yml settings each one reads (deploy.<target>.<key>).
DEPLOY_TARGET_SETTINGS = {
    "github-pages": (),
    "s3": ("bucket", "endpoint", "region"),
    "rsync": ("host", "user", "path", "port"),
}
REQUIRED_DEPLOY_SETTINGS = {"s3": ("bucket", "region"), "rsync": ("host", "user", "path")}
DEFAULT_RSYNC_PORT = 22

# Allow-lists, not deny-lists: these values reach a shell on a runner that holds deploy secrets,
# and become `name=value` lines in $GITHUB_OUTPUT, so a newline or shell metacharacter must never pass.
_HOST_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
_HOST_RE = re.compile(rf"{_HOST_LABEL}(?:\.{_HOST_LABEL})*", re.ASCII)
_ENDPOINT_RE = re.compile(rf"https://{_HOST_LABEL}(?:\.{_HOST_LABEL})*(?::[0-9]{{1,5}})?/?", re.ASCII)
_BUCKET_RE = re.compile(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", re.ASCII)
_REGION_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*", re.ASCII)
_SSH_USER_RE = re.compile(r"[a-z_][a-z0-9_-]{0,31}", re.ASCII)
_DEPLOY_PATH_RE = re.compile(r"[A-Za-z0-9._~/+-]+", re.ASCII)


def is_valid_bucket(value: str) -> bool:
    return _BUCKET_RE.fullmatch(value) is not None and ".." not in value


def is_valid_endpoint(value: str) -> bool:
    return _ENDPOINT_RE.fullmatch(value) is not None


def is_valid_region(value: str) -> bool:
    return _REGION_RE.fullmatch(value) is not None


def is_valid_host(value: str) -> bool:
    return len(value) <= 253 and _HOST_RE.fullmatch(value) is not None


def is_valid_ssh_user(value: str) -> bool:
    return _SSH_USER_RE.fullmatch(value) is not None


def is_valid_deploy_path(value: str) -> bool:
    if _DEPLOY_PATH_RE.fullmatch(value) is None or value.startswith("-"):
        return False
    segments = value.split("/")
    if ".." in segments:
        return False
    named = [segment for segment in segments if segment not in ("", ".")]
    return bool(named) and not (len(named) == 1 and named[0].startswith("~"))


def is_valid_port(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 65535


DEPLOY_SETTING_RULES: dict[tuple[str, str], tuple[Callable[[object], bool], str]] = {
    ("s3", "bucket"): (
        is_valid_bucket,
        "must be 3-63 characters of a-z, 0-9, dots and hyphens, starting and ending with a letter or digit",
    ),
    ("s3", "endpoint"): (
        is_valid_endpoint,
        "must be an https:// URL with only a host and an optional port, such as https://minio.example.com:9000",
    ),
    ("s3", "region"): (is_valid_region, "must be lowercase letters, digits and single hyphens, such as us-east-1"),
    ("rsync", "host"): (is_valid_host, "must be a hostname or an IPv4 address"),
    ("rsync", "user"): (
        is_valid_ssh_user,
        "must be 1-32 characters of a-z, 0-9, _ and -, starting with a letter or _",
    ),
    ("rsync", "path"): (
        is_valid_deploy_path,
        "must use only letters, digits and . _ ~ / + -, must not start with - or contain a .. segment, "
        "and must name a folder below / or ~",
    ),
    ("rsync", "port"): (is_valid_port, "must be a number from 1 to 65535"),
}
