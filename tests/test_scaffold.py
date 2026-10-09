import os
import sys
from pathlib import Path

import pytest

from skill_hub.contract import NAME_RULE, SCAFFOLD_DESCRIPTION
from skill_hub.qa import run_qa
from skill_hub.scaffold import ScaffoldError, create_skill, render_skill
from tests.conftest import make_skill, write_hub

ALREADY = "src/pdf-tidy already exists; choose another name or remove it"
COULD_NOT_WRITE = "could not write src/pdf-tidy/SKILL.md"


def tree(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


def refuse(root: Path, name: str, message: str) -> None:
    before = tree(root)
    with pytest.raises(ScaffoldError) as caught:
        create_skill(root, name)
    assert str(caught.value) == message
    assert tree(root) == before


# Round trip: the promise of the feature

def test_scaffolded_skill_passes_qa_with_only_s14(tmp_path):
    write_hub(tmp_path)
    make_skill(tmp_path)
    assert create_skill(tmp_path, "pdf-tidy") == "src/pdf-tidy/SKILL.md"
    result = run_qa(tmp_path)
    assert result.errors == []
    assert [(f.check_id, f.path) for f in result.warnings] == [("S14", "src/pdf-tidy/SKILL.md")]
    assert result.skill_count == 2


def test_creates_src_when_missing(tmp_path):
    write_hub(tmp_path)
    create_skill(tmp_path, "pdf-tidy")
    result = run_qa(tmp_path)
    assert result.errors == []
    assert [f.check_id for f in result.warnings] == ["S14"]



@pytest.mark.parametrize("name", ["true", "no", "null", "on", "2024", "017", "0x1f"])
def test_names_yaml_would_read_as_non_strings_still_pass_qa(tmp_path, name):
    write_hub(tmp_path)
    create_skill(tmp_path, name)
    result = run_qa(tmp_path)
    assert result.errors == []
    assert [f.check_id for f in result.warnings] == ["S14"]


# Template

def test_render_fills_name_title_and_placeholder():
    text = render_skill("pdf-tidy")
    assert text.startswith('---\nname: "pdf-tidy"\n')
    assert f'description: "{SCAFFOLD_DESCRIPTION}"\n' in text
    assert '  version: "0.1.0" # x-release-please-version\n' in text
    assert "\n# Pdf Tidy\n" in text
    assert "\n## Steps\n" in text and "\n## Example\n" in text


def test_single_word_title():
    assert "\n# Linter\n" in render_skill("linter")


def test_written_file_has_unix_line_endings(tmp_path):
    write_hub(tmp_path)
    create_skill(tmp_path, "pdf-tidy")
    data = (tmp_path / "src" / "pdf-tidy" / "SKILL.md").read_bytes()
    assert b"\r" not in data
    assert data.decode("utf-8") == render_skill("pdf-tidy")


# Expected failures: message, tree unchanged

@pytest.mark.parametrize("name", ["PDF-tidy", "pdf_tidy", "-pdf", "pdf-", "pdf--tidy", "a" * 65, "", "pdf tidy"])
def test_invalid_name(tmp_path, name):
    write_hub(tmp_path)
    refuse(tmp_path, name, NAME_RULE)


def test_existing_folder(tmp_path):
    write_hub(tmp_path)
    (tmp_path / "src" / "pdf-tidy").mkdir(parents=True)
    refuse(tmp_path, "pdf-tidy", ALREADY)


def test_existing_file(tmp_path):
    write_hub(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "pdf-tidy").write_text("x", encoding="utf-8")
    refuse(tmp_path, "pdf-tidy", ALREADY)


def test_dangling_symlink_at_skill_path(tmp_path):
    write_hub(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "pdf-tidy").symlink_to(tmp_path / "nowhere")
    refuse(tmp_path, "pdf-tidy", ALREADY)


def test_case_insensitive_collision(tmp_path):
    write_hub(tmp_path)
    upper = tmp_path / "src" / "Pdf-Tidy"
    upper.mkdir(parents=True)
    if not (tmp_path / "src" / "pdf-tidy").exists():
        pytest.skip("filesystem is case-sensitive")
    refuse(tmp_path, "pdf-tidy", ALREADY)


def test_root_missing(tmp_path):
    with pytest.raises(ScaffoldError) as caught:
        create_skill(tmp_path / "nope", "pdf-tidy")
    assert str(caught.value) == "--root is not a directory"
    assert not (tmp_path / "nope").exists()


def test_root_is_a_file(tmp_path):
    (tmp_path / "hub").write_text("x", encoding="utf-8")
    with pytest.raises(ScaffoldError) as caught:
        create_skill(tmp_path / "hub", "pdf-tidy")
    assert str(caught.value) == "--root is not a directory"


def test_no_hub_yml(tmp_path):
    refuse(tmp_path, "pdf-tidy", "hub.yml not found; run this from your hub's root or pass --root")


def test_src_is_a_file(tmp_path):
    write_hub(tmp_path)
    (tmp_path / "src").write_text("x", encoding="utf-8")
    refuse(tmp_path, "pdf-tidy", "src is not a directory")


def test_src_is_a_dangling_symlink(tmp_path):
    write_hub(tmp_path)
    (tmp_path / "src").symlink_to(tmp_path / "nowhere")
    refuse(tmp_path, "pdf-tidy", "src is not a directory")


@pytest.mark.skipif(sys.platform == "win32" or os.geteuid() == 0, reason="permissions not enforced")
def test_unwritable_src(tmp_path):
    write_hub(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    src.chmod(0o555)
    try:
        refuse(tmp_path, "pdf-tidy", COULD_NOT_WRITE)
    finally:
        src.chmod(0o755)


def test_failed_write_removes_the_new_folder(tmp_path, monkeypatch):
    write_hub(tmp_path)
    (tmp_path / "src").mkdir()

    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_text", fail)
    with pytest.raises(ScaffoldError) as caught:
        create_skill(tmp_path, "pdf-tidy")
    assert str(caught.value) == COULD_NOT_WRITE
    assert not (tmp_path / "src" / "pdf-tidy").exists()
