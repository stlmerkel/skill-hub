"""Guard the kit-update workflow's shape: triggers, least privilege, token fallback, pins and the locked updater.

Reads the fixture copy, like tests/test_deploy_workflows.py: a hub without KIT_UPDATE_TOKEN receives this test
before its live workflow (pending workflow files), and tests/test_kit_snapshots.py keeps the fixture equal to the
live file in the kit repo. PyYAML reads the `on:` key as True.
"""

from pathlib import Path

import yaml

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
