"""Guard the deploy workflows and their caller jobs in qa.yml.

PyYAML reads YAML 1.1, where the `on:` key parses as True, so the trigger is read as `workflow[True]`.
"""

from pathlib import Path

import pytest
import yaml

from skill_hub.contract import DEPLOY_TARGET_SETTINGS

REPO = Path(__file__).parent.parent
WORKFLOWS = REPO / ".github" / "workflows"
TARGETS = tuple(DEPLOY_TARGET_SETTINGS)
SECRETS = {
    "github-pages": (),
    "s3": ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"),
    "rsync": ("DEPLOY_SSH_KEY", "DEPLOY_SSH_KNOWN_HOSTS"),
}
PERMISSIONS = {"github-pages": {"pages": "write", "id-token": "write"}, "s3": {}, "rsync": {}}
PINS = {"actions/download-artifact": "v8", "actions/upload-pages-artifact": "v5", "actions/deploy-pages": "v5"}


def load(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def caller(target: str) -> dict:
    return load("qa.yml")["jobs"][f"deploy-{target}"]


def called(target: str) -> dict:
    return load(f"deploy-{target}.yml")


def call_spec(target: str) -> dict:
    return called(target)[True]["workflow_call"] or {}


def deploy_job(target: str) -> dict:
    return called(target)["jobs"]["deploy"]


def secret_refs(names) -> dict:
    return {name: f"${{{{ secrets.{name} }}}}" for name in names}


@pytest.mark.parametrize("target", TARGETS)
def test_caller_runs_only_for_its_target(target):
    job = caller(target)
    assert job["needs"] == "build"
    assert job["if"] == f"needs.build.outputs.target == '{target}'"
    assert job["uses"] == f"./.github/workflows/deploy-{target}.yml"


@pytest.mark.parametrize("target", TARGETS)
def test_caller_grants_only_its_targets_permissions(target):
    assert caller(target)["permissions"] == PERMISSIONS[target]


@pytest.mark.parametrize("target", TARGETS)
def test_caller_passes_only_its_secrets_by_name(target):
    assert caller(target).get("secrets", {}) == secret_refs(SECRETS[target])


@pytest.mark.parametrize("target", TARGETS)
def test_caller_passes_the_build_outputs_as_inputs(target):
    keys = DEPLOY_TARGET_SETTINGS[target]
    assert caller(target).get("with", {}) == {key: f"${{{{ needs.build.outputs.{target}_{key} }}}}" for key in keys}
    assert set(call_spec(target).get("inputs") or {}) == set(keys)


def test_build_job_exposes_every_deploy_output():
    outputs = load("qa.yml")["jobs"]["build"]["outputs"]
    names = {"target", *(f"{target}_{key}" for target, keys in DEPLOY_TARGET_SETTINGS.items() for key in keys)}
    assert outputs == {name: f"${{{{ steps.deploy.outputs.{name} }}}}" for name in names}


def test_every_called_workflow_exists():
    for name, job in load("qa.yml")["jobs"].items():
        if "uses" in job:
            assert (REPO / job["uses"]).is_file(), name


@pytest.mark.parametrize("target", TARGETS)
def test_called_workflow_runs_only_when_called(target):
    assert set(called(target)[True]) == {"workflow_call"}


@pytest.mark.parametrize("target", TARGETS)
def test_called_workflow_requires_its_secrets(target):
    assert (call_spec(target).get("secrets") or {}) == {name: {"required": True} for name in SECRETS[target]}


@pytest.mark.parametrize("target", TARGETS)
def test_deploy_job_permissions_and_concurrency(target):
    job = deploy_job(target)
    assert job["permissions"] == PERMISSIONS[target]
    assert job["concurrency"] == {"group": "deploy", "cancel-in-progress": False}


@pytest.mark.parametrize("target", TARGETS)
def test_deploys_the_build_artifact(target):
    (download,) = [step for step in deploy_job(target)["steps"] if "download-artifact" in step.get("uses", "")]
    assert download["with"] == {"name": "marketplace-page", "path": "site/"}


@pytest.mark.parametrize("target", TARGETS)
def test_actions_are_pinned(target):
    for step in deploy_job(target)["steps"]:
        if "uses" in step:
            action, ref = step["uses"].split("@")
            assert PINS[action] == ref, step["uses"]


@pytest.mark.parametrize("target", [target for target in TARGETS if SECRETS[target]])
def test_checks_secrets_are_set_before_anything_else(target):
    first = deploy_job(target)["steps"][0]
    assert first["env"] == secret_refs(SECRETS[target])
    assert all(name in first["run"] for name in SECRETS[target]) and "is not set" in first["run"]


def test_pages_deploy_uses_the_github_pages_environment():
    assert deploy_job("github-pages")["environment"] == {
        "name": "github-pages",
        "url": "${{ steps.pages.outputs.page_url }}",
    }


@pytest.mark.parametrize("name", ["qa.yml", *(f"deploy-{target}.yml" for target in TARGETS)])
def test_no_expression_inside_a_run_script(name):
    for job in load(name)["jobs"].values():
        for step in job.get("steps", []):
            assert "${{" not in step.get("run", ""), step.get("name", step.get("run"))


def rsync_run() -> str:
    (step,) = [step for step in deploy_job("rsync")["steps"] if "rsync " in step.get("run", "")]
    return step["run"]


def test_rsync_step_verifies_the_host_and_never_prompts():
    run = rsync_run()
    assert "StrictHostKeyChecking=yes" in run
    assert "BatchMode=yes" in run


@pytest.mark.parametrize("target", TARGETS)
def test_no_run_script_scans_for_host_keys(target):
    for step in deploy_job(target)["steps"]:
        assert "ssh-keyscan" not in step.get("run", ""), step.get("name")


@pytest.mark.parametrize("target", TARGETS)
def test_no_step_overrides_path_or_user(target):
    for step in deploy_job(target)["steps"]:
        assert not {"PATH", "USER"} & set(step.get("env") or {}), step.get("name")
