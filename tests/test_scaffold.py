import json
import os
import sys
from pathlib import Path

import pytest

from skill_hub.contract import NAME_RULE, SCAFFOLD_DESCRIPTION
from skill_hub.qa import run_qa
from skill_hub.releases import RELEASE_CONFIG, RELEASE_MANIFEST
from skill_hub.scaffold import ScaffoldError, create_skill, render_skill
from tests.conftest import make_skill, skill_md, write_hub

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
    created = create_skill(tmp_path, "pdf-tidy")
    assert (created.path, created.registered) == ("src/pdf-tidy/SKILL.md", False)
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


KIT_CONFIG = (Path(__file__).parent.parent / RELEASE_CONFIG).read_text(encoding="utf-8")


def release_hub(root: Path, config_text: str = KIT_CONFIG) -> None:
    write_hub(root)
    make_skill(root, "example-skill", skill_md("example-skill", version='"0.1.0"'))  # matches initial-version
    (root / RELEASE_CONFIG).write_text(config_text, encoding="utf-8")
    (root / RELEASE_MANIFEST).write_text("{}\n", encoding="utf-8")


def test_registers_new_skill_last_in_packages(tmp_path):
    release_hub(tmp_path)
    created = create_skill(tmp_path, "pdf-tidy")
    assert created.registered is True
    config = json.loads((tmp_path / RELEASE_CONFIG).read_text(encoding="utf-8"))
    assert list(config["packages"]) == ["src/example-skill", "src/pdf-tidy"]
    assert config["packages"]["src/pdf-tidy"] == {"component": "pdf-tidy", "extra-files": ["SKILL.md"]}
    assert (tmp_path / RELEASE_MANIFEST).read_text(encoding="utf-8") == "{}\n"


def test_registration_keeps_kit_formatting(tmp_path):
    release_hub(tmp_path)
    create_skill(tmp_path, "pdf-tidy")
    expected = KIT_CONFIG.replace(
        '      ]\n    }\n  }\n}\n',
        '      ]\n    },\n    "src/pdf-tidy": {\n      "component": "pdf-tidy",\n'
        '      "extra-files": [\n        "SKILL.md"\n      ]\n    }\n  }\n}\n',
    )
    assert (tmp_path / RELEASE_CONFIG).read_text(encoding="utf-8") == expected


def test_registration_keeps_non_ascii_unescaped(tmp_path):
    release_hub(tmp_path, '{"$comment": "café skills", "packages": {}}\n')
    create_skill(tmp_path, "pdf-tidy")
    text = (tmp_path / RELEASE_CONFIG).read_text(encoding="utf-8")
    assert '"src/pdf-tidy"' in text
    assert '"$comment": "café skills"' in text


@pytest.mark.parametrize("name", ["pdf-tidy", "true", "2024"])
def test_registered_skill_passes_qa_with_only_s14(tmp_path, name):
    release_hub(tmp_path)
    create_skill(tmp_path, name)
    result = run_qa(tmp_path)
    assert result.errors == []
    assert [f.check_id for f in result.warnings] == ["S14"]


@pytest.mark.parametrize("text", ["{not json", "[]", '{"release-type": "simple"}', '{"packages": []}'])
def test_invalid_release_config_refuses(tmp_path, text):
    release_hub(tmp_path, text)
    refuse(tmp_path, "pdf-tidy", "release-please-config.json is not a valid release config; fix it or run skill-hub qa")


@pytest.mark.skipif(sys.platform == "win32" or os.geteuid() == 0, reason="permissions not enforced")
def test_unreadable_release_config_refuses(tmp_path):
    release_hub(tmp_path)
    config = tmp_path / RELEASE_CONFIG
    config.chmod(0)
    try:
        refuse(tmp_path, "pdf-tidy", "could not read release-please-config.json")
    finally:
        config.chmod(0o644)


def test_failed_config_write_rolls_back(tmp_path, monkeypatch):
    release_hub(tmp_path)
    before = tree(tmp_path)
    original = (tmp_path / RELEASE_CONFIG).read_bytes()
    real_write_text = Path.write_text

    def fail_config(self, *args, **kwargs):
        if self.name == RELEASE_CONFIG:
            raise OSError("disk full")
        return real_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_config)
    with pytest.raises(ScaffoldError) as caught:
        create_skill(tmp_path, "pdf-tidy")
    assert str(caught.value) == "could not write release-please-config.json"
    assert tree(tmp_path) == before
    assert (tmp_path / RELEASE_CONFIG).read_bytes() == original
