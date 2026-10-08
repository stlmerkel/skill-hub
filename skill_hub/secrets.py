"""Line-based secret tripwire: known token shapes and credential assignments."""

import re
from dataclasses import dataclass

ALLOW_MARKER = "skill-hub: allow-secret"

_TOKENS = (
    ("AWS access key", re.compile(r"(?<![A-Za-z0-9])(?:AKIA|ASIA)[0-9A-Z]{16}")),
    ("GitHub token", re.compile(r"(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{36,}|(?<![A-Za-z0-9])github_pat_[A-Za-z0-9_]{22,}")),
    ("Slack token", re.compile(r"(?<![A-Za-z0-9])xox[abprs]-[A-Za-z0-9-]{10,}")),
    ("sk- API key", re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{20,}")),
    ("Google API key", re.compile(r"(?<![A-Za-z0-9])AIza[0-9A-Za-z_-]{35}")),
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED |)PRIVATE KEY-----")),
)

_SENSITIVE_SEGMENTS = frozenset({"secret", "token", "password", "passwd", "pwd", "apikey"})
_SENSITIVE_SUFFIXES = (
    "api_key", "api-key", "private_key", "private-key",
    "client_secret", "access_key", "secret_key",
)

_ASSIGNMENT = re.compile(
    r"""(?<![A-Za-z0-9_-])(?P<nq>["']?)(?P<name>[A-Za-z_][A-Za-z0-9_-]*)(?P=nq)"""
    r"""\s*[:=]\s*"""
    r"""(?:(?P<vq>["'])(?P<quoted>.*?)(?P=vq)"""
    r"""|(?P<bare>[^\s"'`()\[\]{}<>:,;]{16,})(?=$|[\s,;]))"""
)

_PLACEHOLDER_WORDS = frozenset({"changeme", "example", "placeholder", "redacted"})
_PLACEHOLDER_FORMS = (
    re.compile(r"<[^<>]*>"),
    re.compile(r"\$\{[^{}]*\}"),
    re.compile(r"\{\{[^{}]*\}\}"),
    re.compile(r"[xX*.]+"),
)


@dataclass(frozen=True)
class SecretHit:
    line: int
    kind: str


def _is_sensitive_name(name: str) -> bool:
    lower = name.lower()
    if lower.endswith(_SENSITIVE_SUFFIXES):
        return True
    return re.split(r"[_-]", lower)[-1] in _SENSITIVE_SEGMENTS


def _is_placeholder(value: str) -> bool:
    lower = value.lower()
    if lower in _PLACEHOLDER_WORDS or lower.startswith(("your-", "your_")):
        return True
    return any(form.fullmatch(value) for form in _PLACEHOLDER_FORMS)


def _assignment_value_is_secret(match: re.Match) -> bool:
    quoted, bare = match.group("quoted"), match.group("bare")
    if quoted is not None:
        if len(quoted) < 8 or any(ch.isspace() for ch in quoted):
            return False
        value = quoted
    else:
        if not (any(ch.isalpha() for ch in bare) and any(ch.isdigit() for ch in bare)):
            return False
        value = bare
    return not _is_placeholder(value)


def _scan_line(line: str) -> str | None:
    for kind, pattern in _TOKENS:
        if pattern.search(line):
            return kind
    for match in _ASSIGNMENT.finditer(line):
        if _is_sensitive_name(match.group("name")) and _assignment_value_is_secret(match):
            return "credential assignment"
    return None


def scan_text(text: str) -> list[SecretHit]:
    hits = []
    for number, line in enumerate(text.splitlines(), start=1):
        if ALLOW_MARKER in line:
            continue
        kind = _scan_line(line)
        if kind is not None:
            hits.append(SecretHit(number, kind))
    return hits
