"""Guard the release workflow's least-privilege setup. Never reads the `on:` key: YAML 1.1 parses it as True."""

from pathlib import Path

import yaml

from skill_hub.contract import KIT_RELEASE_CONFIG, KIT_RELEASE_MANIFEST
from skill_hub.releases import RELEASE_CONFIG, RELEASE_MANIFEST

WORKFLOW = Path(__file__).parent.parent / ".github" / "workflows" / "release.yml"


def load() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_permissions_are_granted_per_job_only():
    workflow = load()
    assert workflow["permissions"] == {}
    assert list(workflow["jobs"]) == ["release-please", "kit-release"]
    for job in workflow["jobs"].values():
        assert job["permissions"] == {"contents": "write", "pull-requests": "write"}


def test_action_ref_token_and_files():
    (step,) = load()["jobs"]["release-please"]["steps"]
    assert step["uses"] == "googleapis/release-please-action@v5"
    assert step["with"] == {
        "token": "${{ secrets.RELEASE_PLEASE_TOKEN || github.token }}",
        "config-file": RELEASE_CONFIG,
        "manifest-file": RELEASE_MANIFEST,
    }


def test_kit_release_job_is_variable_gated():
    job = load()["jobs"]["kit-release"]
    assert job["if"] == "vars.SKILL_HUB_KIT_RELEASES == 'true'"
    (step,) = job["steps"]
    assert step["uses"] == "googleapis/release-please-action@v5"
    assert step["with"] == {
        "token": "${{ secrets.RELEASE_PLEASE_TOKEN || github.token }}",
        "config-file": KIT_RELEASE_CONFIG,
        "manifest-file": KIT_RELEASE_MANIFEST,
    }
    assert "if" not in load()["jobs"]["release-please"]
