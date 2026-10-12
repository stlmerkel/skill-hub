import os

from skill_hub.skills import SKILLS_DIR, read_frontmatter, skill_dirs
from tests.conftest import make_skill, skill_md


def test_skills_dir_name():
    assert SKILLS_DIR == "skills"


def test_skill_dirs_sorted_real_directories_only(tmp_path):
    for name in ("zeta", "alpha"):
        make_skill(tmp_path, name, skill_md(name))
    root = tmp_path / SKILLS_DIR
    (root / ".hidden").mkdir()
    (root / "loose.md").write_text("x", encoding="utf-8")
    os.symlink(root / "alpha", root / "linked")
    assert [path.name for path in skill_dirs(tmp_path)] == ["alpha", "zeta"]


def test_read_frontmatter(tmp_path):
    skill_dir = make_skill(tmp_path, "alpha", skill_md("alpha"))
    assert read_frontmatter(skill_dir)["name"] == "alpha"
