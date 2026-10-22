"""Guard the kit-update workflow: triggers, least privilege, token fallback, pins, locked updater, push fallback.

Reads the fixture copy, like tests/test_deploy_workflows.py: a hub without KIT_UPDATE_TOKEN receives this test
before its live workflow (pending workflow files), and tests/test_kit_snapshots.py keeps the fixture equal to the
live file in the kit repo. PyYAML reads the `on:` key as True.
"""

import os
import subprocess
from pathlib import Path

import pytest
import yaml

from tests.kitrepo import git

WORKFLOWS = Path(__file__).parent / "fixtures" / "kit-workflows"
TOKEN = "${{ secrets.KIT_UPDATE_TOKEN || github.token }}"


def load(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def workflow() -> dict:
    return load("kit-update.yml")


def steps() -> list:
    return workflow()["jobs"]["update"]["steps"]


def uses(step_list: list, action: str) -> dict:
    (step,) = [step for step in step_list if step.get("uses", "").startswith(f"{action}@")]
    return step


def script() -> str:
    (step,) = [step for step in steps() if "skill-hub update" in step.get("run", "")]
    return step["run"]


def test_name_and_single_job():
    assert workflow()["name"] == "Kit update"
    assert list(workflow()["jobs"]) == ["update"]


def test_triggers():
    on = workflow()[True]
    assert on["schedule"] == [{"cron": "17 6 * * 1"}]
    major = on["workflow_dispatch"]["inputs"]["major"]
    assert major["type"] == "boolean"
    assert major["default"] is False


def test_never_runs_in_the_kit_repo():
    # The kit repo sets SKILL_HUB_KIT_RELEASES; it has no kit release behind it to update from.
    assert workflow()["jobs"]["update"]["if"] == "vars.SKILL_HUB_KIT_RELEASES != 'true'"


def test_push_leases_against_the_remote_branch():
    run = script()
    assert 'git_auth ls-remote origin "refs/heads/$branch"' in run
    assert '--force-with-lease="refs/heads/$branch:$remote_sha"' in run


def test_token_reaches_only_the_remote_git_calls():
    # The checkout keeps no credentials; the push and ls-remote get the token through env, and the updater
    # (which merges an unreviewed release) runs without GH_TOKEN.
    assert uses(steps(), "actions/checkout")["with"]["persist-credentials"] is False
    run = script()
    assert 'GIT_CONFIG_KEY_0="http.${GITHUB_SERVER_URL}/.extraheader" GIT_CONFIG_VALUE_0="$auth" git "$@"' in run
    code = [line.strip() for line in run.splitlines() if not line.strip().startswith("#")]
    remote_calls = [line for line in code if " push " in line or "ls-remote" in line]
    assert len(remote_calls) == 3
    assert all("git_auth " in line and "git push" not in line for line in remote_calls), remote_calls
    updater_calls = [line for line in run.splitlines() if "uv run --locked skill-hub update" in line]
    assert len(updater_calls) == 2
    assert all("env -u GH_TOKEN uv run" in line for line in updater_calls), updater_calls
    assert "set -x" not in run and "echo \"$auth\"" not in run


def test_job_times_out():
    assert workflow()["jobs"]["update"]["timeout-minutes"] == 15


def test_issue_commands_never_stop_the_run():
    # A hub with Issues disabled still gets minor updates: both issue calls are guarded and only warn.
    run = script()
    assert 'if ! titles="$(gh issue list ' in run
    assert 'if ! gh issue create ' in run
    issue_lines = [line.strip() for line in run.splitlines() if "gh issue " in line]
    assert len(issue_lines) == 2 and all(line.startswith("if ! ") for line in issue_lines), issue_lines
    assert run.count('echo "warning: could not') == 2


def test_permissions_least_privilege():
    assert workflow()["permissions"] == {}
    assert workflow()["jobs"]["update"]["permissions"] == {
        "contents": "write",
        "pull-requests": "write",
        "issues": "write",
    }


def test_concurrency_never_cancels():
    assert workflow()["concurrency"] == {"group": "kit-update", "cancel-in-progress": False}


def test_checkout_and_gh_token_fall_back():
    assert uses(steps(), "actions/checkout")["with"]["token"] == TOKEN
    env = [step for step in steps() if "skill-hub update" in step.get("run", "")][0]["env"]
    assert env["GH_TOKEN"] == TOKEN
    assert env["HAS_TOKEN"] == "${{ secrets.KIT_UPDATE_TOKEN != '' }}"
    assert env["MAJOR"] == "${{ inputs.major || false }}"


def test_pins_match_qa_workflow():
    qa_steps = load("qa.yml")["jobs"]["qa"]["steps"]
    for action in ("actions/checkout", "astral-sh/setup-uv"):
        assert uses(steps(), action)["uses"] == uses(qa_steps, action)["uses"]
    assert uses(steps(), "astral-sh/setup-uv")["with"] == {"python-version": "3.11"}
    assert {step["uses"].split("@")[0] for step in steps() if "uses" in step} == {
        "actions/checkout",
        "astral-sh/setup-uv",
    }


def test_installs_the_hub_lockfile():
    assert any(step.get("run") == "uv sync --locked" for step in steps())


def test_script_uses_env_not_expressions():
    # Same lint as test_no_expression_inside_a_run_script (live files), applied to the fixture.
    for step in steps():
        assert "${{" not in step.get("run", ""), step.get("name", step.get("run"))
    assert script().startswith("set -euo pipefail\n")


def test_update_runs_locked_hub_copy():
    run = script()
    assert "uv run --locked skill-hub update" in run
    for banned in ("uvx", "pip install", "git+"):
        assert banned not in run, banned


def test_script_keeps_the_spec_decisions():
    run = script()
    assert "--check --github-output" in run
    assert 'skill-hub kit ${newer_major}.x is available' in run
    assert "--state all" in run
    assert "kit-update: v${target} available" in run
    assert "--skip-workflows" in run
    assert "--force-with-lease" in run
    assert "--label kit-update" in run
    assert "Allow GitHub Actions to create and approve pull requests" in run


def test_commit_never_runs_hooks():
    # A hook in the hub's .git would run with the token in this step's environment.
    assert "-c core.hooksPath=/dev/null" in script()
    assert "commit --no-verify" in script()


def test_open_update_pr_found_by_branch_or_label():
    # An adopter may remove the label; the kit-update/ branch still marks the PR.
    run = script()
    assert 'startswith("kit-update/")' in run
    assert '.name == "kit-update"' in run


# Behaviour of the script's push fallback, run for real: stub `uv` (the updater) and `gh`, and a local remote whose
# pre-receive hook refuses workflow changes with GitHub's message for a token without the Workflows permission.
FAKE_UV = """#!/bin/bash
# uv run --locked skill-hub update ARGS: record the call, touch README.md and, unless skipped, a workflow file.
[ -z "${GH_TOKEN:-}" ] || exit 9
shift 4
summary="" skip=no check=no
while [ $# -gt 0 ]; do
  case "$1" in --summary-file) summary="$2"; shift ;; --skip-workflows) skip=yes ;; --check) check=yes ;; esac
  shift
done
echo "target=1.2.0" >> "$GITHUB_OUTPUT"
if [ "$check" = yes ]; then echo "newer_major=" >> "$GITHUB_OUTPUT"; exit 0; fi
echo "$skip" >> "$LOG/updates"
echo "kit 1.2.0" >> README.md
if [ "$skip" = no ]; then echo "# kit 1.2.0" >> .github/workflows/qa.yml; fi
echo "body skip=$skip" > "$summary"
"""
FAKE_GH = """#!/bin/bash
case "$*" in
  "pr list --state closed"*) echo 0 ;;
  "pr create"*) while [ $# -gt 0 ]; do [ "$1" = --body-file ] && cp "$2" "$LOG/pr-body.md"; shift; done ;;
esac
"""
REFUSE_WORKFLOWS = """#!/bin/sh
while read old new ref; do
  if git diff --name-only "$new^" "$new" | grep -q '^.github/workflows/'; then
    echo "refusing to allow a Personal Access Token to create or update workflow .github/workflows/qa.yml" >&2
    exit 1
  fi
done
"""
REFUSE_ALL = """#!/bin/sh
echo "pre-receive hook declined" >&2
exit 1
"""
REFUSE_ALL_AS_WORKFLOWS = """#!/bin/sh
echo "refusing to allow a Personal Access Token to create or update workflow .github/workflows/qa.yml" >&2
exit 1
"""


def run_script(tmp_path: Path, has_token: str, hook: str | None) -> tuple[subprocess.CompletedProcess, Path, Path]:
    remote, hub, stubs, log, runner = (tmp_path / name for name in ("remote.git", "hub", "bin", "log", "runner"))
    for folder in (hub / ".github" / "workflows", stubs, log, runner):
        folder.mkdir(parents=True)
    git(tmp_path, "init", "-q", "--bare", str(remote))
    git(hub, "init", "-q", "-b", "main")
    (hub / "README.md").write_text("hub\n")
    (hub / ".github" / "workflows" / "qa.yml").write_text("name: QA\n")
    git(hub, "add", "-A")
    git(hub, "commit", "-q", "-m", "init")
    git(hub, "remote", "add", "origin", str(remote))
    git(hub, "push", "-q", "origin", "main")
    for path, text in ((stubs / "uv", FAKE_UV), (stubs / "gh", FAKE_GH)) + (
        ((remote / "hooks" / "pre-receive", hook),) if hook else ()
    ):
        path.write_text(text)
        path.chmod(0o755)
    (tmp_path / "script.sh").write_text(script())
    env = {
        **os.environ,
        "PATH": f"{stubs}{os.pathsep}{os.environ['PATH']}",
        "GH_TOKEN": "secret",
        "HAS_TOKEN": has_token,
        "MAJOR": "false",
        "RUNNER_TEMP": str(runner),
        "GITHUB_SERVER_URL": "https://github.com",
        "LOG": str(log),
        "GIT_CONFIG_COUNT": "2",
        "GIT_CONFIG_KEY_0": "user.name",
        "GIT_CONFIG_VALUE_0": "Test",
        "GIT_CONFIG_KEY_1": "commit.gpgsign",
        "GIT_CONFIG_VALUE_1": "false",
    }
    done = subprocess.run(["bash", str(tmp_path / "script.sh")], cwd=hub, env=env, capture_output=True, text=True)
    return done, remote, log


def pushed_files(remote: Path) -> list[str]:
    return git(remote, "diff", "--name-only", "main", "kit-update/v1.2.0").splitlines()


def test_token_without_workflows_permission_falls_back_to_pending(tmp_path):
    done, remote, log = run_script(tmp_path, "true", REFUSE_WORKFLOWS)
    assert done.returncode == 0, done.stderr
    assert (log / "updates").read_text().split() == ["no", "yes"]
    assert pushed_files(remote) == ["README.md"]
    body = (log / "pr-body.md").read_text()
    assert body.startswith("body skip=yes\n")
    assert "lacks the Workflows permission" in body
    assert "::warning::KIT_UPDATE_TOKEN lacks the Workflows permission" in done.stdout


def test_token_with_workflows_permission_pushes_workflow_files(tmp_path):
    done, remote, log = run_script(tmp_path, "true", None)
    assert done.returncode == 0, done.stderr
    assert (log / "updates").read_text().split() == ["no"]
    assert pushed_files(remote) == [".github/workflows/qa.yml", "README.md"]
    assert "Workflows permission" not in (log / "pr-body.md").read_text()


@pytest.mark.parametrize(("has_token", "hook"), [("true", REFUSE_ALL), ("false", REFUSE_ALL_AS_WORKFLOWS)])
def test_other_push_failures_never_retry(tmp_path, has_token, hook):
    # Any other refusal, or a workflow refusal when the workflow files were already skipped, fails the run once.
    done, remote, log = run_script(tmp_path, has_token, hook)
    assert done.returncode != 0
    assert len((log / "updates").read_text().split()) == 1
    assert not (log / "pr-body.md").exists()
