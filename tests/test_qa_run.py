# tests/test_qa_run.py
import os
import sys

import pytest

from skill_hub.qa import run_qa
from tests.conftest import ids, make_skill, sync_manifests, write_hub


def test_clean_run(tmp_path):
    write_hub(tmp_path)
    make_skill(tmp_path)
    sync_manifests(tmp_path)
    result = run_qa(tmp_path)
    assert result.findings == [] and result.skill_count == 1


def test_r1_missing_skills(tmp_path):
    write_hub(tmp_path)
    assert ids(run_qa(tmp_path).findings) == ["R1"]


def test_r1_skills_is_a_file(tmp_path):
    write_hub(tmp_path)
    (tmp_path / "skills").write_text("x", encoding="utf-8")
    assert ids(run_qa(tmp_path).findings) == ["R1"]


def test_r2_no_skills(tmp_path):
    write_hub(tmp_path)
    (tmp_path / "skills" / ".hidden").mkdir(parents=True)
    assert ids(run_qa(tmp_path).findings) == ["R2"]


def test_r3_stray_file_warns(tmp_path):
    write_hub(tmp_path)
    make_skill(tmp_path)
    (tmp_path / "skills" / "notes.txt").write_text("x", encoding="utf-8")
    sync_manifests(tmp_path)
    result = run_qa(tmp_path)
    assert ids(result.findings) == ["R3"] and result.warnings and not result.errors


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges on Windows")
def test_r4_symlinked_skill_dir_warns(tmp_path):
    write_hub(tmp_path)
    make_skill(tmp_path)
    (tmp_path / "skills" / "linked").symlink_to(tmp_path / "skills" / "changelog-formatter")
    sync_manifests(tmp_path)
    assert ids(run_qa(tmp_path).findings) == ["R4"]


def test_broken_hub_still_checks_skills_with_empty_allow_keys(tmp_path):
    write_hub(tmp_path, "hub: []\nqa:\n  allow_keys: [when_to_use]\n")
    make_skill(tmp_path, text=None)
    skill_md_path = tmp_path / "skills" / "changelog-formatter" / "SKILL.md"
    skill_md_path.write_text(
        skill_md_path.read_text(encoding="utf-8").replace("---\n\n", "when_to_use: x\n---\n\n", 1),
        encoding="utf-8",
    )
    assert ids(run_qa(tmp_path).findings) == ["H3", "S6"]


@pytest.mark.skipif(sys.platform == "win32" or os.geteuid() == 0, reason="permissions not enforced")
def test_r1_unreadable_skills(tmp_path):
    write_hub(tmp_path)
    make_skill(tmp_path)
    skills = tmp_path / "skills"
    skills.chmod(0)
    try:
        assert "R1" in ids(run_qa(tmp_path).findings)
    finally:
        skills.chmod(0o755)


def test_hidden_directory_in_skills_is_not_a_skill(tmp_path):
    write_hub(tmp_path)
    make_skill(tmp_path)
    hidden = tmp_path / "skills" / ".cache"
    hidden.mkdir()
    (hidden / "SKILL.md").write_text("garbage", encoding="utf-8")
    sync_manifests(tmp_path)
    result = run_qa(tmp_path)
    assert result.findings == [] and result.skill_count == 1


@pytest.mark.skipif(sys.platform == "win32" or os.geteuid() == 0, reason="permissions not enforced")
@pytest.mark.parametrize("mode", [0o000, 0o644])
def test_unreadable_skill_directory_is_s13_not_traceback(tmp_path, mode):
    write_hub(tmp_path)
    make_skill(tmp_path, "aaa-good")
    skill = make_skill(tmp_path, "zzz-locked")
    skill.chmod(mode)
    try:
        result = run_qa(tmp_path)
    finally:
        skill.chmod(0o755)
    assert [(f.check_id, f.path) for f in result.findings] == [("S13", "skills/zzz-locked")]
    assert result.skill_count == 2


@pytest.mark.skipif(sys.platform == "win32" or os.geteuid() == 0, reason="permissions not enforced")
def test_unstatable_skills_entries_are_s13(tmp_path):
    write_hub(tmp_path)
    make_skill(tmp_path)
    skills = tmp_path / "skills"
    skills.chmod(0o644)  # listable, not searchable: entries cannot be stat'ed
    try:
        result = run_qa(tmp_path)
    finally:
        skills.chmod(0o755)
    found = sorted((f.check_id, f.path) for f in result.findings)
    assert found == [("R2", "skills"), ("S13", "skills/changelog-formatter")]


def _hub_with_kit_file(tmp_path, text):
    write_hub(tmp_path)
    make_skill(tmp_path)
    sync_manifests(tmp_path)
    kit = tmp_path / ".skill-hub" / "kit.yml"
    kit.parent.mkdir()
    kit.write_text(text, encoding="utf-8")


def test_h17_pending_workflows_warns(tmp_path):
    text = (
        'repo: "https://github.com/acme/kit"\nversion: "1.1.0"\ncommit: "' + "a" * 40 + '"\n'
        'workflows_version: "1.0.0"\nworkflows_commit: "' + "b" * 40 + '"\n'
    )
    _hub_with_kit_file(tmp_path, text)
    result = run_qa(tmp_path)
    assert ids(result.findings) == ["H17"] and result.warnings and not result.errors


def test_h17_unreadable_kit_file_warns(tmp_path):
    _hub_with_kit_file(tmp_path, "a: [")
    result = run_qa(tmp_path)
    assert ids(result.findings) == ["H17"] and result.warnings and not result.errors


def test_no_kit_file_no_h17(tmp_path):
    write_hub(tmp_path)
    make_skill(tmp_path)
    sync_manifests(tmp_path)
    assert run_qa(tmp_path).findings == []


def test_current_kit_file_has_no_h17(tmp_path):
    _hub_with_kit_file(tmp_path, 'repo: "https://github.com/acme/kit"\nversion: "1.1.0"\n')
    assert run_qa(tmp_path).findings == []
