import os
import subprocess

import pytest

from skill_hub import merge
from skill_hub.kitgit import Entry
from skill_hub.merge import (
    ADOPTER_DELETED,
    BINARY_CONFLICT,
    KIT_DELETED_CHANGED,
    MERGE_FAILED,
    SUBMODULE,
    SYMLINK,
    TYPE_CHANGE,
    UNSAFE_PATH,
    Outcome,
    merge_path,
)


class Blobs:
    """Dict-backed blob store: entry() registers content, the instance serves it."""

    def __init__(self):
        self.data: dict[str, bytes] = {}

    def entry(self, content: bytes, mode: str = "100644") -> Entry:
        sha = f"blob{len(self.data)}"
        self.data[sha] = content
        return Entry(mode, sha)

    def __call__(self, sha: str) -> bytes:
        return self.data[sha]


@pytest.fixture
def blobs():
    return Blobs()


@pytest.fixture
def hub(tmp_path):
    root = tmp_path / "hub"
    root.mkdir()
    return root


LINES = [f"line {n}\n" for n in range(1, 21)]


def text(lines):
    return "".join(lines).encode()


def edit(lines, **changes):
    out = list(lines)
    for index, value in changes.items():
        out[int(index[1:])] = value
    return out


def test_clean_merge(hub, blobs):
    base = text(LINES)
    ours = text(edit(LINES, i1="ours 2\n"))
    theirs = text(edit(LINES, i17="kit 18\n"))
    (hub / "f.txt").write_bytes(ours)
    out = merge_path(hub, "f.txt", blobs.entry(base), blobs.entry(theirs), blobs)
    assert out == Outcome("f.txt", "updated")
    assert (hub / "f.txt").read_bytes() == text(edit(LINES, i1="ours 2\n", i17="kit 18\n"))


def test_conflict_counts_markers(hub, blobs):
    base = text(LINES)
    ours = text(edit(LINES, i1="ours 2\n", i17="ours 18\n"))
    theirs = text(edit(LINES, i1="kit 2\n", i17="kit 18\n"))
    (hub / "f.txt").write_bytes(ours)
    out = merge_path(hub, "f.txt", blobs.entry(base), blobs.entry(theirs), blobs)
    assert out == Outcome("f.txt", "conflict", conflicts=2)
    merged = (hub / "f.txt").read_text()
    assert merged.count("<<<<<<< your hub") == 2
    assert merged.count(">>>>>>> kit (new)") == 2


def test_unchanged_text_is_not_rewritten(hub, blobs):
    (hub / "f.txt").write_bytes(b"mine\n")
    out = merge_path(hub, "f.txt", blobs.entry(b"kit\n"), blobs.entry(b"kit\n"), blobs)
    assert out == Outcome("f.txt", "unchanged")
    assert (hub / "f.txt").read_bytes() == b"mine\n"


def test_adopter_deleted_stays_deleted(hub, blobs):
    out = merge_path(hub, "f.txt", blobs.entry(b"old\n"), blobs.entry(b"new\n"), blobs)
    assert out == Outcome("f.txt", "kept", reason=ADOPTER_DELETED)
    assert not (hub / "f.txt").exists()
    same = merge_path(hub, "g.txt", blobs.entry(b"old\n"), blobs.entry(b"old\n"), blobs)
    assert same == Outcome("g.txt", "unchanged")
    assert not (hub / "g.txt").exists()


def test_kit_deleted_unchanged_file_is_removed(hub, blobs):
    (hub / "f.txt").write_bytes(b"kit\n")
    out = merge_path(hub, "f.txt", blobs.entry(b"kit\n"), None, blobs)
    assert out == Outcome("f.txt", "deleted")
    assert not (hub / "f.txt").exists()


def test_kit_deleted_changed_file_is_kept(hub, blobs):
    (hub / "f.txt").write_bytes(b"mine\n")
    out = merge_path(hub, "f.txt", blobs.entry(b"kit\n"), None, blobs)
    assert out == Outcome("f.txt", "kept", reason=KIT_DELETED_CHANGED)
    assert (hub / "f.txt").read_bytes() == b"mine\n"


def test_kit_deleted_and_adopter_deleted_is_nothing(hub, blobs):
    out = merge_path(hub, "f.txt", blobs.entry(b"kit\n"), None, blobs)
    assert out == Outcome("f.txt", "unchanged")
    assert not (hub / "f.txt").exists()


def test_new_kit_file_added(hub, blobs):
    out = merge_path(hub, "a/b/new.sh", None, blobs.entry(b"#!/bin/sh\n", "100755"), blobs)
    assert out == Outcome("a/b/new.sh", "added")
    path = hub / "a" / "b" / "new.sh"
    assert path.read_bytes() == b"#!/bin/sh\n"
    assert os.stat(path).st_mode & 0o100


def test_both_added_identical(hub, blobs):
    (hub / "f.txt").write_bytes(b"same\n")
    out = merge_path(hub, "f.txt", None, blobs.entry(b"same\n"), blobs)
    assert out == Outcome("f.txt", "unchanged")


def test_both_added_different_text_conflicts(hub, blobs):
    (hub / "f.txt").write_bytes(b"mine\n")
    out = merge_path(hub, "f.txt", None, blobs.entry(b"kit\n"), blobs)
    assert out.action == "conflict" and out.conflicts == 1
    merged = (hub / "f.txt").read_text()
    assert "<<<<<<< your hub" in merged and "mine" in merged and "kit" in merged


def test_both_added_different_binary_kept(hub, blobs):
    (hub / "f.bin").write_bytes(b"\x00mine")
    out = merge_path(hub, "f.bin", None, blobs.entry(b"\x00kit"), blobs)
    assert out == Outcome("f.bin", "kept", reason=BINARY_CONFLICT)
    assert (hub / "f.bin").read_bytes() == b"\x00mine"


def test_binary_shortcuts(hub, blobs):
    old, new = b"\x00old", b"\x00new"
    (hub / "o_is_b.bin").write_bytes(old)
    out = merge_path(hub, "o_is_b.bin", blobs.entry(old), blobs.entry(new), blobs)
    assert out == Outcome("o_is_b.bin", "updated")
    assert (hub / "o_is_b.bin").read_bytes() == new
    (hub / "o_is_t.bin").write_bytes(new)
    out = merge_path(hub, "o_is_t.bin", blobs.entry(old), blobs.entry(new), blobs)
    assert out == Outcome("o_is_t.bin", "unchanged")
    assert (hub / "o_is_t.bin").read_bytes() == new


def test_binary_conflict_kept(hub, blobs):
    (hub / "f.bin").write_bytes(b"\x00mine")
    out = merge_path(hub, "f.bin", blobs.entry(b"\x00old"), blobs.entry(b"\x00new"), blobs)
    assert out == Outcome("f.bin", "kept", reason=BINARY_CONFLICT)
    assert (hub / "f.bin").read_bytes() == b"\x00mine"


@pytest.mark.parametrize("ours", [b"mine \xff\n", b"text\n"], ids=["invalid-utf8-ours", "text-ours"])
def test_text_vs_binary_mixed_kept(hub, blobs, ours):
    (hub / "f.txt").write_bytes(ours)
    theirs = b"new\n" if ours != b"text\n" else b"new\x00\n"
    out = merge_path(hub, "f.txt", blobs.entry(b"old\n"), blobs.entry(theirs), blobs)
    assert out == Outcome("f.txt", "kept", reason=BINARY_CONFLICT)
    assert (hub / "f.txt").read_bytes() == ours


@pytest.mark.parametrize("where", ["base", "target", "ours"])
def test_symlink_entry_kept(hub, blobs, where):
    regular = blobs.entry(b"old\n")
    link = blobs.entry(b"elsewhere", "120000")
    base, target = (link, blobs.entry(b"new\n")) if where == "base" else (regular, link)
    if where == "ours":
        base, target = regular, blobs.entry(b"new\n")
        (hub / "elsewhere").write_bytes(b"secret\n")
        (hub / "f.txt").symlink_to("elsewhere")
    else:
        (hub / "f.txt").write_bytes(b"old\n")
    out = merge_path(hub, "f.txt", base, target, blobs)
    assert out == Outcome("f.txt", "kept", reason=SYMLINK)
    if where == "ours":
        assert (hub / "f.txt").is_symlink()
        assert (hub / "elsewhere").read_bytes() == b"secret\n"
    else:
        assert (hub / "f.txt").read_bytes() == b"old\n"


def test_submodule_entry_kept(hub, blobs):
    (hub / "sub").mkdir()
    out = merge_path(hub, "sub", None, Entry("160000", "abc123"), blobs)
    assert out == Outcome("sub", "kept", reason=SUBMODULE)
    assert (hub / "sub").is_dir()


def test_directory_at_path_kept(hub, blobs):
    (hub / "f.txt").mkdir()
    (hub / "f.txt" / "inner").write_bytes(b"keep\n")
    out = merge_path(hub, "f.txt", blobs.entry(b"old\n"), None, blobs)
    assert out == Outcome("f.txt", "kept", reason=TYPE_CHANGE)
    assert (hub / "f.txt" / "inner").read_bytes() == b"keep\n"
    (hub / "plain").write_bytes(b"file\n")
    out = merge_path(hub, "plain/child.txt", None, blobs.entry(b"new\n"), blobs)
    assert out == Outcome("plain/child.txt", "kept", reason=TYPE_CHANGE)
    assert (hub / "plain").read_bytes() == b"file\n"


def _snapshot(*folders):
    return {folder: sorted(os.listdir(folder)) for folder in folders}


@pytest.mark.parametrize(
    ("path", "reason"),
    [
        ("../x", UNSAFE_PATH),
        ("/abs-skill-hub-test", UNSAFE_PATH),
        ("a/../../x", UNSAFE_PATH),
        ("link/x", SYMLINK),
        ("", UNSAFE_PATH),
        (".git/hooks/pre-commit", UNSAFE_PATH),
        (".GIT/config", UNSAFE_PATH),
        ("a/.git/config", UNSAFE_PATH),
    ],
    ids=["dotdot", "absolute", "nested-dotdot", "symlink-parent", "empty", "dot-git", "dot-git-case", "nested-dot-git"],
)
def test_unsafe_paths_are_refused(tmp_path, hub, blobs, path, reason):
    (hub / "a").mkdir()
    (hub / "link").symlink_to(tmp_path.parent)
    before = _snapshot(tmp_path, tmp_path.parent)
    out = merge_path(hub, path, None, blobs.entry(b"payload\n"), blobs)
    assert out == Outcome(path, "kept", reason=reason)
    assert _snapshot(tmp_path, tmp_path.parent) == before
    assert not os.path.exists("/abs-skill-hub-test")


def test_exec_bit_follows_kit_only_if_unchanged(hub, blobs):
    path = hub / "run.sh"
    path.write_bytes(b"echo\n")
    path.chmod(0o644)
    out = merge_path(hub, "run.sh", blobs.entry(b"echo\n"), blobs.entry(b"echo\n", "100755"), blobs)
    assert out == Outcome("run.sh", "updated")
    assert os.stat(path).st_mode & 0o111 == 0o111

    other = hub / "mine.sh"
    other.write_bytes(b"old\n")
    other.chmod(0o755)
    out = merge_path(hub, "mine.sh", blobs.entry(b"old\n"), blobs.entry(b"new\n"), blobs)
    assert out == Outcome("mine.sh", "updated")
    assert other.read_bytes() == b"new\n"
    assert os.stat(other).st_mode & 0o777 == 0o755


@pytest.mark.parametrize("code", [255, -9])
def test_merge_failure_leaves_file(hub, blobs, monkeypatch, code):
    ours = text(edit(LINES, i1="ours 2\n"))
    (hub / "f.txt").write_bytes(ours)

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, code, stdout=b"garbage", stderr=b"")

    monkeypatch.setattr(merge.subprocess, "run", fake_run)
    out = merge_path(hub, "f.txt", blobs.entry(text(LINES)), blobs.entry(text(edit(LINES, i17="x\n"))), blobs)
    assert out == Outcome("f.txt", "kept", reason=MERGE_FAILED)
    assert (hub / "f.txt").read_bytes() == ours


def test_git_missing_is_merge_failed(hub, blobs, monkeypatch):
    (hub / "f.txt").write_bytes(b"mine\n")

    def missing(command, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(merge.subprocess, "run", missing)
    out = merge_path(hub, "f.txt", blobs.entry(b"old\n"), blobs.entry(b"new\n"), blobs)
    assert out == Outcome("f.txt", "kept", reason=MERGE_FAILED)
    assert (hub / "f.txt").read_bytes() == b"mine\n"


def test_reasons_say_the_copy_was_kept():
    reasons = (ADOPTER_DELETED, KIT_DELETED_CHANGED, SYMLINK, SUBMODULE, TYPE_CHANGE, BINARY_CONFLICT, UNSAFE_PATH)
    for reason in (*reasons, MERGE_FAILED, merge.UNREADABLE, merge.WRITE_FAILED):
        assert "kept" in reason


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads any file")
def test_unreadable_ours_is_kept(hub, blobs):
    path = hub / "f.txt"
    path.write_bytes(b"mine\n")
    path.chmod(0o000)
    try:
        out = merge_path(hub, "f.txt", blobs.entry(b"old\n"), blobs.entry(b"new\n"), blobs)
    finally:
        path.chmod(0o644)
    assert out == Outcome("f.txt", "kept", reason=merge.UNREADABLE)
    assert path.read_bytes() == b"mine\n"


@pytest.mark.skipif(os.geteuid() == 0, reason="root writes any folder")
def test_failed_write_is_kept(hub, blobs):
    folder = hub / "locked"
    folder.mkdir()
    (folder / "f.txt").write_bytes(b"kit\n")
    folder.chmod(0o555)
    try:
        added = merge_path(hub, "locked/new.txt", None, blobs.entry(b"new\n"), blobs)
        deleted = merge_path(hub, "locked/f.txt", blobs.entry(b"kit\n"), None, blobs)
        updated = merge_path(hub, "locked/f.txt", blobs.entry(b"kit\n"), blobs.entry(b"next\n"), blobs)
    finally:
        folder.chmod(0o755)
    assert added == Outcome("locked/new.txt", "kept", reason=merge.WRITE_FAILED)
    assert deleted == Outcome("locked/f.txt", "kept", reason=merge.WRITE_FAILED)
    assert updated == Outcome("locked/f.txt", "kept", reason=merge.WRITE_FAILED)
    assert sorted(os.listdir(folder)) == ["f.txt"]
    assert (folder / "f.txt").read_bytes() == b"kit\n"
