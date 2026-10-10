# tests/test_qa_skill.py
import os
import sys
import warnings

import pytest

from skill_hub.contract import SCAFFOLD_DESCRIPTION
from skill_hub.qa import check_skill, run_qa
from tests.conftest import ids, make_skill, skill_md, write_hub

LIVE = "s3cr3t" + "Value99"


def run(tmp_path, text=None, dirname="changelog-formatter", allow=()):
    return check_skill(make_skill(tmp_path, dirname, text), allow)


def test_good_skill_has_no_findings(tmp_path):
    assert run(tmp_path) == []


def test_s1_missing_skill_md(tmp_path):
    skill = tmp_path / "skills" / "empty"
    skill.mkdir(parents=True)
    assert ids(check_skill(skill, ())) == ["S1"]


def test_s1_skill_md_is_directory(tmp_path):
    skill = tmp_path / "skills" / "odd"
    (skill / "SKILL.md").mkdir(parents=True)
    assert ids(check_skill(skill, ())) == ["S1"]


@pytest.mark.parametrize("text", ["# no frontmatter\n", "---\nname: x\n"])
def test_s2_bad_delimiters(tmp_path, text):
    assert ids(run(tmp_path, text)) == ["S2"]


def test_s2_invalid_utf8(tmp_path):
    skill = make_skill(tmp_path)
    (skill / "SKILL.md").write_bytes(b"---\nname: \xff\n---\nbody\n")
    assert ids(check_skill(skill, ())) == ["S2"]


@pytest.mark.parametrize(
    "frontmatter",
    ["name: [unclosed", "- a\n- b", "", "name: a\nname: b", "released: 2026-99-99"],
)
def test_s3_bad_frontmatter_skips_field_checks(tmp_path, frontmatter):
    assert ids(run(tmp_path, f"---\n{frontmatter}\n---\nbody\n")) == ["S3"]


def test_s3_line_is_a_file_line(tmp_path):
    (finding,) = run(tmp_path, "---\nname: ok\nname: dup\n---\nbody\n")
    assert finding.line == 3


@pytest.mark.parametrize(
    ("name", "dirname"),
    [("Changelog", "changelog"), ("other-name", "changelog"), ("a" * 65, "a" * 65), ("on", "on")],
)
def test_s4_name(tmp_path, name, dirname):
    assert ids(run(tmp_path, skill_md(name), dirname)) == ["S4"]


def test_s4_64_char_name_passes(tmp_path):
    assert run(tmp_path, skill_md("a" * 64), "a" * 64) == []


def test_s4_missing_name(tmp_path):
    text = skill_md().replace("name: changelog-formatter\n", "")
    assert ids(run(tmp_path, text)) == ["S4"]


@pytest.mark.parametrize(("length", "expected"), [(1024, []), (1025, ["S5"])])
def test_s5_description_length(tmp_path, length, expected):
    text = skill_md().replace(
        'description: "Formats changelog entries. Use when the user asks to write or tidy a changelog."',
        f'description: "{"d" * length}"',
    )
    assert ids(run(tmp_path, text)) == expected


@pytest.mark.parametrize("value", ['"   "', "", "42"])
def test_s5_bad_description(tmp_path, value):
    text = skill_md().replace(
        'description: "Formats changelog entries. Use when the user asks to write or tidy a changelog."',
        f"description: {value}",
    )
    assert ids(run(tmp_path, text)) == ["S5"]


def test_s6_top_level_version_has_move_hint(tmp_path):
    findings = run(tmp_path, skill_md(extra_frontmatter='version: "1.0.0"\n'))
    assert ids(findings) == ["S6"]
    assert "metadata.version" in findings[0].message
    assert findings[0].line == 6


def test_s6_unknown_key_not_echoed(tmp_path):
    findings = run(tmp_path, skill_md(extra_frontmatter="when_to_use: later\n"))
    assert ids(findings) == ["S6"] and "when_to_use" not in findings[0].message


def test_s6_allow_keys(tmp_path):
    assert run(tmp_path, skill_md(extra_frontmatter="when_to_use: later\n"), allow=("when_to_use",)) == []


@pytest.mark.parametrize("version", ["1.0", "1", '"1.0"', '"01.0.0"', "null"])
def test_s7_bad_version(tmp_path, version):
    assert ids(run(tmp_path, skill_md(version=version))) == ["S7"]


def test_s7_unquoted_version_gets_quote_hint(tmp_path):
    (finding,) = run(tmp_path, skill_md(version="1.0"))
    assert "number" in finding.message and "quote" in finding.message


def test_s7_missing_metadata(tmp_path):
    text = skill_md().replace('metadata:\n  version: "1.0.0"\n', "")
    assert ids(run(tmp_path, text)) == ["S7"]


def test_s7_and_s8_when_metadata_not_mapping(tmp_path):
    text = skill_md().replace('metadata:\n  version: "1.0.0"\n', "metadata: [a]\n")
    assert ids(run(tmp_path, text)) == ["S7", "S8"]


@pytest.mark.parametrize(
    "extra",
    [
        "  author: 42\n",  # inside metadata: non-string value
        "  released: 2026-01-01\n",
    ],
)
def test_s8_metadata_values(tmp_path, extra):
    text = skill_md().replace('  version: "1.0.0"\n', f'  version: "1.0.0"\n{extra}')
    assert ids(run(tmp_path, text)) == ["S8"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [('""', ["S8"]), ('"c"', []), (f'"{"c" * 500}"', []), (f'"{"c" * 501}"', ["S8"]), ('"  "', ["S8"])],
)
def test_s8_compatibility(tmp_path, value, expected):
    assert ids(run(tmp_path, skill_md(extra_frontmatter=f"compatibility: {value}\n"))) == expected


@pytest.mark.parametrize("extra", ["license: 2\n", "allowed-tools: [Read]\n"])
def test_s8_string_fields(tmp_path, extra):
    findings = run(tmp_path, skill_md(extra_frontmatter=extra))
    assert ids(findings) == ["S8"] and "quote" in findings[0].message


def test_s9_python_must_compile(tmp_path):
    skill = make_skill(tmp_path)
    (skill / "scripts").mkdir()
    (skill / "scripts" / "bad.py").write_text("def broken(:\n", encoding="utf-8")
    (skill / "scripts" / "good.py").write_text("print('ok')\n", encoding="utf-8")
    findings = check_skill(skill, ())
    assert ids(findings) == ["S9"] and findings[0].path.endswith("scripts/bad.py")


def test_s10_secret_in_body_and_in_reference_file(tmp_path):
    skill = make_skill(tmp_path, text=skill_md(body=f"\nUse password = '{LIVE}'\n"))
    (skill / "references").mkdir()
    (skill / "references" / "notes.md").write_text(f"api_key: \"{LIVE}\"\n", encoding="utf-8")
    findings = check_skill(skill, ())
    assert ids(findings) == ["S10", "S10"]
    assert all(LIVE not in f.message for f in findings)


def test_s10_large_binary_warns(tmp_path):
    skill = make_skill(tmp_path)
    (skill / "assets").mkdir()
    (skill / "assets" / "blob.bin").write_bytes(b"\xff" * 1_000_001)
    findings = check_skill(skill, ())
    assert ids(findings) == ["S10"] and findings[0].level == "warning"


def test_s11_empty_body_warns(tmp_path):
    findings = run(tmp_path, skill_md(body="\n  \n"))
    assert ids(findings) == ["S11"] and findings[0].level == "warning"


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges on Windows")
def test_s12_symlink_not_followed(tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_text(f"password = '{LIVE}'\n", encoding="utf-8")
    skill = make_skill(tmp_path)
    (skill / "link.md").symlink_to(outside)
    findings = check_skill(skill, ())
    assert ids(findings) == ["S12"] and findings[0].level == "warning"


@pytest.mark.skipif(sys.platform == "win32" or os.geteuid() == 0, reason="permissions not enforced")
def test_s13_unreadable_file(tmp_path):
    skill = make_skill(tmp_path)
    locked = skill / "locked.md"
    locked.write_text("x", encoding="utf-8")
    locked.chmod(0)
    try:
        assert ids(check_skill(skill, ())) == ["S13"]
    finally:
        locked.chmod(0o644)


def test_hidden_files_and_dirs_inside_a_skill_are_scanned(tmp_path):
    skill = make_skill(tmp_path)
    (skill / ".env").write_text(f"API_KEY={LIVE}xyz12\n", encoding="utf-8")
    (skill / ".secrets").mkdir()
    (skill / ".secrets" / "x.txt").write_text(f"password = '{LIVE}'\n", encoding="utf-8")
    findings = check_skill(skill, ())
    assert ids(findings) == ["S10", "S10"]
    assert sorted(f.path for f in findings) == [
        "skills/changelog-formatter/.env",
        "skills/changelog-formatter/.secrets/x.txt",
    ]
    assert all(LIVE not in f.message for f in findings)


def test_bom_crlf_skill_passes(tmp_path):
    skill = make_skill(tmp_path)
    text = "\ufeff" + skill_md().replace("\n", "\r\n")
    (skill / "SKILL.md").write_bytes(text.encode("utf-8"))
    assert check_skill(skill, ()) == []


@pytest.mark.skipif(sys.platform == "win32" or os.geteuid() == 0, reason="permissions not enforced")
def test_s13_unreadable_subdirectory_fails_closed(tmp_path):
    skill = make_skill(tmp_path)
    locked = skill / "references"
    locked.mkdir()
    (locked / "notes.md").write_text(f"password = '{LIVE}'\n", encoding="utf-8")
    locked.chmod(0)
    try:
        assert ids(check_skill(skill, ())) == ["S13"]
    finally:
        locked.chmod(0o755)


def test_s9_compile_warning_does_not_echo_source(tmp_path):
    skill = make_skill(tmp_path)
    (skill / "scripts").mkdir()
    (skill / "scripts" / "esc.py").write_text('x = "\\d MARKERTEXT"\n', encoding="utf-8")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert check_skill(skill, ()) == []
    assert caught == []


@pytest.mark.parametrize("source", ["x = " + "-" * 200000 + "1\n", "(" * 100000 + ")" * 100000 + "\n"])
def test_s9_pathological_source_is_a_finding(tmp_path, source):
    skill = make_skill(tmp_path)
    (skill / "scripts").mkdir()
    (skill / "scripts" / "deep.py").write_text(source, encoding="utf-8")
    assert ids(check_skill(skill, ())) == ["S9"]


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges on Windows")
def test_s12_symlinked_directory(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "x.md").write_text(f"password = '{LIVE}'\n", encoding="utf-8")
    skill = make_skill(tmp_path)
    (skill / "linkdir").symlink_to(outside, target_is_directory=True)
    assert ids(check_skill(skill, ())) == ["S12"]


@pytest.mark.skipif(sys.platform == "win32" or os.geteuid() == 0, reason="permissions not enforced")
@pytest.mark.parametrize("mode", [0o000, 0o644])
def test_s13_unreadable_skill_directory_is_one_finding(tmp_path, mode):
    skill = make_skill(tmp_path)
    (skill / "notes.md").write_text("x", encoding="utf-8")
    skill.chmod(mode)
    try:
        findings = check_skill(skill, ())
    finally:
        skill.chmod(0o755)
    assert [(f.level, f.check_id, f.path, f.message) for f in findings] == [
        ("error", "S13", "skills/changelog-formatter", "directory could not be read")
    ]


@pytest.mark.skipif(sys.platform == "win32", reason="mkfifo unavailable on Windows")
def test_non_regular_file_is_skipped_with_warning(tmp_path):
    skill = make_skill(tmp_path)
    os.mkfifo(skill / "pipe")
    findings = check_skill(skill, ())
    assert [(f.level, f.check_id, f.path, f.message) for f in findings] == [
        ("warning", "S12", "skills/changelog-formatter/pipe", "not a regular file; not scanned")
    ]


def _placeholder_skill(description_yaml: str) -> str:
    return skill_md("changelog-formatter").replace(
        'description: "Formats changelog entries. Use when the user asks to write or tidy a changelog."',
        f"description: {description_yaml}",
    )


def test_scaffold_placeholder_description_is_s14_warning(tmp_path):
    write_hub(tmp_path)
    make_skill(tmp_path, text=_placeholder_skill(f'"{SCAFFOLD_DESCRIPTION}"'))
    result = run_qa(tmp_path)
    assert result.errors == []
    assert [(f.check_id, f.path) for f in result.warnings] == [("S14", "skills/changelog-formatter/SKILL.md")]


def test_s14_ignores_surrounding_whitespace(tmp_path):
    write_hub(tmp_path)
    make_skill(tmp_path, text=_placeholder_skill(f'"  {SCAFFOLD_DESCRIPTION} "'))
    assert ids(run_qa(tmp_path).warnings) == ["S14"]


def test_real_description_has_no_s14(tmp_path):
    write_hub(tmp_path)
    make_skill(tmp_path)
    assert "S14" not in ids(run_qa(tmp_path).findings)


def test_description_mentioning_todo_has_no_s14(tmp_path):
    write_hub(tmp_path)
    make_skill(tmp_path, text=_placeholder_skill('"TODO list manager. Use when the user asks to track tasks."'))
    assert "S14" not in ids(run_qa(tmp_path).findings)
