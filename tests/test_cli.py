import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from skill_hub.cli import main
from skill_hub.findings import WARNING, Finding
from skill_hub.manifests import MANIFEST_PATHS, ManifestError
from skill_hub.qa import QaResult, run_qa
from tests.conftest import (
    GOOD_HUB,
    RSYNC_DEPLOY,
    S3_DEPLOY,
    make_deploy_workflow,
    make_skill,
    skill_md,
    sync_manifests,
    write_hub,
)

SECRET = "AKIA" + "Q" * 16
LOWER = "sk" + "-" + "a1" * 12  # lowercase, so it is a valid skill name


def test_clean_exit_zero(tmp_path, capsys):
    write_hub(tmp_path)
    make_skill(tmp_path)
    sync_manifests(tmp_path)
    assert main(["qa", "--root", str(tmp_path)]) == 0
    assert capsys.readouterr().out.strip() == "QA: 0 errors, 0 warnings across 1 skill"


def test_warnings_only_exit_zero_unless_strict(tmp_path, capsys):
    write_hub(tmp_path, GOOD_HUB.replace("name: acme-skills", "name: my-skill-hub"))
    make_skill(tmp_path)
    sync_manifests(tmp_path)
    assert main(["qa", "--root", str(tmp_path)]) == 0
    assert main(["qa", "--root", str(tmp_path), "--strict"]) == 1


def test_errors_exit_one_and_report_format(tmp_path, capsys):
    write_hub(tmp_path)
    make_skill(tmp_path, "foo", skill_md("Foo"))
    assert main(["qa", "--root", str(tmp_path)]) == 1
    out = capsys.readouterr().out.splitlines()
    assert out[0] == (
        "ERROR S4 skills/foo/SKILL.md: name must be 1-64 characters of a-z, 0-9 and single hyphens, "
        "with no leading or trailing hyphen"
    )
    assert out[-1] == "QA: 1 error, 0 warnings across 1 skill"


def test_report_includes_line_numbers(tmp_path, capsys):
    write_hub(tmp_path)
    make_skill(tmp_path, text=skill_md(extra_frontmatter='version: "1.0.0"\n'))
    main(["qa", "--root", str(tmp_path)])
    assert "skills/changelog-formatter/SKILL.md:6:" in capsys.readouterr().out


def test_missing_everything_is_findings_not_traceback(tmp_path, capsys):
    assert main(["qa", "--root", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "ERROR H1 hub.yml" in out and "ERROR R1 skills" in out


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
    assert "S3 skills/aaa-broken/SKILL.md" in out
    assert "S9 skills/zzz-other/tool.py" in out
    assert "S10 skills/zzz-other/SKILL.md" in out


def test_non_utf8_filename_does_not_crash_output(tmp_path, capsys, monkeypatch):
    bad = QaResult([Finding(WARNING, "S12", "skills/x/bad\udcff.txt", "not a regular file; not scanned")], 1)
    monkeypatch.setattr("skill_hub.cli.run_qa", lambda root: bad)
    assert main(["qa", "--root", str(tmp_path)]) == 0
    assert "skills/x/bad\\udcff.txt" in capsys.readouterr().out


def test_new_skill_creates_and_reports(tmp_path, capsys):
    write_hub(tmp_path)
    assert main(["new-skill", "pdf-tidy", "--root", str(tmp_path)]) == 0
    out = capsys.readouterr()
    assert out.out.splitlines() == [
        "Created skills/pdf-tidy/SKILL.md",
        "Release registration skipped: no release-please-config.json",
        "Next: replace the placeholder description and instructions, then run `uv run skill-hub qa`.",
        "Updated the marketplace manifests",
    ]
    assert out.err == ""
    assert (tmp_path / "skills" / "pdf-tidy" / "SKILL.md").is_file()


def test_new_skill_refusal_exits_one_on_stderr(tmp_path, capsys):
    write_hub(tmp_path)
    assert main(["new-skill", "Bad_Name", "--root", str(tmp_path)]) == 1
    out = capsys.readouterr()
    assert out.out == ""
    assert out.err == (
        "error: name must be 1-64 characters of a-z, 0-9 and single hyphens, "
        "with no leading or trailing hyphen\n"
    )


def test_new_skill_then_qa_passes(tmp_path, capsys):
    write_hub(tmp_path)
    main(["new-skill", "pdf-tidy", "--root", str(tmp_path)])
    sync_manifests(tmp_path)
    assert main(["qa", "--root", str(tmp_path)]) == 0
    assert main(["qa", "--root", str(tmp_path), "--strict"]) == 1


def test_new_skill_listed_in_help():
    result = subprocess.run(
        [sys.executable, "-m", "skill_hub.cli", "--help"], capture_output=True, text=True, check=True
    )
    assert "new-skill" in result.stdout


def test_new_skill_failure_has_no_traceback(tmp_path):
    (tmp_path / "hub.yml").write_text("x", encoding="utf-8")
    (tmp_path / "skills").write_text("x", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "skill_hub.cli", "new-skill", "pdf-tidy", "--root", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert result.stderr == "error: skills is not a directory\n"


def test_new_skill_registered_has_no_skip_line(tmp_path, capsys):
    write_hub(tmp_path)
    (tmp_path / "release-please-config.json").write_text(json.dumps({"packages": {}}), encoding="utf-8")
    (tmp_path / ".release-please-manifest.json").write_text("{}", encoding="utf-8")
    assert main(["new-skill", "pdf-tidy", "--root", str(tmp_path)]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "Created skills/pdf-tidy/SKILL.md",
        "Next: replace the placeholder description and instructions, then run `uv run skill-hub qa`.",
        "Updated the marketplace manifests",
    ]
    config = json.loads((tmp_path / "release-please-config.json").read_text(encoding="utf-8"))
    assert "skills/pdf-tidy" in config["packages"]


FIXTURE = Path(__file__).parent / "fixtures" / "default-clone"


def test_build_exit_zero_and_summary(tmp_path, capsys):
    out = tmp_path / "out"
    assert main(["build", "--root", str(FIXTURE), "--out", str(out)]) == 0
    assert capsys.readouterr().out.strip() == f"Built the marketplace page for 1 skill in {out}"
    assert (out / "index.html").is_file()


def test_build_error_exit_one_on_stderr(tmp_path, capsys):
    write_hub(tmp_path)
    make_skill(tmp_path, "foo", skill_md("Foo"))
    assert main(["build", "--root", str(tmp_path), "--out", str(tmp_path / "out")]) == 1
    captured = capsys.readouterr()
    assert captured.err.startswith("error: QA found 1 error") and captured.out == ""


def test_build_prints_theme_warnings(tmp_path, capsys):
    write_hub(tmp_path, GOOD_HUB + 'site:\n  theme: "theme"\n')
    make_skill(tmp_path)
    theme = tmp_path / "theme"
    theme.mkdir()
    (theme / "index.html.j2").write_text("x", encoding="utf-8")
    (tmp_path / "real.css").write_text("x", encoding="utf-8")
    os.symlink(tmp_path / "real.css", theme / "linked.css")
    sync_manifests(tmp_path)
    assert main(["build", "--root", str(tmp_path), "--out", str(tmp_path / "out")]) == 0
    assert capsys.readouterr().out.splitlines()[0] == "warning: theme/linked.css: symlink in theme is not followed"


def test_manifests_command_writes_both_and_qa_passes(tmp_path, capsys):
    write_hub(tmp_path)
    make_skill(tmp_path)
    assert main(["manifests", "--root", str(tmp_path)]) == 0
    assert capsys.readouterr().out.strip() == (
        "Wrote .claude-plugin/marketplace.json and .cursor-plugin/marketplace.json for 1 skill"
    )
    assert all((tmp_path / rel).is_file() for rel in MANIFEST_PATHS)
    assert run_qa(tmp_path).errors == []


def test_manifests_command_refuses_on_other_qa_errors(tmp_path, capsys):
    write_hub(tmp_path)
    make_skill(tmp_path, "foo", skill_md("Foo"))
    assert main(["manifests", "--root", str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert captured.err.startswith("error: QA found 1 error") and captured.out == ""
    assert not (tmp_path / MANIFEST_PATHS[0]).exists()


def test_manifests_command_reports_a_write_failure(tmp_path, capsys, monkeypatch):
    write_hub(tmp_path)
    make_skill(tmp_path)

    def broken(root, rendered):
        raise ManifestError("could not write .claude-plugin/marketplace.json")

    monkeypatch.setattr("skill_hub.manifests.write_manifests", broken)
    assert main(["manifests", "--root", str(tmp_path)]) == 1
    assert capsys.readouterr().err.strip() == "error: could not write .claude-plugin/marketplace.json"


def test_new_skill_refreshes_manifests(tmp_path, capsys):
    write_hub(tmp_path)
    make_skill(tmp_path)
    sync_manifests(tmp_path)
    assert main(["new-skill", "pdf-tidy", "--root", str(tmp_path)]) == 0
    assert capsys.readouterr().out.splitlines()[-1] == "Updated the marketplace manifests"
    assert '"pdf-tidy"' in (tmp_path / MANIFEST_PATHS[0]).read_text(encoding="utf-8")
    assert run_qa(tmp_path).errors == []


def test_new_skill_with_other_qa_errors_creates_and_hints(tmp_path, capsys):
    write_hub(tmp_path)
    make_skill(tmp_path, "foo", skill_md("Foo"))
    assert main(["new-skill", "pdf-tidy", "--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[-1] == "Manifests not updated: fix the QA errors, then run `skill-hub manifests`"
    assert (tmp_path / "skills" / "pdf-tidy" / "SKILL.md").is_file()
    assert not (tmp_path / MANIFEST_PATHS[0]).exists()


S3_OUTPUT = "target=s3\ns3_bucket=acme-skills\ns3_region=us-east-1\n"


def test_deploy_config_prints_the_outputs(tmp_path, capsys):
    write_hub(tmp_path, GOOD_HUB + S3_DEPLOY)
    make_deploy_workflow(tmp_path, "s3")
    assert main(["deploy-config", "--root", str(tmp_path)]) == 0
    assert capsys.readouterr().out == S3_OUTPUT


def test_deploy_config_appends_to_github_output(tmp_path, monkeypatch, capsys):
    write_hub(tmp_path, GOOD_HUB + S3_DEPLOY)
    make_deploy_workflow(tmp_path, "s3")
    output = tmp_path / "github-output"
    output.write_text("earlier=1\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    assert main(["deploy-config", "--root", str(tmp_path), "--github-output"]) == 0
    assert output.read_text(encoding="utf-8") == "earlier=1\n" + S3_OUTPUT
    assert capsys.readouterr().out == "Deploy target: s3\n"


def test_deploy_config_without_a_target(tmp_path, monkeypatch, capsys):
    write_hub(tmp_path)
    output = tmp_path / "github-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    assert main(["deploy-config", "--root", str(tmp_path), "--github-output"]) == 0
    assert output.read_text(encoding="utf-8") == "target=\n"
    assert capsys.readouterr().out == "No deploy target set; the deploy jobs will be skipped\n"


def test_deploy_config_refuses_an_invalid_hub(tmp_path, monkeypatch, capsys):
    write_hub(tmp_path, GOOD_HUB + RSYNC_DEPLOY.replace("path: /var/www/skills", "path: '/var/www;id'"))
    make_deploy_workflow(tmp_path, "rsync")
    output = tmp_path / "github-output"
    output.write_text("earlier=1\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    assert main(["deploy-config", "--root", str(tmp_path), "--github-output"]) == 1
    assert output.read_text(encoding="utf-8") == "earlier=1\n"
    captured = capsys.readouterr()
    assert captured.out == "" and ";id" not in captured.err
    assert "skill-hub qa" in captured.err


def test_deploy_config_needs_github_output_set(tmp_path, monkeypatch, capsys):
    write_hub(tmp_path)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    assert main(["deploy-config", "--root", str(tmp_path), "--github-output"]) == 1
    assert "GITHUB_OUTPUT" in capsys.readouterr().err


def _update_hub(tmp_path):
    from tests.test_update import KIT_B, build, kit_a

    return build(tmp_path, [("1.0.0", kit_a()), ("1.1.0", KIT_B)])[1]


def test_update_cli_github_output(tmp_path, monkeypatch, capsys):
    hub = _update_hub(tmp_path)
    output = tmp_path / "github-output"
    output.write_text("earlier=1\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    assert main(["update", "--root", str(hub), "--check", "--github-output"]) == 0
    assert output.read_text(encoding="utf-8") == "earlier=1\ntarget=1.1.0\nnewer_major=\nchanged=true\n"
    assert "1.0.0 → 1.1.0" in capsys.readouterr().out
    assert (hub / "hub.yml").read_text().count("site:") == 0  # --check writes nothing


def test_update_cli_github_output_needs_the_variable(tmp_path, monkeypatch, capsys):
    hub = _update_hub(tmp_path)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    assert main(["update", "--root", str(hub), "--github-output"]) == 1
    assert "GITHUB_OUTPUT" in capsys.readouterr().err
    assert "site:" not in (hub / "hub.yml").read_text()


def test_update_cli_summary_file(tmp_path, capsys):
    hub = _update_hub(tmp_path)
    summary = tmp_path / "summary.md"
    assert main(["update", "--root", str(hub), "--summary-file", str(summary)]) == 0
    text = summary.read_text(encoding="utf-8")
    assert text.startswith("## Kit update: 1.0.0 → 1.1.0")
    assert "`skill_hub/example.py`" in text
    assert "site:" in (hub / "hub.yml").read_text()


def test_update_cli_error_exit(tmp_path, capsys):
    hub = _update_hub(tmp_path)
    (hub / "stray.txt").write_text("x")
    assert main(["update", "--root", str(hub)]) == 1
    captured = capsys.readouterr()
    assert captured.err == "error: the working tree has uncommitted changes; commit or stash them first\n"
    assert "Traceback" not in captured.out + captured.err
    assert main(["update", "--root", str(tmp_path / "nowhere")]) == 1
    assert capsys.readouterr().err == "error: kit.yml could not be read\n"


def test_update_cli_flag_conflicts(tmp_path, capsys):
    for flag in ("--major", "--skip-workflows", "--check"):
        with pytest.raises(SystemExit) as exit_info:
            main(["update", "--root", str(tmp_path), "--workflows-only", flag])
        assert exit_info.value.code == 2
        assert "--workflows-only cannot be combined with" in capsys.readouterr().err


def test_update_cli_summary_file_write_failure(tmp_path, monkeypatch, capsys):
    hub = _update_hub(tmp_path)
    output = tmp_path / "github-output"
    output.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    summary = tmp_path / "missing-folder" / "summary.md"
    assert main(["update", "--root", str(hub), "--summary-file", str(summary), "--github-output"]) == 1
    captured = capsys.readouterr()
    assert captured.err == "error: could not write the summary file\n"
    assert "Traceback" not in captured.out + captured.err
    assert output.read_text(encoding="utf-8") == ""
