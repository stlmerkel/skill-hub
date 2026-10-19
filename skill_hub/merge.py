"""Three-way merge of one kit-owned file.

B = the kit file at the hub's release, T = the kit file at the target release, O = the hub's copy.
"""

import os
import stat
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from skill_hub.kitgit import Entry, KitGitError

ADOPTER_DELETED = "the hub deleted this file and the kit changed it; the deletion was kept"
KIT_DELETED_CHANGED = "the kit deleted this file but the hub changed it; the hub's copy was kept"
SYMLINK = "a symlink is involved (in the kit or in the hub's path); the hub's copy was kept"
SUBMODULE = "the kit has a submodule here; the hub's copy was kept"
TYPE_CHANGE = "a file and a folder clash at this path; the hub's copy was kept"
BINARY_CONFLICT = "both the hub and the kit changed this binary file; the hub's copy was kept"
UNSAFE_PATH = "the path points outside the hub; nothing was written and the hub's copy was kept"
MERGE_FAILED = "git could not merge this file; the hub's copy was kept"
UNREADABLE = "the hub's copy could not be read; the hub's copy was kept"
WRITE_FAILED = "the file could not be written; the hub's copy was kept"

REGULAR_MODES = {"100644", "100755"}
MERGE_LABELS = ["-L", "your hub", "-L", "kit (old)", "-L", "kit (new)"]


@dataclass(frozen=True)
class Outcome:
    path: str
    action: str  # unchanged | updated | added | deleted | conflict | kept
    conflicts: int = 0
    reason: str = ""


class _Kept(Exception):
    """Internal: carries a fixed reason up to merge_path."""


def _is_text(data: bytes) -> bool:
    if b"\0" in data:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _entry_reason(entry: Entry | None) -> str | None:
    if entry is None or entry.mode in REGULAR_MODES:
        return None
    if entry.mode == "120000":
        return SYMLINK
    if entry.mode == "160000":
        return SUBMODULE
    return TYPE_CHANGE


def _target(root: Path, path: str) -> Path:
    """The hub path for `path`, after every check that must pass before a write."""
    parts = PurePosixPath(path).parts
    if not parts or path.startswith("/") or "\\" in path or ".." in parts:
        raise _Kept(UNSAFE_PATH)
    current = root
    for part in parts[:-1]:
        current = current / part
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            break
        except OSError:
            raise _Kept(UNREADABLE) from None
        if stat.S_ISLNK(info.st_mode):
            raise _Kept(SYMLINK)
        if not stat.S_ISDIR(info.st_mode):
            raise _Kept(TYPE_CHANGE)
    full = root.joinpath(*parts)
    try:
        info = os.lstat(full)
    except FileNotFoundError:
        info = None
    except OSError:
        raise _Kept(UNREADABLE) from None
    if info is not None:
        if stat.S_ISLNK(info.st_mode):
            raise _Kept(SYMLINK)
        if not stat.S_ISREG(info.st_mode):
            raise _Kept(TYPE_CHANGE)
    if not full.resolve().is_relative_to(root.resolve()):
        raise _Kept(UNSAFE_PATH)
    return full


def _git_merge(ours: bytes, base: bytes, theirs: bytes) -> tuple[bytes, int]:
    """Run git merge-file on copies outside the hub; returns (merged bytes, conflict count)."""
    with tempfile.TemporaryDirectory() as scratch:
        files = []
        for name, data in (("ours", ours), ("base", base), ("theirs", theirs)):
            file = Path(scratch) / name
            file.write_bytes(data)
            files.append(str(file))
        try:
            done = subprocess.run(
                ["git", "merge-file", "-p", *MERGE_LABELS, *files], capture_output=True, check=False
            )
        except OSError:
            raise _Kept(MERGE_FAILED) from None
    if not 0 <= done.returncode <= 127:
        raise _Kept(MERGE_FAILED)
    return done.stdout, done.returncode


def _write(full: Path, data: bytes, mode: int) -> None:
    """Temp file in the same folder, then os.replace: O is either old or new, never half written."""
    temp = None
    try:
        full.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(dir=full.parent, prefix=".skill-hub-")
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.chmod(temp, mode)
        os.replace(temp, full)
    except OSError:
        if temp is not None:
            try:
                os.unlink(temp)
            except OSError:
                pass
        raise _Kept(WRITE_FAILED) from None


def _with_exec(mode: int, executable: bool) -> int:
    """Set or clear the executable bits, keeping O's other permission bits."""
    if executable:
        return mode | ((mode & 0o444) >> 2)
    return mode & ~0o111


def merge_path(
    root: Path, path: str, base: Entry | None, target: Entry | None, blob: Callable[[str], bytes]
) -> Outcome:
    """Decide and perform the update of one kit-owned path. Never raises for an expected condition."""
    try:
        return _merge(root, path, base, target, blob)
    except _Kept as kept:
        return Outcome(path, "kept", reason=str(kept))


def _merge(root: Path, path: str, base: Entry | None, target: Entry | None, blob: Callable[[str], bytes]) -> Outcome:
    for entry in (base, target):
        reason = _entry_reason(entry)
        if reason:
            raise _Kept(reason)
    full = _target(root, path)
    try:
        b = blob(base.blob) if base else None
        t = blob(target.blob) if target else None
    except KitGitError:
        raise _Kept(MERGE_FAILED) from None
    try:
        o = full.read_bytes() if full.exists() else None
        o_mode = stat.S_IMODE(os.lstat(full).st_mode) if o is not None else None
    except OSError:
        raise _Kept(UNREADABLE) from None

    if t is None:
        if o is None:
            return Outcome(path, "unchanged")  # B present, T absent, O absent (or nothing at all)
        if o != b:
            raise _Kept(KIT_DELETED_CHANGED)
        try:
            os.unlink(full)
        except OSError:
            raise _Kept(WRITE_FAILED) from None
        return Outcome(path, "deleted")

    t_exec = target.mode == "100755"
    if o is None:
        if b is None:
            _write(full, t, 0o755 if t_exec else 0o644)
            return Outcome(path, "added")
        if b != t or base.mode != target.mode:
            raise _Kept(ADOPTER_DELETED)
        return Outcome(path, "unchanged")

    # O present. The executable bit follows the kit only when O's matches B's.
    o_exec = bool(o_mode & 0o100)
    new_exec = t_exec if base is not None and o_exec == (base.mode == "100755") else o_exec
    new_mode = _with_exec(o_mode, new_exec)

    conflicts = 0
    if base is not None and o == b:
        merged = t
    elif o == t or (base is not None and b == t):
        merged = o
    elif all(_is_text(data) for data in (o, t, b or b"")):
        merged, conflicts = _git_merge(o, b or b"", t)
    else:
        raise _Kept(BINARY_CONFLICT)

    if merged == o and new_mode == o_mode:
        return Outcome(path, "unchanged")
    _write(full, merged, new_mode)
    if conflicts:
        return Outcome(path, "conflict", conflicts=conflicts)
    return Outcome(path, "updated")
