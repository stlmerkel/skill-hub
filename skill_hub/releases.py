"""Release config checks (R5, R6) over release-please-config.json and its manifest."""

import json
from pathlib import Path

from skill_hub.contract import is_valid_name
from skill_hub.findings import ERROR, Finding

RELEASE_CONFIG = "release-please-config.json"
RELEASE_MANIFEST = ".release-please-manifest.json"
VERSION_FILE = "version.txt"  # written into each skill by Release Please's simple release type
PACKAGE_PREFIX = "skills/"
DEFAULT_INITIAL_VERSION = "1.0.0"  # what Release Please releases first when initial-version is unset


def read_json_object(path: Path) -> dict | None:
    """The JSON object in path, or None when path does not exist.

    Raises OSError when the file cannot be read, ValueError when it is not UTF-8 JSON holding an object.
    """
    if not path.exists() and not path.is_symlink():
        return None
    data = json.loads(path.read_bytes().decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("not a JSON object")
    return data


def _load(root: Path, name: str, findings: list[Finding]) -> dict | None:
    try:
        return read_json_object(root / name)
    except OSError:
        findings.append(Finding(ERROR, "R5", name, "could not be read"))
    except ValueError:
        findings.append(Finding(ERROR, "R5", name, "must be a UTF-8 JSON object"))
    return {}


def check_release(root: Path, skill_names: list[str]) -> tuple[list[Finding], dict[str, str], dict[str, str]]:
    """R5 and R6 findings; each released skill's manifest version; each unreleased skill's first-release version."""
    findings: list[Finding] = []
    config = _load(root, RELEASE_CONFIG, findings)
    if config is None:
        return [], {}, {}  # no release config: the hub has opted out of releases
    if findings:
        return findings, {}, {}

    packages = config.get("packages")
    if not isinstance(packages, dict):
        findings.append(Finding(ERROR, "R5", RELEASE_CONFIG, "has no packages object"))
    manifest = _load(root, RELEASE_MANIFEST, findings)
    if manifest is None:
        findings.append(Finding(ERROR, "R5", RELEASE_MANIFEST, "not found; release-please needs it, even as {}"))
        manifest = {}

    skills = set(skill_names)
    listed = packages if isinstance(packages, dict) else {}
    if isinstance(packages, dict):
        for name in skill_names:
            if PACKAGE_PREFIX + name not in listed:
                message = f"not listed under packages in {RELEASE_CONFIG}"
                findings.append(Finding(ERROR, "R5", PACKAGE_PREFIX + name, message))
    for source, entries in ((RELEASE_CONFIG, listed), (RELEASE_MANIFEST, manifest)):
        for key in entries:
            if not key.startswith(PACKAGE_PREFIX):
                continue
            name = key[len(PACKAGE_PREFIX):]
            if name in skills:
                continue
            if is_valid_name(name):
                findings.append(Finding(ERROR, "R6", key, f"listed in {source} but is not a skill"))
            else:
                findings.append(Finding(ERROR, "R6", source, "an entry under skills/ is not a skill"))

    released = {
        key[len(PACKAGE_PREFIX):]: version
        for key, version in manifest.items()
        if key.startswith(PACKAGE_PREFIX) and isinstance(version, str)
    }
    default_initial = config.get("initial-version")
    if not isinstance(default_initial, str):
        default_initial = DEFAULT_INITIAL_VERSION
    first_release = {}
    for name in skill_names:
        package = listed.get(PACKAGE_PREFIX + name)
        if name in released or not isinstance(package, dict):
            continue
        initial = package.get("initial-version")
        first_release[name] = initial if isinstance(initial, str) else default_initial
    return findings, released, first_release
