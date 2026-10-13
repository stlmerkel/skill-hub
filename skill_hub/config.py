"""Load and check hub.yml (checks H1-H16; the deploy block's H12-H16 live in deploy.py)."""

from dataclasses import dataclass
from pathlib import Path

from skill_hub.contract import (
    DEFAULT_HUB_NAME,
    DEFAULT_REPO_URL,
    HUB_FILE,
    is_blank,
    is_utf8_encodable,
    is_hex_colour,
    is_reserved_marketplace_name,
    is_safe_logo_url,
    is_valid_name,
    type_name,
)
from skill_hub.deploy import DeploySettings, check_deploy
from skill_hub.findings import ERROR, WARNING, Finding
from skill_hub.yamlutil import load_yaml

REQUIRED_HUB_KEYS = ("name", "display_name", "owner", "description", "repo_url")
SITE_KEYS = ("accent", "logo_url", "theme")
THEME_ENTRY = "index.html.j2"


@dataclass(frozen=True)
class SiteSettings:
    accent: str = ""
    logo_url: str = ""
    theme: str = ""


@dataclass(frozen=True)
class HubConfig:
    name: str
    display_name: str
    owner: str
    description: str
    repo_url: str
    allow_keys: tuple[str, ...]
    site: SiteSettings = SiteSettings()
    deploy: DeploySettings = DeploySettings()


MANIFEST_KEYS = ("owner", "description")  # copied into the marketplace manifests, which are written as UTF-8


def _error(check_id: str, message: str, line: int | None = None) -> Finding:
    return Finding(ERROR, check_id, HUB_FILE, message, line)


def _check_theme(root: Path, theme: str) -> list[Finding]:
    try:
        hub_root = root.resolve()
        folder = (root / theme).resolve()
    except (OSError, RuntimeError, ValueError):  # RuntimeError: a symlink loop on 3.11/3.12; ValueError: a NUL
        return [_error("H10", "site.theme could not be resolved")]
    if folder == hub_root or not folder.is_relative_to(hub_root):
        return [_error("H10", "site.theme must be a folder inside the hub root")]
    if not folder.is_dir():
        return [_error("H10", "site.theme folder not found")]
    entry = folder / THEME_ENTRY
    if entry.is_symlink() or not entry.is_file():
        return [_error("H10", f"site.theme has no {THEME_ENTRY}")]
    return []


def _check_site(root: Path, data: dict) -> tuple[list[Finding], SiteSettings]:
    site = data.get("site")
    if site is None:  # absent, or a `site:` block with every key commented out
        return [], SiteSettings()
    if not isinstance(site, dict):
        return [_error("H7", f"site must be a mapping, found {type_name(site)}")], SiteSettings()

    findings: list[Finding] = []
    if any(key not in SITE_KEYS for key in site):
        message = "site has an unknown key; expected accent, logo_url or theme"
        findings.append(Finding(WARNING, "H7", HUB_FILE, message))
    values: dict[str, str] = {}
    for key in SITE_KEYS:
        if key not in site:
            continue
        value = site[key]
        if isinstance(value, str):
            values[key] = value
        else:
            findings.append(_error("H7", f"site.{key} must be a string, found {type_name(value)}; quote it"))

    accent = values.get("accent", "")
    if accent and not is_hex_colour(accent):
        findings.append(_error("H8", 'site.accent must be a hex colour such as "#4f46e5"'))
    logo_url = values.get("logo_url", "")
    if logo_url and not is_safe_logo_url(logo_url):
        findings.append(_error("H9", "site.logo_url must be an https:// URL or a relative path"))
    theme = values.get("theme", "")
    if theme:
        findings.extend(_check_theme(root, theme))
    return findings, SiteSettings(**values)


def check_hub(root: Path) -> tuple[list[Finding], HubConfig | None]:
    path = root / HUB_FILE
    if not path.exists():
        return [_error("H1", "hub.yml not found at the repository root")], None
    if not path.is_file():
        return [_error("H1", "hub.yml is not a regular file")], None

    try:
        text = path.read_bytes().decode("utf-8").removeprefix("\ufeff")
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
            elif key in MANIFEST_KEYS and not is_utf8_encodable(value):
                message = f"hub.{key} contains a character that can't be written as UTF-8 (a lone surrogate escape?)"
                findings.append(_error("H3", message))
        name = hub.get("name")
        if isinstance(name, str) and not is_blank(name) and not is_valid_name(name):
            findings.append(_error(
                "H4",
                "hub.name must be 1-64 characters of a-z, 0-9 and single hyphens, with no leading or trailing hyphen",
            ))
        if isinstance(name, str) and is_valid_name(name) and is_reserved_marketplace_name(name):
            findings.append(_error("H11", "hub.name is a marketplace name Claude Code reserves; choose another"))
        if name == DEFAULT_HUB_NAME:
            message = f"hub.name is still the default {DEFAULT_HUB_NAME!r}; set your hub's name"
            findings.append(Finding(WARNING, "H6", HUB_FILE, message))
        if hub.get("repo_url") == DEFAULT_REPO_URL:
            message = "hub.repo_url is still the placeholder; set your repository URL"
            findings.append(Finding(WARNING, "H6", HUB_FILE, message))

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

    site_findings, site = _check_site(root, data)
    findings.extend(site_findings)

    deploy_findings, deploy = check_deploy(root, data)
    findings.extend(deploy_findings)

    if any(finding.level == ERROR for finding in findings):
        return findings, None
    return findings, HubConfig(
        *(hub[key] for key in REQUIRED_HUB_KEYS), allow_keys=allow_keys, site=site, deploy=deploy
    )
