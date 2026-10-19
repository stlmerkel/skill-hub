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
    assert 'git ls-remote origin "refs/heads/$branch"' in run
    assert '--force-with-lease="refs/heads/$branch:$remote_sha"' in run


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
