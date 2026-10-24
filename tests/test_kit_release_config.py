"""The kit's own Release Please stream: config, manifest and version markers (kit-owned files at the repo root).

These files arrive in every hub with each kit update, so the ungated tests check structure only. Checks on the
kit's release state (manifest, changelog) run only where SKILL_HUB_KIT_RELEASES is "true" (the kit repo), and
never pin a value a release changes.
"""

import json
import os
from pathlib import Path, PurePosixPath

import pytest

from skill_hub.contract import HUB_OWNED_PATHS, KIT_RELEASE_CONFIG, KIT_RELEASE_MANIFEST, parse_version
from skill_hub.releases import RELEASE_CONFIG

ROOT = Path(__file__).parent.parent
kit_only = pytest.mark.skipif(os.environ.get("SKILL_HUB_KIT_RELEASES") != "true", reason="kit repo only")


def kit_config() -> dict:
    path = ROOT / KIT_RELEASE_CONFIG
    if not path.is_file():
        pytest.skip("this hub has deleted the kit release config")
    return json.loads(path.read_text(encoding="utf-8"))


def test_kit_config_and_manifest_names():
    assert KIT_RELEASE_CONFIG == "kit-release-please-config.json"
    assert KIT_RELEASE_MANIFEST == ".kit-release-please-manifest.json"


@kit_only
def test_kit_manifest_holds_one_version():
    manifest = json.loads((ROOT / KIT_RELEASE_MANIFEST).read_text(encoding="utf-8"))
    assert list(manifest) == ["."]
    assert parse_version(manifest["."]) is not None


def test_kit_package_shape():
    config = kit_config()
    assert config["release-type"] == "simple"
    assert config["include-component-in-tag"] is True
    assert config["bump-minor-pre-major"] is False
    (path, package) = next(iter(config["packages"].items()))
    assert list(config["packages"]) == ["."]
    assert path == "."
    assert package["component"] == "kit"
    assert package["changelog-path"] == "CHANGELOG.md"
    # release-as pins only the first release (KIT.md, "Maintaining the kit"); its value is not asserted.
    if "release-as" in package:
        assert parse_version(package["release-as"]) is not None
    # A bare .yml path makes Release Please parse and re-dump the file, dropping its comments and marker.
    assert package["extra-files"] == [{"type": "generic", "path": ".skill-hub/kit.yml"}]


def test_kit_exclude_paths_match_contract():
    package = kit_config()["packages"]["."]
    # Release Please matches exclude-paths as folder prefixes only (`file.indexOf(path + '/') === 0`), so a
    # root-level hub-owned file (README.md, the release-please files) cannot be excluded. In the kit repo a
    # feat:/fix: commit touching only those still bumps the kit: accepted, the kit stream never runs in hubs.
    expected = []
    for path in HUB_OWNED_PATHS:
        folder = path.rstrip("/") if path.endswith("/") else str(PurePosixPath(path).parent)
        if folder != "." and folder not in expected:
            expected.append(folder)
    assert package["exclude-paths"] == expected == ["skills", ".claude-plugin", ".cursor-plugin"]


def test_kit_labels_differ_from_skill_stream():
    kit = kit_config()
    skills = json.loads((ROOT / RELEASE_CONFIG).read_text(encoding="utf-8"))
    for key in ("label", "release-label", "snapshot-label"):
        assert kit[key].startswith("autorelease: kit-")
        assert kit[key] != skills.get(key)
    assert len({kit["label"], kit["release-label"], kit["snapshot-label"]}) == 3


def test_kit_extra_files_carry_markers():
    # pyproject.toml is not an extra-file: bumping it would leave uv.lock stale and break `uv sync --locked`.
    assert "pyproject.toml" not in json.dumps(kit_config()["packages"]["."]["extra-files"])
    assert "x-release-please" not in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    lines = (ROOT / ".skill-hub/kit.yml").read_text(encoding="utf-8").splitlines()
    version_lines = [line for line in lines if line.startswith("version")]
    assert len(version_lines) == 1
    assert "x-release-please-version" in version_lines[0]


@kit_only
def test_release_as_is_gone_once_released():
    # release-as pins only the first release (KIT.md, "Maintaining the kit"). Release Please moves the manifest to
    # that version when it cuts the release; a key still set then forces every later release to the same version.
    package = kit_config()["packages"]["."]
    if "release-as" in package:
        released = json.loads((ROOT / KIT_RELEASE_MANIFEST).read_text(encoding="utf-8"))["."]
        assert parse_version(released) < parse_version(package["release-as"]), (
            f"kit v{released} is released: remove release-as from {KIT_RELEASE_CONFIG}"
        )


@kit_only
def test_changelog_starts_as_heading():
    assert (ROOT / "CHANGELOG.md").read_text(encoding="utf-8").startswith("# Changelog\n")
