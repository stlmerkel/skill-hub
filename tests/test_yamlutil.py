# tests/test_yamlutil.py
import datetime

from skill_hub.yamlutil import load_yaml

SECRET = "hunter" + "2hunter2"


def test_plain_mapping_and_key_lines():
    loaded = load_yaml('name: a\n"description": b\nmetadata:\n  version: "1.0.0"\n')
    assert loaded.error is None
    assert loaded.data == {"name": "a", "description": "b", "metadata": {"version": "1.0.0"}}
    assert loaded.key_lines == (("name", 1), ("description", 2), ("metadata", 3))


def test_empty_document_is_none():
    loaded = load_yaml("")
    assert loaded.error is None and loaded.data is None


def test_duplicate_top_level_key_rejected():
    loaded = load_yaml("name: first\nname: second\n")
    assert loaded.error is not None and loaded.error.line == 2
    assert "duplicate" in loaded.error.message


def test_duplicate_nested_key_rejected():
    loaded = load_yaml('metadata:\n  version: "1"\n  version: "2"\n')
    assert loaded.error is not None and loaded.error.line == 3


def test_merge_key_rejected():
    loaded = load_yaml("base: &b {x: 1}\nother:\n  <<: *b\n")
    assert loaded.error is not None and "merge" in loaded.error.message


def test_syntax_error_has_line_and_no_source_text():
    loaded = load_yaml(f"name: ok\npassword: [{SECRET}\n")
    assert loaded.error is not None and loaded.error.line is not None
    assert SECRET not in loaded.error.message


def test_invalid_date_is_an_error_not_a_traceback():
    loaded = load_yaml("released: 2026-99-99\n")
    assert loaded.error is not None


def test_scalars_are_coerced_by_yaml_and_reported_raw_in_key_lines():
    loaded = load_yaml("yes: on\nd: 2026-01-01\nv: 1.0\n")
    assert loaded.data == {True: True, "d": datetime.date(2026, 1, 1), "v": 1.0}
    assert loaded.key_lines[0] == ("yes", 1)


def test_list_key_rejected():
    loaded = load_yaml("? [a, b]\n: c\n")
    assert loaded.error is not None  # list keys are unhashable
