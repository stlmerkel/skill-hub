import codecs
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from skill_hub.config import check_hub
from skill_hub.manifests import MANIFEST_PATHS, ManifestError, check_manifests, render_manifests, write_manifests
from skill_hub.qa import run_qa
from tests.conftest import ids, make_skill, skill_md, sync_manifests, write_hub

SNAPSHOT = Path(__file__).parent / "fixtures" / "default-clone"
DESCRIPTION = "Formats changelog entries. Use when the user asks to write or tidy a changelog."
CLAUDE, CURSOR = MANIFEST_PATHS


def hub(root, *names):
    write_hub(root)
    for name in names:
        make_skill(root, name, skill_md(name))
    return check_hub(root)[1]


def test_exact_shape_sorted_no_version(tmp_path):
    config = hub(tmp_path, "zeta-skill", "alpha-skill")
    rendered = render_manifests(tmp_path, config)
    assert list(rendered) == [CLAUDE, CURSOR]
    assert rendered[CLAUDE] == rendered[CURSOR]
    data = json.loads(rendered[CLAUDE])
    assert list(data) == ["name", "owner", "description", "plugins"]
    assert data == {
        "name": "acme-skills",
        "owner": {"name": "Acme Platform Team"},
        "description": "Skills for Acme engineers.",
        "plugins": [
            {"name": "alpha-skill", "source": "./skills/alpha-skill", "description": DESCRIPTION},
            {"name": "zeta-skill", "source": "./skills/zeta-skill", "description": DESCRIPTION},
        ],
    }
    assert '"version"' not in rendered[CLAUDE] and rendered[CLAUDE].endswith("}\n")


def test_rendering_is_deterministic_and_keeps_non_ascii(tmp_path):
    write_hub(tmp_path)
    accented = "Caf" + chr(0xE9) + " notes. Use when asked."
    make_skill(tmp_path, "notes", skill_md("notes").replace(DESCRIPTION, accented))
    config = check_hub(tmp_path)[1]
    first = render_manifests(tmp_path, config)
    assert first == render_manifests(tmp_path, config)
    assert accented in first[CLAUDE]


def test_write_creates_files_and_leaves_no_temp(tmp_path):
    config = hub(tmp_path, "alpha-skill")
    rendered = render_manifests(tmp_path, config)
    write_manifests(tmp_path, rendered)
    for rel in MANIFEST_PATHS:
        assert (tmp_path / rel).read_text(encoding="utf-8") == rendered[rel]
        assert os.listdir((tmp_path / rel).parent) == ["marketplace.json"]


def test_write_failure_is_a_manifest_error_and_leaves_no_temp(tmp_path, monkeypatch):
    config = hub(tmp_path, "alpha-skill")

    def broken_replace(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", broken_replace)
    with pytest.raises(ManifestError, match=r"^could not write \.claude-plugin/marketplace\.json$"):
        write_manifests(tmp_path, render_manifests(tmp_path, config))
    assert os.listdir(tmp_path / ".claude-plugin") == []


def test_write_lone_surrogate_is_a_manifest_error(tmp_path):
    write_hub(tmp_path)
    escape = "\\" + "ud800"  # built by concatenation so no tool turns it into a character (L72)
    make_skill(tmp_path, "notes", skill_md("notes").replace("Formats", escape + " Formats"))
    with pytest.raises(ManifestError, match=r"^could not write \.claude-plugin/marketplace\.json$"):
        write_manifests(tmp_path, render_manifests(tmp_path, check_hub(tmp_path)[1]))
    assert os.listdir(tmp_path / ".claude-plugin") == []


def test_r7_fresh(tmp_path):
    config = hub(tmp_path, "alpha-skill")
    sync_manifests(tmp_path)
    assert check_manifests(tmp_path, config) == []


def test_r7_missing(tmp_path):
    config = hub(tmp_path, "alpha-skill")
    findings = check_manifests(tmp_path, config)
    assert ids(findings) == ["R7", "R7"]
    assert {f.message for f in findings} == {"not found; run `skill-hub manifests`"}


@pytest.mark.parametrize("change", ["add", "remove", "describe", "hand-edit", "invalid-json"])
def test_r7_out_of_date(tmp_path, change):
    hub(tmp_path, "alpha-skill", "beta-skill")
    sync_manifests(tmp_path)
    if change == "add":
        make_skill(tmp_path, "gamma-skill", skill_md("gamma-skill"))
    elif change == "remove":
        shutil.rmtree(tmp_path / "skills" / "beta-skill")
    elif change == "describe":
        path = tmp_path / "skills" / "beta-skill" / "SKILL.md"
        path.write_text(path.read_text(encoding="utf-8").replace("Formats", "Rewrites"), encoding="utf-8")
    elif change == "hand-edit":
        path = tmp_path / CLAUDE
        path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    else:
        (tmp_path / CLAUDE).write_text("{not json", encoding="utf-8")
    findings = check_manifests(tmp_path, check_hub(tmp_path)[1])
    assert findings and {f.message for f in findings} == {"out of date; run `skill-hub manifests`"}


def test_r7_directory_in_place_of_file(tmp_path):
    config = hub(tmp_path, "alpha-skill")
    sync_manifests(tmp_path)
    (tmp_path / CURSOR).unlink()
    (tmp_path / CURSOR).mkdir()
    (finding,) = check_manifests(tmp_path, config)
    assert finding.path == CURSOR and finding.message == "could not be read; run `skill-hub manifests`"


def test_r7_tolerates_crlf_and_bom(tmp_path):
    config = hub(tmp_path, "alpha-skill")
    sync_manifests(tmp_path)
    for rel in MANIFEST_PATHS:
        path = tmp_path / rel
        path.write_bytes(codecs.BOM_UTF8 + path.read_bytes().replace(b"\n", b"\r\n"))
    assert check_manifests(tmp_path, config) == []


def test_r7_ignores_a_version_bump(tmp_path):
    config = hub(tmp_path, "alpha-skill")
    sync_manifests(tmp_path)
    path = tmp_path / "skills" / "alpha-skill" / "SKILL.md"
    path.write_text(path.read_text(encoding="utf-8").replace('"1.0.0"', '"1.1.0"'), encoding="utf-8")
    assert check_manifests(tmp_path, config) == []


def test_qa_runs_r7(tmp_path):
    hub(tmp_path, "alpha-skill")
    assert ids(run_qa(tmp_path).errors) == ["R7", "R7"]
    sync_manifests(tmp_path)
    assert run_qa(tmp_path).errors == []


def test_qa_skips_r7_when_another_error_exists(tmp_path):
    write_hub(tmp_path)
    make_skill(tmp_path, "foo", skill_md("Foo"))
    assert "R7" not in ids(run_qa(tmp_path).findings)


def test_default_clone_manifests_are_fresh():
    assert check_manifests(SNAPSHOT, check_hub(SNAPSHOT)[1]) == []


@pytest.mark.skipif(shutil.which("claude") is None, reason="the claude CLI is not installed")
def test_claude_plugin_validate_accepts_the_generated_marketplace(tmp_path):
    hub_root = tmp_path / "hub"
    shutil.copytree(SNAPSHOT, hub_root)
    sync_manifests(hub_root)
    proc = subprocess.run(
        ["claude", "plugin", "validate", str(hub_root)], capture_output=True, text=True, timeout=120
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
