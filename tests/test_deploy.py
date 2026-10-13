import pytest

from skill_hub.config import check_hub
from skill_hub.deploy import DeploySettings, render_outputs
from skill_hub.findings import WARNING
from tests.conftest import GOOD_HUB, RSYNC_DEPLOY, S3_DEPLOY, ids, make_deploy_workflow, write_hub


def check(tmp_path, block, workflow=None):
    write_hub(tmp_path, GOOD_HUB + block)
    if workflow:
        make_deploy_workflow(tmp_path, workflow)
    return check_hub(tmp_path)


@pytest.mark.parametrize("block", ["", "deploy:\n", 'deploy:\n  target: ""\n'])
def test_no_target_has_no_findings(tmp_path, block):
    findings, config = check(tmp_path, block)
    assert findings == [] and config.deploy == DeploySettings()


@pytest.mark.parametrize("block", ["deploy: []\n", "deploy: s3\n"])
def test_h12_deploy_not_mapping(tmp_path, block):
    findings, config = check(tmp_path, block)
    assert ids(findings) == ["H12"] and config is None


@pytest.mark.parametrize("target", ["on", "42", "null", "S3", "-s3", "'s3; id'", '"s3\\nrsync_host=evil"'])
def test_h12_bad_target(tmp_path, target):
    findings, config = check(tmp_path, f"deploy:\n  target: {target}\n")
    assert ids(findings) == ["H12"] and config is None


def test_h12_never_prints_the_target(tmp_path):
    (finding,) = check(tmp_path, "deploy:\n  target: 's3; id'\n")[0]
    assert "; id" not in finding.message


def test_h12_unknown_key_is_a_warning(tmp_path):
    findings, config = check(tmp_path, 'deploy:\n  target: ""\n  bucket: acme\n')
    assert ids(findings) == ["H12"] and findings[0].level == WARNING and config is not None


@pytest.mark.parametrize(
    "block",
    [
        "deploy:\n  s3: []\n",
        "deploy:\n  s3:\n    bucket: 2024\n",
        "deploy:\n  s3:\n    region:\n",
        'deploy:\n  rsync:\n    port: "22"\n',
        "deploy:\n  rsync:\n    port: on\n",
    ],
)
def test_h13_bad_types(tmp_path, block):
    findings, config = check(tmp_path, block)
    assert ids(findings) == ["H13"] and config is None


def test_h13_type_message_has_quote_hint(tmp_path):
    (finding,) = check(tmp_path, "deploy:\n  s3:\n    bucket: 2024\n")[0]
    assert "number" in finding.message and "quote" in finding.message


def test_h13_unknown_setting_is_a_warning(tmp_path):
    findings, config = check(tmp_path, "deploy:\n  rsync:\n    hostname: web1\n")
    assert ids(findings) == ["H13"] and findings[0].level == WARNING and config is not None


@pytest.mark.parametrize(
    "block, workflow",
    [
        (S3_DEPLOY.replace("    bucket: acme-skills\n", ""), "s3"),
        (S3_DEPLOY.replace("region: us-east-1", "region: '  '"), "s3"),
        ("deploy:\n  target: s3\n", "s3"),
        (RSYNC_DEPLOY.replace("    path: /var/www/skills\n", ""), "rsync"),
        (RSYNC_DEPLOY.replace("user: deploy", 'user: ""'), "rsync"),
    ],
)
def test_h14_missing_required_setting(tmp_path, block, workflow):
    findings, config = check(tmp_path, block, workflow)
    assert set(ids(findings)) == {"H14"} and config is None


def test_h14_not_repeated_after_a_type_error(tmp_path):
    findings, _ = check(tmp_path, S3_DEPLOY.replace("bucket: acme-skills", "bucket: 2024"), "s3")
    assert ids(findings) == ["H13"]


def test_h14_only_for_the_selected_target(tmp_path):
    findings, config = check(tmp_path, 'deploy:\n  target: github-pages\n  s3:\n    bucket: ""\n', "github-pages")
    assert findings == [] and config.deploy == DeploySettings("github-pages")


H15_CASES = [
    (S3_DEPLOY, "bucket: acme-skills", "bucket: Acme_Skills", "s3"),
    (S3_DEPLOY, "bucket: acme-skills", "bucket: 'acme; id'", "s3"),
    (S3_DEPLOY, 'endpoint: ""', "endpoint: http://minio.lan", "s3"),
    (S3_DEPLOY, "region: us-east-1", 'region: "us-east-1\\nrsync_host=evil"', "s3"),
    (RSYNC_DEPLOY, "host: web1.example.com", "host: -oProxyCommand=id", "rsync"),
    (RSYNC_DEPLOY, "user: deploy", "user: 'deploy;id'", "rsync"),
    (RSYNC_DEPLOY, "path: /var/www/skills", "path: /var/www/../../etc", "rsync"),
    (RSYNC_DEPLOY, "path: /var/www/skills", "path: '-e sh'", "rsync"),
    (RSYNC_DEPLOY, "path: /var/www/skills", "path: /var/www/skills\n    port: 70000", "rsync"),
]


@pytest.mark.parametrize("block, old, new, workflow", H15_CASES)
def test_h15_bad_value(tmp_path, block, old, new, workflow):
    findings, config = check(tmp_path, block.replace(old, new), workflow)
    assert ids(findings) == ["H15"] and config is None
    assert new.split(": ", 1)[1].strip("'\"") not in findings[0].message


def test_h15_checks_settings_of_an_unselected_target(tmp_path):
    findings, config = check(tmp_path, "deploy:\n  target: \"\"\n  rsync:\n    path: '/var/www;id'\n")
    assert ids(findings) == ["H15"] and config is None


@pytest.mark.parametrize("block", [S3_DEPLOY, "deploy:\n  target: github-pages\n", "deploy:\n  target: my-cdn\n"])
def test_h16_missing_workflow(tmp_path, block):
    findings, config = check(tmp_path, block)
    assert ids(findings) == ["H16"] and config is None


def test_custom_target_with_its_workflow_passes(tmp_path):
    findings, config = check(tmp_path, "deploy:\n  target: my-cdn\n", "my-cdn")
    assert findings == [] and config.deploy == DeploySettings("my-cdn")


def test_s3_outputs_leave_out_an_empty_endpoint(tmp_path):
    findings, config = check(tmp_path, S3_DEPLOY, "s3")
    assert findings == []
    assert config.deploy == DeploySettings("s3", (("s3_bucket", "acme-skills"), ("s3_region", "us-east-1")))


def test_s3_whitespace_endpoint_is_unset(tmp_path):
    findings, config = check(tmp_path, S3_DEPLOY.replace('endpoint: ""', "endpoint: ' '"), "s3")
    assert findings == []
    assert [name for name, _ in config.deploy.outputs] == ["s3_bucket", "s3_region"]


def test_s3_outputs_with_an_endpoint(tmp_path):
    block = S3_DEPLOY.replace('endpoint: ""', "endpoint: https://abc123.r2.cloudflarestorage.com").replace(
        "region: us-east-1", "region: auto"
    )
    _, config = check(tmp_path, block, "s3")
    assert config.deploy.outputs == (
        ("s3_bucket", "acme-skills"),
        ("s3_endpoint", "https://abc123.r2.cloudflarestorage.com"),
        ("s3_region", "auto"),
    )


@pytest.mark.parametrize("extra, port", [("", "22"), ("    port: 2222\n", "2222")])
def test_rsync_outputs_include_the_port(tmp_path, extra, port):
    _, config = check(tmp_path, RSYNC_DEPLOY + extra, "rsync")
    assert config.deploy == DeploySettings(
        "rsync",
        (
            ("rsync_host", "web1.example.com"),
            ("rsync_user", "deploy"),
            ("rsync_path", "/var/www/skills"),
            ("rsync_port", port),
        ),
    )


def test_only_the_selected_targets_settings_are_output(tmp_path):
    block = RSYNC_DEPLOY + "  s3:\n    bucket: other-bucket\n    region: us-east-1\n"
    findings, config = check(tmp_path, block, "rsync")
    assert findings == []
    assert all(name.startswith("rsync_") for name, _ in config.deploy.outputs)


def test_render_outputs():
    assert render_outputs(DeploySettings()) == "target=\n"
    settings = DeploySettings("s3", (("s3_bucket", "acme-skills"), ("s3_region", "us-east-1")))
    assert render_outputs(settings) == "target=s3\ns3_bucket=acme-skills\ns3_region=us-east-1\n"
