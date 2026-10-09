"""Guard the release workflow's least-privilege setup. Never reads the `on:` key: YAML 1.1 parses it as True."""

from pathlib import Path

import yaml

from skill_hub.releases import RELEASE_CONFIG, RELEASE_MANIFEST

WORKFLOW = Path(__file__).parent.parent / ".github" / "workflows" / "release.yml"


def load() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_permissions_are_granted_per_job_only():
    workflow = load()
    assert workflow["permissions"] == {}
    assert list(workflow["jobs"]) == ["release-please"]
    assert workflow["jobs"]["release-please"]["permissions"] == {"contents": "write", "pull-requests": "write"}


def test_action_ref_token_and_files():
    (step,) = load()["jobs"]["release-please"]["steps"]
    assert step["uses"] == "googleapis/release-please-action@v5"
    assert step["with"] == {
        "token": "${{ secrets.RELEASE_PLEASE_TOKEN || github.token }}",
        "config-file": RELEASE_CONFIG,
        "manifest-file": RELEASE_MANIFEST,
    }
