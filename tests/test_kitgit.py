import pytest

from skill_hub.kitgit import (
    Entry,
    KitGitError,
    fetch_commit,
    list_kit_tags,
    newer_major,
    read_blob,
    require_clean_repo,
    select_target,
    tree_entries,
)
from tests.kitrepo import Exec, Link, git, make_hub, make_kit_repo


def _kit(tmp_path):
    return make_kit_repo(
        tmp_path / "kit",
        [("1.0.0", {"a.txt": b"one\n"}), ("1.2.0", {"a.txt": b"two\n"})],
    )


def test_list_kit_tags_ignores_non_kit_and_suffixed_tags(tmp_path):
    url = _kit(tmp_path)
    kit = tmp_path / "kit"
    git(kit, "tag", "v9.9.9")
    git(kit, "tag", "kit-v1.3.0-rc1")
    git(kit, "tag", "kit-v1.3")
    tags = list_kit_tags(url)
    assert sorted(tags) == [(1, 0, 0), (1, 2, 0)]
    assert tags[(1, 2, 0)] == git(kit, "rev-parse", "HEAD")


def test_annotated_tags_resolve_to_commit(tmp_path):
    url = _kit(tmp_path)
    kit = tmp_path / "kit"
    git(kit, "tag", "-a", "-m", "annotated", "kit-v1.4.0")
    tags = list_kit_tags(url)
    assert tags[(1, 4, 0)] == git(kit, "rev-parse", "kit-v1.4.0^{commit}")
    assert tags[(1, 4, 0)] != git(kit, "rev-parse", "kit-v1.4.0")


def test_list_kit_tags_unreachable_repo(tmp_path):
    missing = (tmp_path / "nowhere-secret").as_uri()
    with pytest.raises(KitGitError, match="could not list") as info:
        list_kit_tags(missing)
    assert "nowhere-secret" not in str(info.value)


def test_list_kit_tags_rejects_invalid_repo():
    with pytest.raises(KitGitError, match="not a valid kit repo"):
        list_kit_tags("--upload-pack=evil")


def test_fetch_rejects_invalid_repo(tmp_path):
    with pytest.raises(KitGitError, match="not a valid kit repo"):
        fetch_commit(tmp_path, "-x", (1, 0, 0), "a" * 40)


TAGS = {(1, 0, 0): "a", (1, 2, 0): "b", (2, 0, 0): "c"}


def test_select_target_stays_in_major():
    assert select_target(TAGS, (1, 0, 0), major=False) == (1, 2, 0)
    assert select_target(TAGS, (1, 0, 0), major=True) == (2, 0, 0)


def test_select_target_never_downgrades():
    assert select_target({(1, 0, 0): "a"}, (1, 2, 0), major=False) is None
    assert select_target({(1, 0, 0): "a"}, (1, 2, 0), major=True) is None


def test_newer_major():
    assert newer_major(TAGS, (1, 0, 0)) == 2
    assert newer_major(TAGS, (2, 0, 0)) is None


def test_fetch_commit_verifies_sha(tmp_path):
    url = _kit(tmp_path)
    hub = make_hub(tmp_path / "hub", url, "1.0.0", {"x": b"x"})
    good = git(tmp_path / "kit", "rev-parse", "kit-v1.2.0^{commit}")
    fetch_commit(hub, url, (1, 2, 0), good)
    assert read_blob(hub, tree_entries(hub, good)["a.txt"].blob) == b"two\n"
    with pytest.raises(KitGitError, match="does not match"):
        fetch_commit(hub, url, (1, 2, 0), "0" * 40)


def test_fetch_commit_missing_tag(tmp_path):
    url = _kit(tmp_path)
    hub = make_hub(tmp_path / "hub", url, "1.0.0", {"x": b"x"})
    with pytest.raises(KitGitError, match="could not fetch"):
        fetch_commit(hub, url, (9, 0, 0), "0" * 40)


def test_require_clean_repo(tmp_path):
    hub = make_hub(tmp_path / "hub", "file:///k", "1.0.0", {"x": b"x"})
    require_clean_repo(hub)
    (hub / "new.txt").write_text("u")
    with pytest.raises(KitGitError, match="uncommitted changes"):
        require_clean_repo(hub)
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(KitGitError, match="not a git repository"):
        require_clean_repo(plain)


def test_require_clean_repo_rejects_a_hub_nested_in_another_repo(tmp_path):
    outer = make_hub(tmp_path / "outer", "file:///k", "1.0.0", {".gitignore": b"inner/\n"})
    inner = outer / "inner"
    inner.mkdir()
    (inner / "hub.yml").write_text("name: x\n")
    assert git(outer, "status", "--porcelain") == ""  # git-ignored: the outer repo reads as clean
    with pytest.raises(KitGitError, match="not the top of its own git repository") as info:
        require_clean_repo(inner)
    assert "inner" not in str(info.value)


def test_tree_entries_modes(tmp_path):
    url = make_kit_repo(
        tmp_path / "kit",
        [("1.0.0", {"run.sh": Exec(b"#!/bin/sh\n"), "ln": Link(b"run.sh"), "d/f": b"f"})],
    )
    commit = list_kit_tags(url)[(1, 0, 0)]
    hub = make_hub(tmp_path / "hub", url, "1.0.0", {"x": b"x"})
    fetch_commit(hub, url, (1, 0, 0), commit)
    entries = tree_entries(hub, commit)
    assert entries["run.sh"].mode == "100755"
    assert entries["ln"].mode == "120000"
    assert entries["d/f"] == Entry("100644", entries["d/f"].blob)
    assert read_blob(hub, entries["ln"].blob) == b"run.sh"


def test_kit_repo_deletes_paths(tmp_path):
    url = make_kit_repo(tmp_path / "kit", [("1.0.0", {"a": b"1", "b": b"2"}), ("1.1.0", {"a": None})])
    commit = list_kit_tags(url)[(1, 1, 0)]
    hub = make_hub(tmp_path / "hub", url, "1.0.0", {"x": b"x"})
    fetch_commit(hub, url, (1, 1, 0), commit)
    assert sorted(tree_entries(hub, commit)) == ["b"]
