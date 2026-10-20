import pytest

from skill_hub.contract import KIT_FILE
from skill_hub.kitfile import KitFile, KitFileError, read_kit_file, render_kit_file, write_kit_file

COMMIT = "a" * 40
BASE = 'repo: "https://github.com/acme/kit"\nversion: "1.2.3"\n'


def put(root, text):
    path = root / KIT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_round_trip(tmp_path):
    kit = KitFile("https://github.com/acme/kit", "1.2.3", COMMIT, "1.1.0", "b" * 40)
    text = render_kit_file(kit)
    assert text.startswith("#")
    version_line = next(line for line in text.splitlines() if line.startswith("version:"))
    assert version_line.endswith("# x-release-please-version")
    write_kit_file(tmp_path, kit)
    assert read_kit_file(tmp_path) == kit


def test_round_trip_minimal(tmp_path):
    kit = KitFile("file:///tmp/kit", "0.0.0")
    write_kit_file(tmp_path, kit)
    assert read_kit_file(tmp_path) == kit
    assert not kit.pending


def test_pending_follows_workflows_version():
    assert KitFile("https://x", "1.0.0", COMMIT, "0.9.0", COMMIT).pending


BAD = [
    (None, "kit.yml could not be read"),
    ("a: [", "kit.yml is not valid YAML"),
    ("- x\n", "kit.yml must be a mapping, found list"),
    ('version: "1.2.3"\n', "kit.yml repo is missing"),
    ('repo: "-x"\nversion: "1.2.3"\n', "kit.yml repo must be an https:// or file:// URL"),
    ('repo: "https://a/b"\nversion: "1.2"\n', "kit.yml version must be a quoted X.Y.Z version"),
    ('repo: "https://a/b"\nversion: 1.2\n', "kit.yml version must be a quoted X.Y.Z version"),
    (BASE + 'commit: "abc"\n', "kit.yml commit must be empty or 40 lowercase hex characters"),
    (BASE + 'workflows_version: "1.0.0"\n', "kit.yml workflows_version and workflows_commit must be set together"),
]


@pytest.mark.parametrize(("text", "message"), BAD)
def test_read_kit_file_rejects(tmp_path, text, message):
    if text is not None:
        put(tmp_path, text)
    with pytest.raises(KitFileError, match=message) as info:
        read_kit_file(tmp_path)
    for secret in ("-x", "abc", "1.2"):
        if secret in (text or "") and secret not in message:
            assert secret not in str(info.value)
