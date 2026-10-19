"""`skill-hub update`: kit releases built as git repos in tmp_path, merged into a throwaway hub."""

import sys
from pathlib import Path

import pytest

from skill_hub import update
from skill_hub.kitfile import KitFile, KitFileError, read_kit_file, write_kit_file
from skill_hub.kitgit import KitGitError
from skill_hub.update import UpdateError, format_summary, render_update_outputs, run_update
from tests.conftest import sync_manifests
from tests.kitrepo import commit_files, git, make_hub, make_kit_repo

SNAPSHOT = Path(__file__).parent / "fixtures" / "default-clone"

HUB_A = b"""\
hub:
  name: my-skill-hub
  display_name: My Skill Hub
  owner: Your Team
  description: Skills for our team's coding agents.
  repo_url: https://github.com/you/your-hub

qa:
  allow_keys: []

deploy:
  target: ""
"""
HUB_B = HUB_A + b"""
site:
  accent: ""
"""
HUB_EDITED = HUB_A.replace(b"name: my-skill-hub", b"name: acme-skills").replace(
    b"description: Skills for our team's coding agents.", b"description: Skills for Acme engineers."
)

QA_A = b"""\
name: QA
on:
  pull_request:
jobs:
  qa:
    runs-on: ubuntu-latest
    steps:
      - run: uv sync --locked
      - run: uv run --locked pytest

  deploy-s3:
    needs: qa
    uses: ./.github/workflows/deploy-s3.yml

  deploy-rsync:
    needs: qa
    uses: ./.github/workflows/deploy-rsync.yml
"""
QA_B = QA_A.replace(b"  pull_request:\n", b"  pull_request:\n  push:\n")
QA_C = QA_B.replace(b"uv run --locked pytest", b"uv run --locked pytest -q")
QA_HUB = QA_A.replace(b"\n  deploy-s3:\n    needs: qa\n    uses: ./.github/workflows/deploy-s3.yml\n", b"")

SOURCE_A = b"def greet():\n    return 'hello'\n\n\ndef other():\n    return 1\n"
SOURCE_B = SOURCE_A.replace(b"'hello'", b"'hello from the kit'")
SOURCE_HUB = SOURCE_A.replace(b"'hello'", b"'hello from the hub'")

CHANGELOG_A = b"# Changelog\n\n## [1.0.0](https://example.com/1.0.0) (2026-01-01)\n\n* first release\n"
CHANGELOG_B = (
    b"# Changelog\n\n## [1.1.0](https://example.com/1.1.0) (2026-02-01)\n\n### Features\n\n* site block\n\n"
    + CHANGELOG_A[len(b"# Changelog\n\n"):]
)


def _snapshot(rel: str) -> bytes:
    return (SNAPSHOT / rel).read_bytes()


def kit_a() -> dict[str, bytes | None]:
    return {
        "hub.yml": HUB_A,
        ".github/workflows/qa.yml": QA_A,
        ".github/workflows/deploy-s3.yml": b"on: workflow_call\n",
        ".github/workflows/deploy-rsync.yml": b"on: workflow_call\n",
        "skill_hub/example.py": SOURCE_A,
        "skill_hub/old.py": b"OLD = True\n",
        "CHANGELOG.md": CHANGELOG_A,
        "README.md": b"# skill-hub kit\n",
        "skills/example-skill/SKILL.md": _snapshot("skills/example-skill/SKILL.md"),
        "release-please-config.json": _snapshot("release-please-config.json"),
        ".release-please-manifest.json": _snapshot(".release-please-manifest.json"),
    }


KIT_B = {
    "hub.yml": HUB_B,
    ".github/workflows/qa.yml": QA_B,
    "skill_hub/example.py": SOURCE_B,
    "skill_hub/old.py": None,
    "skill_hub/new.py": b"NEW = True\n",
    "CHANGELOG.md": CHANGELOG_B,
    "README.md": b"# skill-hub kit, now longer\n",
    "skills/example-skill/SKILL.md": b"changed by the kit\n",
    "release-please-config.json": b"{}\n",
    ".release-please-manifest.json": b'{"x": "1"}\n',
}


def hub_files() -> dict[str, bytes]:
    files = {k: v for k, v in kit_a().items() if v is not None}
    files["README.md"] = b"# Acme skills\n"
    files["hub.yml"] = HUB_EDITED
    files[".github/workflows/qa.yml"] = QA_HUB
    del files[".github/workflows/deploy-s3.yml"]
    files["skill_hub/example.py"] = SOURCE_HUB
    return files


def build(tmp_path: Path, releases) -> tuple[str, Path]:
    url = make_kit_repo(tmp_path / "kit", releases)
    hub = make_hub(tmp_path / "hub", url, "1.0.0", hub_files())
    sync_manifests(hub)
    commit_files(hub, {}, "manifests")
    return url, hub


def release(tmp_path: Path, version: str, files: dict[str, bytes | None]) -> None:
    commit_files(tmp_path / "kit", files, f"release {version}")
    git(tmp_path / "kit", "tag", f"kit-v{version}")


def sha(tmp_path: Path, version: str) -> str:
    return git(tmp_path / "kit", "rev-parse", f"kit-v{version}^{{commit}}")


def status(hub: Path) -> str:
    return git(hub, "status", "--porcelain")


def test_update_scenario_keeps_edits(tmp_path):
    _, hub = build(tmp_path, [("1.0.0", kit_a()), ("1.1.0", KIT_B)])
    hub_owned = ["README.md", "skills/example-skill/SKILL.md", "release-please-config.json",
                 ".release-please-manifest.json"]
    before = {rel: (hub / rel).read_bytes() for rel in hub_owned}

    result = run_update(hub)

    hub_yml = (hub / "hub.yml").read_text()
    assert "name: acme-skills" in hub_yml and "description: Skills for Acme engineers." in hub_yml
    assert "site:\n  accent: \"\"" in hub_yml
    qa = (hub / ".github/workflows/qa.yml").read_text()
    assert not (hub / ".github/workflows/deploy-s3.yml").exists()
    assert "deploy-s3" not in qa and "deploy-rsync" in qa
    assert "  push:\n" in qa
    assert (hub / "skill_hub/new.py").read_bytes() == b"NEW = True\n"
    assert not (hub / "skill_hub/old.py").exists()
    conflicts = [o for o in result.outcomes if o.action == "conflict"]
    assert [o.path for o in conflicts] == ["skill_hub/example.py"]
    assert b"<<<<<<< your hub" in (hub / "skill_hub/example.py").read_bytes()
    summary = format_summary(result)
    assert "`skill_hub/example.py`" in summary.split("### Conflicts")[1]
    assert {rel: (hub / rel).read_bytes() for rel in hub_owned} == before
    kit = read_kit_file(hub)
    assert (kit.version, kit.commit) == ("1.1.0", sha(tmp_path, "1.1.0"))
    assert not kit.pending
    assert (result.from_version, result.to_version) == ("1.0.0", "1.1.0")
    assert "site block" in result.changelog and "first release" not in result.changelog
    assert result.manifests_note == ""
    assert result.qa_errors == 0  # the clashing file is kit source, which QA does not read

    (hub / "skill_hub/example.py").write_bytes(SOURCE_HUB)  # resolve the clash
    assert update.run_qa(hub).errors == []


def test_skip_workflows_then_catch_up(tmp_path):
    kit_c = {".github/workflows/qa.yml": QA_C, "CHANGELOG.md": b"# Changelog\n\n## 1.2.0\n\n* pytest -q\n"}
    _, hub = build(tmp_path, [("1.0.0", kit_a()), ("1.1.0", KIT_B)])

    result = run_update(hub, skip_workflows=True)
    assert (hub / ".github/workflows/qa.yml").read_bytes() == QA_HUB
    assert result.pending_workflows == [".github/workflows/qa.yml"]
    kit = read_kit_file(hub)
    assert (kit.version, kit.workflows_version, kit.workflows_commit) == ("1.1.0", "1.0.0", sha(tmp_path, "1.0.0"))
    assert "uv run skill-hub update --workflows-only" in format_summary(result)
    (hub / "skill_hub/example.py").write_bytes(SOURCE_HUB)
    commit_files(hub, {}, "update to 1.1.0")
    release(tmp_path, "1.2.0", kit_c)

    run_update(hub, skip_workflows=True)
    assert (hub / ".github/workflows/qa.yml").read_bytes() == QA_HUB
    kit = read_kit_file(hub)
    assert (kit.version, kit.commit) == ("1.2.0", sha(tmp_path, "1.2.0"))
    assert (kit.workflows_version, kit.workflows_commit) == ("1.0.0", sha(tmp_path, "1.0.0"))
    commit_files(hub, {}, "update to 1.2.0")

    result = run_update(hub, workflows_only=True)
    qa = (hub / ".github/workflows/qa.yml").read_text()
    assert "  push:\n" in qa and "pytest -q" in qa and "deploy-s3" not in qa
    assert [o.path for o in result.outcomes if o.action != "unchanged"] == [".github/workflows/qa.yml"]
    assert all(o.path.startswith(".github/workflows/") for o in result.outcomes)
    kit = read_kit_file(hub)
    assert (kit.version, kit.commit, kit.pending) == ("1.2.0", sha(tmp_path, "1.2.0"), False)


def test_full_update_while_pending_uses_workflow_base(tmp_path):
    kit_c = {".github/workflows/qa.yml": QA_C}
    _, hub = build(tmp_path, [("1.0.0", kit_a()), ("1.1.0", KIT_B)])
    run_update(hub, skip_workflows=True)
    (hub / "skill_hub/example.py").write_bytes(SOURCE_HUB)
    commit_files(hub, {}, "update to 1.1.0")
    release(tmp_path, "1.2.0", kit_c)

    run_update(hub)
    qa = (hub / ".github/workflows/qa.yml").read_text()
    assert "  push:\n" in qa and "pytest -q" in qa and "deploy-s3" not in qa
    assert not read_kit_file(hub).pending


def test_update_refuses_dirty_tree(tmp_path):
    _, hub = build(tmp_path, [("1.0.0", kit_a()), ("1.1.0", KIT_B)])
    (hub / "stray.txt").write_text("x")
    with pytest.raises(KitGitError, match="^the working tree has uncommitted changes; commit or stash them first$"):
        run_update(hub)
    assert status(hub) == "?? stray.txt"
    assert read_kit_file(hub).version == "1.0.0"


def test_update_refuses_non_repo(tmp_path):
    _, hub = build(tmp_path, [("1.0.0", kit_a())])
    plain = tmp_path / "plain"
    (plain / ".skill-hub").mkdir(parents=True)
    (plain / ".skill-hub/kit.yml").write_bytes((hub / ".skill-hub/kit.yml").read_bytes())
    with pytest.raises(KitGitError, match="^this folder is not a git repository$"):
        run_update(plain)
    assert sorted(p.name for p in plain.rglob("*")) == [".skill-hub", "kit.yml"]


def test_update_refuses_missing_kit_file(tmp_path):
    with pytest.raises(KitFileError, match="^kit.yml could not be read$"):
        run_update(tmp_path)


def test_moved_tag_stops_update(tmp_path):
    url, hub = build(tmp_path, [("1.0.0", kit_a()), ("1.1.0", KIT_B)])
    write_kit_file(hub, KitFile(url, "1.0.0", sha(tmp_path, "1.0.0")))
    commit_files(hub, {}, "record the commit")
    commit_files(tmp_path / "kit", {"skill_hub/sneaky.py": b"x\n"}, "moved")
    git(tmp_path / "kit", "tag", "-f", "kit-v1.0.0")

    message = "^the kit release tag this hub is on now points at a different commit than kit.yml records"
    with pytest.raises(UpdateError, match=message):
        run_update(hub)
    assert status(hub) == ""
    with pytest.raises(UpdateError, match=message):
        run_update(hub, check_only=True)


def test_missing_current_tag_stops_update(tmp_path):
    _, hub = build(tmp_path, [("1.0.0", kit_a()), ("1.1.0", KIT_B)])
    git(tmp_path / "kit", "tag", "-d", "kit-v1.0.0")
    with pytest.raises(UpdateError, match="^the kit repo has no release tag for the version in kit.yml"):
        run_update(hub)
    assert status(hub) == ""


def test_up_to_date_writes_nothing(tmp_path):
    _, hub = build(tmp_path, [("1.0.0", kit_a())])
    before = (hub / ".skill-hub/kit.yml").read_bytes()
    result = run_update(hub)
    assert (result.to_version, result.outcomes, result.newer_major) == (None, [], None)
    assert status(hub) == ""
    assert (hub / ".skill-hub/kit.yml").read_bytes() == before
    assert render_update_outputs(result) == "target=\nnewer_major=\nchanged=false\n"
    assert "up to date" in format_summary(result)


def test_hub_yml_conflict_still_completes(tmp_path):
    clash = HUB_B.replace(b"name: my-skill-hub", b"name: kit-name")
    _, hub = build(tmp_path, [("1.0.0", kit_a()), ("1.1.0", {"hub.yml": clash})])
    result = run_update(hub)
    assert [o.path for o in result.outcomes if o.action == "conflict"] == ["hub.yml"]
    assert result.manifests_note.startswith("QA found")
    assert result.qa_errors > 0
    assert read_kit_file(hub).version == "1.1.0"
    summary = format_summary(result)
    assert result.manifests_note in summary and f"QA: {result.qa_errors} error" in summary


def test_workflows_only_without_pending_errors(tmp_path):
    _, hub = build(tmp_path, [("1.0.0", kit_a()), ("1.1.0", KIT_B)])
    with pytest.raises(UpdateError, match="^no workflow files are pending; there is nothing to apply$"):
        run_update(hub, workflows_only=True)
    assert status(hub) == ""


def test_check_only_reports_target_and_newer_major(tmp_path):
    _, hub = build(tmp_path, [("1.0.0", kit_a()), ("1.1.0", KIT_B), ("2.0.0", {"X": b"2"})])
    (hub / "stray.txt").write_text("dirty trees are fine for a check")
    result = run_update(hub, check_only=True)
    assert (result.to_version, result.newer_major, result.outcomes) == ("1.1.0", 2, [])
    assert render_update_outputs(result) == "target=1.1.0\nnewer_major=2\nchanged=true\n"
    assert git(hub, "for-each-ref", "refs/skill-hub") == ""
    assert read_kit_file(hub).version == "1.0.0"

    major = run_update(hub, check_only=True, major=True)
    assert (major.to_version, major.newer_major) == ("2.0.0", None)


def _lock_releases():
    a = kit_a() | {"uv.lock": b"lock A\n", "pyproject.toml": b"[project]\nname = 'kit'\n"}
    return [("1.0.0", a), ("1.1.0", {"uv.lock": b"lock B\n", "pyproject.toml": b"[project]\nname = 'kit2'\n"})]


def _lock_hub(tmp_path, lock: bytes) -> Path:
    _, hub = build(tmp_path, _lock_releases())
    commit_files(hub, {"uv.lock": lock, "pyproject.toml": b"[project]\nname = 'kit'\n"}, "lock")
    return hub


def _outcome(result, path):
    return next(o for o in result.outcomes if o.path == path)


def test_uv_lock_never_builds_source_distributions():
    # Building an sdist runs its code, and the update runs before review with a write token.
    assert update.UV_LOCK == ["uv", "lock", "--no-build"]


def test_uv_lock_unchanged_by_hub_takes_kit(tmp_path, monkeypatch):
    monkeypatch.setattr(update, "UV_LOCK", ["definitely-not-a-command-skill-hub"])
    hub = _lock_hub(tmp_path, b"lock A\n")
    result = run_update(hub)
    assert (hub / "uv.lock").read_bytes() == b"lock B\n"
    assert _outcome(result, "uv.lock").action == "updated"


def test_uv_lock_changed_by_hub_is_regenerated(tmp_path, monkeypatch):
    script = "import pathlib; pathlib.Path('uv.lock').write_text('regenerated\\n')"
    monkeypatch.setattr(update, "UV_LOCK", [sys.executable, "-c", script])
    hub = _lock_hub(tmp_path, b"lock hub\n")
    result = run_update(hub)
    assert (hub / "uv.lock").read_bytes() == b"regenerated\n"
    assert _outcome(result, "uv.lock").action == "updated"


@pytest.mark.parametrize("command", [
    [sys.executable, "-c", "import pathlib, sys; pathlib.Path('uv.lock').write_text('half'); sys.exit(1)"],
    ["definitely-not-a-command-skill-hub"],
])
def test_uv_lock_failure_keeps_hub_copy(tmp_path, monkeypatch, command):
    monkeypatch.setattr(update, "UV_LOCK", command)
    hub = _lock_hub(tmp_path, b"lock hub\n")
    result = run_update(hub)
    assert (hub / "uv.lock").read_bytes() == b"lock hub\n"
    outcome = _outcome(result, "uv.lock")
    assert (outcome.action, outcome.reason) == ("kept", update.LOCK_FAILED)
    assert update.LOCK_FAILED in format_summary(result)


def test_skip_workflows_without_workflow_changes_is_not_pending(tmp_path):
    _, hub = build(tmp_path, [("1.0.0", kit_a()), ("1.1.0", {"skill_hub/new.py": b"NEW = True\n"})])
    result = run_update(hub, skip_workflows=True)
    assert result.pending_workflows == []
    kit = read_kit_file(hub)
    assert (kit.version, kit.pending) == ("1.1.0", False)
    assert "--workflows-only" not in format_summary(result)
    assert not any(f.check_id == "H17" for f in update.run_qa(hub).warnings)
