# tests/test_config.py
import os

import pytest

from skill_hub.config import SiteSettings, check_hub
from tests.conftest import GOOD_HUB, ids, make_theme, write_hub


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


SECRET = "AKIA" + "Q" * 16


def site_hub(body: str) -> str:
    return GOOD_HUB + "site:\n" + body


def test_no_site_block_gives_defaults(tmp_path):
    write_hub(tmp_path)
    findings, config = check_hub(tmp_path)
    assert findings == [] and config.site == SiteSettings()


def test_empty_site_block_gives_defaults(tmp_path):
    write_hub(tmp_path, GOOD_HUB + "site:\n")
    findings, config = check_hub(tmp_path)
    assert findings == [] and config.site == SiteSettings()


def test_good_site_block(tmp_path):
    make_theme(tmp_path, "my-theme")
    write_hub(tmp_path, site_hub('  accent: "#4f46e5"\n  logo_url: "logo.png"\n  theme: "my-theme"\n'))
    findings, config = check_hub(tmp_path)
    assert findings == []
    assert config.site == SiteSettings(accent="#4f46e5", logo_url="logo.png", theme="my-theme")


def test_shipped_empty_strings_are_defaults(tmp_path):
    write_hub(tmp_path, site_hub('  accent: ""\n  logo_url: ""\n  theme: ""\n'))
    findings, config = check_hub(tmp_path)
    assert findings == [] and config.site == SiteSettings()


def test_h7_site_not_mapping(tmp_path):
    write_hub(tmp_path, GOOD_HUB + "site: []\n")
    findings, config = check_hub(tmp_path)
    assert ids(findings) == ["H7"] and config is None


def test_h7_unquoted_hex_is_null_with_quote_hint(tmp_path):
    write_hub(tmp_path, site_hub("  accent: #4f46e5\n"))
    findings, config = check_hub(tmp_path)
    assert ids(findings) == ["H7"] and config is None
    assert "null" in findings[0].message and "quote" in findings[0].message


def test_h7_non_string_value(tmp_path):
    write_hub(tmp_path, site_hub("  logo_url: 42\n"))
    assert ids(check_hub(tmp_path)[0]) == ["H7"]


def test_h7_unknown_key_is_a_warning_without_echo(tmp_path):
    write_hub(tmp_path, site_hub(f"  {SECRET}: x\n"))
    findings, config = check_hub(tmp_path)
    assert ids(findings) == ["H7"] and findings[0].level == "warning"
    assert config is not None
    assert SECRET not in findings[0].message


@pytest.mark.parametrize("value", ["red", '"#12345"', '"red;}</style><script>alert(1)</script>"', f'"{SECRET}"'])
def test_h8_bad_accent(tmp_path, value):
    write_hub(tmp_path, site_hub(f"  accent: {value}\n"))
    findings = check_hub(tmp_path)[0]
    assert ids(findings) == ["H8"]
    assert SECRET not in findings[0].message


@pytest.mark.parametrize("value", ["javascript:alert(1)", "http://example.test/a.png", "//evil.test/a.png"])
def test_h9_bad_logo_url(tmp_path, value):
    write_hub(tmp_path, site_hub(f'  logo_url: "{value}"\n'))
    findings = check_hub(tmp_path)[0]
    assert ids(findings) == ["H9"]
    assert value not in findings[0].message


def test_h10_theme_folder_missing(tmp_path):
    write_hub(tmp_path, site_hub('  theme: "nope"\n'))
    assert ids(check_hub(tmp_path)[0]) == ["H10"]


def test_h10_theme_without_entry_point(tmp_path):
    (tmp_path / "bare").mkdir()
    write_hub(tmp_path, site_hub('  theme: "bare"\n'))
    assert ids(check_hub(tmp_path)[0]) == ["H10"]


def test_h10_theme_entry_point_is_a_directory(tmp_path):
    (tmp_path / "odd" / "index.html.j2").mkdir(parents=True)
    write_hub(tmp_path, site_hub('  theme: "odd"\n'))
    assert ids(check_hub(tmp_path)[0]) == ["H10"]


def test_h10_theme_outside_root(tmp_path):
    root = tmp_path / "hub"
    root.mkdir()
    make_theme(tmp_path, "outside")
    write_hub(root, site_hub('  theme: "../outside"\n'))
    assert ids(check_hub(root)[0]) == ["H10"]


def test_h10_theme_symlink_to_outside(tmp_path):
    root = tmp_path / "hub"
    root.mkdir()
    outside = make_theme(tmp_path, "outside")
    os.symlink(outside, root / "linked")
    write_hub(root, site_hub('  theme: "linked"\n'))
    assert ids(check_hub(root)[0]) == ["H10"]


def test_h10_theme_cannot_be_the_hub_root(tmp_path):
    (tmp_path / "index.html.j2").write_text("x", encoding="utf-8")
    write_hub(tmp_path, site_hub('  theme: "."\n'))
    assert ids(check_hub(tmp_path)[0]) == ["H10"]
