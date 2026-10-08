import subprocess
import sys

from skill_hub.cli import main
from tests.conftest import GOOD_HUB, make_skill, skill_md, write_hub

SECRET = "AKIA" + "Q" * 16
LOWER = "sk" + "-" + "a1" * 12  # lowercase, so it is a valid skill name


def test_clean_exit_zero(tmp_path, capsys):
    write_hub(tmp_path)
    make_skill(tmp_path)
    assert main(["qa", "--root", str(tmp_path)]) == 0
    assert capsys.readouterr().out.strip() == "QA: 0 errors, 0 warnings across 1 skill"


def test_warnings_only_exit_zero_unless_strict(tmp_path, capsys):
    write_hub(tmp_path, GOOD_HUB.replace("name: acme-skills", "name: my-skill-hub"))
    make_skill(tmp_path)
    assert main(["qa", "--root", str(tmp_path)]) == 0
    assert main(["qa", "--root", str(tmp_path), "--strict"]) == 1


def test_errors_exit_one_and_report_format(tmp_path, capsys):
    write_hub(tmp_path)
    make_skill(tmp_path, "foo", skill_md("Foo"))
    assert main(["qa", "--root", str(tmp_path)]) == 1
    out = capsys.readouterr().out.splitlines()
    assert out[0] == 'ERROR S4 src/foo/SKILL.md: name must be 1-64 characters of a-z, 0-9 and single hyphens, with no leading or trailing hyphen'
    assert out[-1] == "QA: 1 error, 0 warnings across 1 skill"


def test_report_includes_line_numbers(tmp_path, capsys):
    write_hub(tmp_path)
    make_skill(tmp_path, text=skill_md(extra_frontmatter='version: "1.0.0"\n'))
    main(["qa", "--root", str(tmp_path)])
    assert "src/changelog-formatter/SKILL.md:6:" in capsys.readouterr().out


def test_missing_everything_is_findings_not_traceback(tmp_path, capsys):
    assert main(["qa", "--root", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "ERROR H1 hub.yml" in out and "ERROR R1 src" in out


def test_secret_never_printed(tmp_path):
    write_hub(tmp_path)
    make_skill(tmp_path, "as-name", skill_md(SECRET))  # secret as the name value
    make_skill(tmp_path, "as-mismatched-name", skill_md(LOWER))  # valid name, differs from directory
    make_skill(tmp_path, "as-key", skill_md("as-key", extra_frontmatter=f"{SECRET}: x\n"))
    make_skill(tmp_path, "in-bad-yaml", f"---\nname: [{SECRET}\n---\nbody\n")
    make_skill(tmp_path, "in-body", skill_md("in-body", body=f"\nkey {SECRET}\n"))
    proc = subprocess.run(
        [sys.executable, "-m", "skill_hub.cli", "qa", "--root", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert SECRET not in proc.stdout and SECRET not in proc.stderr
    assert LOWER not in proc.stdout and LOWER not in proc.stderr
    assert "S4" in proc.stdout and "S6" in proc.stdout and "S3" in proc.stdout and "S10" in proc.stdout


def test_one_broken_skill_does_not_hide_another(tmp_path, capsys):
    write_hub(tmp_path)
    make_skill(tmp_path, "aaa-broken", "---\nname: [oops\n---\nbody\n")
    other = make_skill(tmp_path, "zzz-other", skill_md("zzz-other", body="\nkey " + SECRET + "\n"))
    (other / "tool.py").write_text("def broken(:\n", encoding="utf-8")
    assert main(["qa", "--root", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "S3 src/aaa-broken/SKILL.md" in out
    assert "S9 src/zzz-other/tool.py" in out
    assert "S10 src/zzz-other/SKILL.md" in out
