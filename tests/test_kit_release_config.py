"""The kit's own Release Please stream: config, manifest and version markers (kit-owned files at the repo root)."""

import json
from pathlib import Path

from skill_hub.contract import HUB_OWNED_PATHS, KIT_RELEASE_CONFIG, KIT_RELEASE_MANIFEST
from skill_hub.releases import RELEASE_CONFIG

ROOT = Path(__file__).parent.parent


def kit_config() -> dict:
    return json.loads((ROOT / KIT_RELEASE_CONFIG).read_text(encoding="utf-8"))


def test_kit_config_and_manifest_names():
    assert KIT_RELEASE_CONFIG == "kit-release-please-config.json"
    assert KIT_RELEASE_MANIFEST == ".kit-release-please-manifest.json"
    assert json.loads((ROOT / KIT_RELEASE_MANIFEST).read_text(encoding="utf-8")) == {".": "0.0.0"}


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
    assert package["release-as"] == "1.0.0"
    assert package["extra-files"] == [".skill-hub/kit.yml", {"type": "generic", "path": "pyproject.toml"}]


def test_kit_exclude_paths_match_contract():
    package = kit_config()["packages"]["."]
    assert package["exclude-paths"] == [path.rstrip("/") for path in HUB_OWNED_PATHS]


def test_kit_labels_differ_from_skill_stream():
    kit = kit_config()
    skills = json.loads((ROOT / RELEASE_CONFIG).read_text(encoding="utf-8"))
    for key in ("label", "release-label", "snapshot-label"):
        assert kit[key].startswith("autorelease: kit-")
        assert kit[key] != skills.get(key)
    assert len({kit["label"], kit["release-label"], kit["snapshot-label"]}) == 3


def test_kit_extra_files_carry_markers():
    for name in (".skill-hub/kit.yml", "pyproject.toml"):
        lines = (ROOT / name).read_text(encoding="utf-8").splitlines()
        version_lines = [line for line in lines if line.startswith("version")]
        assert len(version_lines) == 1, name
        assert "x-release-please-version" in version_lines[0], name


def test_changelog_starts_as_heading():
    assert (ROOT / "CHANGELOG.md").read_text(encoding="utf-8") == "# Changelog\n"
