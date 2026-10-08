import os
# tests/test_qa_run.py
import sys

import pytest

from skill_hub.qa import run_qa
from tests.conftest import ids, make_skill, write_hub


def test_clean_run(tmp_path):
    write_hub(tmp_path)
    make_skill(tmp_path)
    result = run_qa(tmp_path)
    assert result.findings == [] and result.skill_count == 1


def test_r1_missing_src(tmp_path):
    write_hub(tmp_path)
    assert ids(run_qa(tmp_path).findings) == ["R1"]


def test_r1_src_is_a_file(tmp_path):
    write_hub(tmp_path)
    (tmp_path / "src").write_text("x", encoding="utf-8")
    assert ids(run_qa(tmp_path).findings) == ["R1"]


def test_r2_no_skills(tmp_path):
    write_hub(tmp_path)
    (tmp_path / "src" / ".hidden").mkdir(parents=True)
    assert ids(run_qa(tmp_path).findings) == ["R2"]


def test_r3_stray_file_warns(tmp_path):
    write_hub(tmp_path)
    make_skill(tmp_path)
    (tmp_path / "src" / "notes.txt").write_text("x", encoding="utf-8")
    result = run_qa(tmp_path)
    assert ids(result.findings) == ["R3"] and result.warnings and not result.errors


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges on Windows")
def test_r4_symlinked_skill_dir_warns(tmp_path):
    write_hub(tmp_path)
    make_skill(tmp_path)
    (tmp_path / "src" / "linked").symlink_to(tmp_path / "src" / "changelog-formatter")
    assert ids(run_qa(tmp_path).findings) == ["R4"]


def test_broken_hub_still_checks_skills_with_empty_allow_keys(tmp_path):
    write_hub(tmp_path, "hub: []\nqa:\n  allow_keys: [when_to_use]\n")
    make_skill(tmp_path, text=None)
    skill_md_path = tmp_path / "src" / "changelog-formatter" / "SKILL.md"
    skill_md_path.write_text(
        skill_md_path.read_text(encoding="utf-8").replace("---\n\n", "when_to_use: x\n---\n\n", 1),
        encoding="utf-8",
    )
    assert ids(run_qa(tmp_path).findings) == ["H3", "S6"]


@pytest.mark.skipif(sys.platform == "win32" or os.geteuid() == 0, reason="permissions not enforced")
def test_r1_unreadable_src(tmp_path):
    write_hub(tmp_path)
    make_skill(tmp_path)
    src = tmp_path / "src"
    src.chmod(0)
    try:
        assert "R1" in ids(run_qa(tmp_path).findings)
    finally:
        src.chmod(0o755)
