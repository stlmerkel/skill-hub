# tests/test_config.py
import pytest

from skill_hub.config import check_hub
from tests.conftest import GOOD_HUB, ids, write_hub


def test_good_hub_has_no_findings(tmp_path):
    write_hub(tmp_path)
    findings, config = check_hub(tmp_path)
    assert findings == []
    assert config.name == "acme-skills" and config.allow_keys == ()


def test_h1_missing(tmp_path):
    findings, config = check_hub(tmp_path)
    assert ids(findings) == ["H1"] and config is None


def test_h1_directory_named_hub_yml(tmp_path):
    (tmp_path / "hub.yml").mkdir()
    assert ids(check_hub(tmp_path)[0]) == ["H1"]


def test_h2_invalid_utf8(tmp_path):
    (tmp_path / "hub.yml").write_bytes(b"hub:\n  name: \xff\n")
    assert ids(check_hub(tmp_path)[0]) == ["H2"]


@pytest.mark.parametrize("text", ["hub: [unclosed\n", "- a\n- b\n", "", "hub: {}\nhub: {}\n"])
def test_h2_bad_yaml_or_not_mapping(tmp_path, text):
    write_hub(tmp_path, text)
    assert ids(check_hub(tmp_path)[0]) == ["H2"]


def test_h3_hub_not_mapping(tmp_path):
    write_hub(tmp_path, "hub: []\n")
    assert ids(check_hub(tmp_path)[0]) == ["H3"]


@pytest.mark.parametrize(
    "replacement",
    ["  owner: \n", "  owner: '   '\n", "  owner: 42\n", "  owner: on\n", ""],
)
def test_h3_required_field_problems(tmp_path, replacement):
    write_hub(tmp_path, GOOD_HUB.replace("  owner: Acme Platform Team\n", replacement))
    assert ids(check_hub(tmp_path)[0]) == ["H3"]


def test_h3_type_message_has_quote_hint(tmp_path):
    write_hub(tmp_path, GOOD_HUB.replace("  owner: Acme Platform Team\n", "  owner: on\n"))
    (finding,) = check_hub(tmp_path)[0]
    assert "boolean" in finding.message and "quote" in finding.message


def test_h4_bad_name(tmp_path):
    write_hub(tmp_path, GOOD_HUB.replace("name: acme-skills", "name: Acme_Skills"))
    findings = check_hub(tmp_path)[0]
    assert ids(findings) == ["H4"]
    assert "Acme_Skills" not in findings[0].message


@pytest.mark.parametrize(
    "qa_block",
    ["qa: null\n", "qa: []\n", "qa:\n  allow_keys: when_to_use\n", "qa:\n  allow_keys: [1]\n"],
)
def test_h5_bad_qa(tmp_path, qa_block):
    write_hub(tmp_path, GOOD_HUB.replace("qa:\n  allow_keys: []\n", qa_block))
    assert ids(check_hub(tmp_path)[0]) == ["H5"]


@pytest.mark.parametrize("qa_block", ["", "qa: {}\n"])
def test_h5_qa_defaults(tmp_path, qa_block):
    write_hub(tmp_path, GOOD_HUB.replace("qa:\n  allow_keys: []\n", qa_block))
    findings, config = check_hub(tmp_path)
    assert findings == [] and config.allow_keys == ()


def test_allow_keys_returned(tmp_path):
    write_hub(tmp_path, GOOD_HUB.replace("allow_keys: []", "allow_keys: [when_to_use]"))
    assert check_hub(tmp_path)[1].allow_keys == ("when_to_use",)


def test_h6_default_identity_warns(tmp_path):
    text = GOOD_HUB.replace("name: acme-skills", "name: my-skill-hub").replace(
        "https://github.com/acme/skills", "https://github.com/you/your-hub"
    )
    write_hub(tmp_path, text)
    findings, config = check_hub(tmp_path)
    assert ids(findings) == ["H6", "H6"]
    assert all(f.level == "warning" for f in findings)
    assert config is not None  # warnings do not withhold the config
