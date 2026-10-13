"""Guard the marketplace build job in qa.yml. Never reads the `on:` key: YAML 1.1 parses it as True."""

from pathlib import Path

import yaml

WORKFLOW = Path(__file__).parent.parent / ".github" / "workflows" / "qa.yml"


def build_job() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["build"]


def test_runs_after_qa_on_pushes_to_main_only():
    job = build_job()
    assert job["needs"] == "qa"
    assert job["if"] == "github.event_name == 'push' && github.ref == 'refs/heads/main'"


def test_builds_and_uploads_the_site_with_a_pinned_action():
    steps = build_job()["steps"]
    assert {"run": "uv run --locked skill-hub build"} in steps
    assert {"id": "deploy", "run": "uv run --locked skill-hub deploy-config --github-output"} in steps
    (upload,) = [step for step in steps if step.get("uses", "").startswith("actions/upload-artifact")]
    assert upload["uses"] == "actions/upload-artifact@v7"
    assert upload["with"] == {"name": "marketplace-page", "path": "site/", "if-no-files-found": "error"}


def test_only_the_pages_deploy_widens_permissions():
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert workflow["permissions"] == {"contents": "read"}
    widened = {name for name, job in workflow["jobs"].items() if job.get("permissions", {}) != {}}
    assert widened == {"deploy-github-pages"}
