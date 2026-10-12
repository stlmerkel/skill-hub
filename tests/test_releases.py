import json
from pathlib import Path

from skill_hub.qa import run_qa
from tests.conftest import ids, make_skill, skill_md, sync_manifests, write_hub

SECRET = "AKIA" + "Q" * 16


def write_release(root: Path, packages: dict | None = None, manifest: dict | None = None) -> None:
    config = {"release-type": "simple", "packages": {} if packages is None else packages}
    (root / "release-please-config.json").write_text(json.dumps(config), encoding="utf-8")
    (root / ".release-please-manifest.json").write_text(json.dumps(manifest or {}), encoding="utf-8")


def entry(name: str) -> dict:
    return {f"skills/{name}": {"component": name, "extra-files": ["SKILL.md"]}}


def hub_with_skill(root: Path) -> Path:
    write_hub(root)
    return make_skill(root)  # changelog-formatter, metadata.version "1.0.0"


def pairs(findings) -> list[tuple[str, str]]:
    return sorted((f.check_id, f.path) for f in findings)


# Opting out and the clean cases

def test_no_release_config_means_no_release_checks(tmp_path):
    hub_with_skill(tmp_path)
    sync_manifests(tmp_path)
    assert run_qa(tmp_path).findings == []


def test_registered_unreleased_skill_is_clean(tmp_path):
    hub_with_skill(tmp_path)
    write_release(tmp_path, entry("changelog-formatter"))
    sync_manifests(tmp_path)
    assert run_qa(tmp_path).findings == []


def test_released_skill_as_release_please_leaves_it_is_clean(tmp_path):
    skill = hub_with_skill(tmp_path)
    write_release(tmp_path, entry("changelog-formatter"), {"skills/changelog-formatter": "1.0.0"})
    (skill / "version.txt").write_text("1.0.0\n", encoding="utf-8")
    changelog = "# Changelog\n\n## 1.0.0 (2026-10-09)\n\n### Features\n\n* first\n"
    (skill / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    sync_manifests(tmp_path)
    assert run_qa(tmp_path).findings == []


def test_non_skill_package_keys_are_ignored(tmp_path):
    hub_with_skill(tmp_path)
    write_release(tmp_path, {**entry("changelog-formatter"), ".": {"component": "kit"}}, {".": "0.1.0"})
    sync_manifests(tmp_path)
    assert run_qa(tmp_path).findings == []


# R5

def test_unregistered_skill_is_r5(tmp_path):
    hub_with_skill(tmp_path)
    write_release(tmp_path)
    assert pairs(run_qa(tmp_path).findings) == [("R5", "skills/changelog-formatter")]


def test_invalid_json_config_is_r5(tmp_path):
    hub_with_skill(tmp_path)
    write_release(tmp_path)
    (tmp_path / "release-please-config.json").write_text("{not json", encoding="utf-8")
    assert pairs(run_qa(tmp_path).findings) == [("R5", "release-please-config.json")]


def test_non_utf8_config_is_r5(tmp_path):
    hub_with_skill(tmp_path)
    write_release(tmp_path)
    (tmp_path / "release-please-config.json").write_bytes(b'{"packages": {"\xff": 1}}')
    assert pairs(run_qa(tmp_path).findings) == [("R5", "release-please-config.json")]


def test_config_that_is_not_an_object_is_r5(tmp_path):
    hub_with_skill(tmp_path)
    write_release(tmp_path)
    (tmp_path / "release-please-config.json").write_text("[]", encoding="utf-8")
    assert pairs(run_qa(tmp_path).findings) == [("R5", "release-please-config.json")]


def test_missing_packages_is_one_r5(tmp_path):
    hub_with_skill(tmp_path)
    make_skill(tmp_path, "second-skill")
    write_release(tmp_path)
    (tmp_path / "release-please-config.json").write_text('{"release-type": "simple"}', encoding="utf-8")
    assert pairs(run_qa(tmp_path).findings) == [("R5", "release-please-config.json")]


def test_missing_manifest_is_r5(tmp_path):
    hub_with_skill(tmp_path)
    write_release(tmp_path, entry("changelog-formatter"))
    (tmp_path / ".release-please-manifest.json").unlink()
    assert pairs(run_qa(tmp_path).findings) == [("R5", ".release-please-manifest.json")]


def test_invalid_manifest_is_r5(tmp_path):
    hub_with_skill(tmp_path)
    write_release(tmp_path, entry("changelog-formatter"))
    (tmp_path / ".release-please-manifest.json").write_text("nope", encoding="utf-8")
    assert pairs(run_qa(tmp_path).findings) == [("R5", ".release-please-manifest.json")]


# R6

def test_stale_config_entry_is_r6(tmp_path):
    hub_with_skill(tmp_path)
    write_release(tmp_path, {**entry("changelog-formatter"), **entry("gone-skill")})
    assert pairs(run_qa(tmp_path).findings) == [("R6", "skills/gone-skill")]


def test_stale_manifest_entry_is_r6(tmp_path):
    hub_with_skill(tmp_path)
    write_release(tmp_path, entry("changelog-formatter"), {"skills/gone-skill": "1.2.0"})
    assert pairs(run_qa(tmp_path).findings) == [("R6", "skills/gone-skill")]


def test_stale_entry_with_invalid_name_is_not_echoed(tmp_path):
    hub_with_skill(tmp_path)
    write_release(tmp_path, {**entry("changelog-formatter"), f"skills/{SECRET} x": {}})
    findings = run_qa(tmp_path).findings
    assert pairs(findings) == [("R6", "release-please-config.json")]
    assert all(SECRET not in f.message and SECRET not in f.path for f in findings)


# S15

def test_version_txt_mismatch_is_s15(tmp_path):
    skill = hub_with_skill(tmp_path)
    write_release(tmp_path, entry("changelog-formatter"))
    (skill / "version.txt").write_text("1.1.0\n", encoding="utf-8")
    assert pairs(run_qa(tmp_path).findings) == [("S15", "skills/changelog-formatter/SKILL.md")]


def test_manifest_mismatch_is_s15_without_echo(tmp_path):
    hub_with_skill(tmp_path)
    write_release(tmp_path, entry("changelog-formatter"), {"skills/changelog-formatter": SECRET})
    findings = run_qa(tmp_path).findings
    assert pairs(findings) == [("S15", "skills/changelog-formatter/SKILL.md")]
    assert SECRET not in findings[0].message


def test_s15_silent_when_version_is_not_a_string(tmp_path):
    write_hub(tmp_path)
    skill = make_skill(tmp_path, text=skill_md(version="1.0"))
    write_release(tmp_path, entry("changelog-formatter"))
    (skill / "version.txt").write_text("1.0.0\n", encoding="utf-8")
    assert ids(run_qa(tmp_path).findings) == ["S7"]


# S16: a registered, never-released skill whose version its first release would change

def write_config(root: Path, config: dict) -> None:
    (root / "release-please-config.json").write_text(json.dumps(config), encoding="utf-8")
    (root / ".release-please-manifest.json").write_text("{}", encoding="utf-8")


def test_unreleased_skill_above_initial_version_is_s16_warning(tmp_path):
    hub_with_skill(tmp_path)  # metadata.version "1.0.0"
    write_config(tmp_path, {"initial-version": "0.1.0", "packages": entry("changelog-formatter")})
    sync_manifests(tmp_path)
    result = run_qa(tmp_path)
    assert result.errors == []
    assert pairs(result.warnings) == [("S16", "skills/changelog-formatter/SKILL.md")]


def test_default_initial_version_is_1_0_0(tmp_path):
    hub_with_skill(tmp_path)
    write_config(tmp_path, {"packages": entry("changelog-formatter")})
    sync_manifests(tmp_path)
    assert run_qa(tmp_path).findings == []


def test_package_initial_version_overrides_top_level(tmp_path):
    hub_with_skill(tmp_path)
    package = {"skills/changelog-formatter": {"component": "changelog-formatter", "initial-version": "1.0.0"}}
    write_config(tmp_path, {"initial-version": "0.1.0", "packages": package})
    sync_manifests(tmp_path)
    assert run_qa(tmp_path).findings == []


def test_released_skill_has_no_s16(tmp_path):
    hub_with_skill(tmp_path)
    write_config(tmp_path, {"initial-version": "0.1.0", "packages": entry("changelog-formatter")})
    (tmp_path / ".release-please-manifest.json").write_text('{"skills/changelog-formatter": "1.0.0"}', encoding="utf-8")
    sync_manifests(tmp_path)
    assert run_qa(tmp_path).findings == []


def test_unregistered_skill_has_no_s16(tmp_path):
    hub_with_skill(tmp_path)
    write_config(tmp_path, {"initial-version": "0.1.0", "packages": {}})
    assert ids(run_qa(tmp_path).findings) == ["R5"]
