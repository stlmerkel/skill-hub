import datetime

import pytest

from skill_hub.contract import (
    DEPLOY_SETTING_RULES,
    github_repo,
    is_blank,
    is_hex_colour,
    is_reserved_marketplace_name,
    is_reserved_plugin_name,
    is_safe_logo_url,
    is_valid_name,
    is_valid_semver,
    type_name,
)


@pytest.mark.parametrize("name", ["a", "example-skill", "sql2-optimizer", "a" * 64, "0-9"])
def test_valid_names(name):
    assert is_valid_name(name)


@pytest.mark.parametrize(
    "name",
    ["", "a" * 65, "Example", "-lead", "trail-", "dou--ble", "under_score", "sp ace", "café"],
)
def test_invalid_names(name):
    assert not is_valid_name(name)


@pytest.mark.parametrize("version", ["0.0.0", "1.2.3", "1.2.3-rc.1+build.01", "10.20.30-alpha-1.x"])
def test_valid_semver(version):
    assert is_valid_semver(version)


@pytest.mark.parametrize(
    "version",
    ["01.2.3", "1.2.3-01", "1.2", "1.2.3-", "1.2.3+", "1.2.3\n", " 1.2.3", "1.2.3 ",
     "\u0661.2.3", "1\u0661.2.3", "v1.2.3"],
)
def test_invalid_semver(version):
    assert not is_valid_semver(version)


def test_is_blank():
    assert is_blank("") and is_blank("  \n\t")
    assert not is_blank(" x ")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "null"),
        (True, "boolean"),
        (1, "number"),
        (1.0, "number"),
        (datetime.date(2026, 1, 1), "date"),
        ("x", "string"),
        ([], "list"),
        ({}, "mapping"),
    ],
)
def test_type_name(value, expected):
    assert type_name(value) == expected


@pytest.mark.parametrize("value", ["#fff", "#FFF", "#4f46e5", "#4F46E5"])
def test_hex_colour_accepts(value):
    assert is_hex_colour(value)


@pytest.mark.parametrize(
    "value",
    ["red", "#12345", "#gggggg", "4f46e5", "#fff;", "#4f46e5 ", "red;}</style><script>alert(1)</script>", ""],
)
def test_hex_colour_rejects(value):
    assert not is_hex_colour(value)


@pytest.mark.parametrize("value", ["https://cdn.example.test/logo.png", "logo.png", "assets/logo.svg", "/logo.png"])
def test_logo_url_accepts(value):
    assert is_safe_logo_url(value)


@pytest.mark.parametrize(
    "value",
    [
        "javascript:alert(1)",
        "JavaScript:alert(1)",
        "vbscript:x",
        "data:image/png;base64,AA",
        "http://example.test/logo.png",
        "//evil.test/logo.png",
        " javascript:alert(1)",
        "\tjavascript:alert(1)",
        "\\\\evil.test/logo.png",
        "https://",
    ],
)
def test_logo_url_rejects(value):
    assert not is_safe_logo_url(value)


@pytest.mark.parametrize(
    "name",
    [
        "agent-skills",
        "claude-plugins-official",
        "healthcare",
        "anthropic-plugin-directory",
        "inline",
        "skills-dir",
        "npm",
        "github",
        "gh",
        "constructor",
        "claudeai-team",
    ],
)
def test_reserved_marketplace_names(name):
    assert is_reserved_marketplace_name(name)


@pytest.mark.parametrize("name", ["my-skill-hub", "acme-skills", "github-tools", "claudeai", "skills"])
def test_unreserved_marketplace_names(name):
    assert not is_reserved_marketplace_name(name)


@pytest.mark.parametrize(
    "name",
    [
        "claude",
        "anthropic",
        "anthropics",
        "claude-code",
        "claude-mods",
        "claude-helper",
        "anthropic-tools",
        "anthropics-tools",
        "cc-plugin-lint",
        "official-claude-tools",
        "tools-anthropic-official",
    ],
)
def test_reserved_plugin_names(name):
    assert is_reserved_plugin_name(name)


@pytest.mark.parametrize("name", ["commit-message", "mcp-for-claude", "claudette", "official-tools", "cc-plugins"])
def test_unreserved_plugin_names(name):
    assert not is_reserved_plugin_name(name)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/acme/skills", "acme/skills"),
        ("https://github.com/acme/skills.git", "acme/skills"),
        ("https://github.com/acme/skills/", "acme/skills"),
        ("https://github.com/acme/skills.git/", "acme/skills"),
        ("https://github.com/acme/my.hub", "acme/my.hub"),
        ("http://github.com/acme/skills", None),
        ("https://gitlab.com/acme/skills", None),
        ("https://github.com/acme", None),
        ("https://github.com/acme/skills/tree/main", None),
        ("https://github.com/acme/..", None),
        ("", None),
    ],
)
def test_github_repo(url, expected):
    assert github_repo(url) == expected


VALID_SETTINGS = [
    ("s3", "bucket", "my-hub"),
    ("s3", "bucket", "hub.example.com"),
    ("s3", "bucket", "a" * 63),
    ("s3", "endpoint", "https://abc123.r2.cloudflarestorage.com"),
    ("s3", "endpoint", "https://minio.lan:9000"),
    ("s3", "endpoint", "https://s3.example.com/"),
    ("s3", "region", "us-east-1"),
    ("s3", "region", "auto"),
    ("rsync", "host", "web1.example.com"),
    ("rsync", "host", "192.168.1.20"),
    ("rsync", "host", "nas"),
    ("rsync", "user", "deploy"),
    ("rsync", "user", "www-data"),
    ("rsync", "user", "_svc"),
    ("rsync", "path", "/var/www/skills"),
    ("rsync", "path", "~/public_html"),
    ("rsync", "path", "sites/hub.v2"),
    ("rsync", "port", 1),
    ("rsync", "port", 22),
    ("rsync", "port", 65535),
]

INVALID_SETTINGS = [
    ("s3", "bucket", "ab"),
    ("s3", "bucket", "a" * 64),
    ("s3", "bucket", "My-Bucket"),
    ("s3", "bucket", "-hub"),
    ("s3", "bucket", "hub-"),
    ("s3", "bucket", "a..b"),
    ("s3", "bucket", "hub;id"),
    ("s3", "bucket", "hub\n"),
    ("s3", "endpoint", "http://minio.lan"),
    ("s3", "endpoint", "https://"),
    ("s3", "endpoint", "https://a.example/path"),
    ("s3", "endpoint", "https://a.example;id"),
    ("s3", "endpoint", "https://a.example\n"),
    ("s3", "region", "US-EAST-1"),
    ("s3", "region", "us east"),
    ("s3", "region", "us-east-1\nrsync_host=evil"),
    ("rsync", "host", "-oProxyCommand=id"),
    ("rsync", "host", "web 1"),
    ("rsync", "host", "web1;id"),
    ("rsync", "host", "deploy@web1"),
    ("rsync", "host", "web1\n"),
    ("rsync", "user", "root;id"),
    ("rsync", "user", "-l"),
    ("rsync", "user", "Deploy"),
    ("rsync", "user", "a" * 33),
    ("rsync", "path", "-e sh"),
    ("rsync", "path", "/var/www;id"),
    ("rsync", "path", "/var/$(id)"),
    ("rsync", "path", "/var/www/../etc"),
    ("rsync", "path", "../up"),
    ("rsync", "path", "/var/www\n"),
    ("rsync", "path", "/var/www\x00"),
    ("rsync", "path", "/var/my site"),
    ("rsync", "port", 0),
    ("rsync", "port", 65536),
    ("rsync", "port", True),
    ("rsync", "port", "22"),
]


@pytest.mark.parametrize("target, key, value", VALID_SETTINGS)
def test_valid_deploy_settings(target, key, value):
    rule, _ = DEPLOY_SETTING_RULES[(target, key)]
    assert rule(value)


@pytest.mark.parametrize("target, key, value", INVALID_SETTINGS)
def test_invalid_deploy_settings(target, key, value):
    rule, _ = DEPLOY_SETTING_RULES[(target, key)]
    assert not rule(value)


def test_every_deploy_setting_has_a_rule():
    from skill_hub.contract import DEPLOY_TARGET_SETTINGS

    expected = {(target, key) for target, keys in DEPLOY_TARGET_SETTINGS.items() for key in keys}
    assert set(DEPLOY_SETTING_RULES) == expected
