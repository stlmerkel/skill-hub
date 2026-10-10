import datetime

import pytest

from skill_hub.contract import is_blank, is_hex_colour, is_safe_logo_url, is_valid_name, is_valid_semver, type_name


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
