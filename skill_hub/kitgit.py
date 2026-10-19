"""Git plumbing for kit updates: list release tags, fetch a release as data, read its tree."""

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from skill_hub.contract import is_valid_kit_repo, parse_kit_tag, KIT_TAG_PREFIX

Version = tuple[int, int, int]


class KitGitError(Exception):
    """Fixed message only: never echoes git's stderr, a path or a repo URL."""


@dataclass(frozen=True)
class Entry:
    mode: str
    blob: str


def _git(root: Path | None, *args: str, failure: str) -> bytes:
    command = ["git", *(["-C", str(root)] if root else []), *args]
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        done = subprocess.run(command, capture_output=True, env=env, check=False)
    except FileNotFoundError:
        raise KitGitError("git is not installed or not on PATH") from None
    if done.returncode != 0:
        raise KitGitError(failure)
    return done.stdout


def _require_repo(repo: str) -> None:
    if not is_valid_kit_repo(repo):
        raise KitGitError("the kit repo in kit.yml is not a valid kit repo URL")


def _ref(version: Version) -> str:
    return f"{KIT_TAG_PREFIX}{version[0]}.{version[1]}.{version[2]}"


def list_kit_tags(repo: str) -> dict[Version, str]:
    """Kit release versions mapped to their commit SHA (annotated tags are peeled)."""
    _require_repo(repo)
    out = _git(None, "ls-remote", "--tags", "--", repo, failure="could not list the kit repo's release tags")
    direct: dict[Version, str] = {}
    peeled: dict[Version, str] = {}
    for line in out.decode("utf-8", errors="replace").splitlines():
        sha, _, ref = line.partition("\t")
        if not ref.startswith("refs/tags/"):
            continue
        name = ref[len("refs/tags/"):]
        target = direct
        if name.endswith("^{}"):
            name, target = name[:-3], peeled
        version = parse_kit_tag(name)
        if version is not None:
            target[version] = sha
    return {**direct, **peeled}


def select_target(tags: dict[Version, str], current: Version, major: bool) -> Version | None:
    candidates = [v for v in tags if v > current and (major or v[0] == current[0])]
    return max(candidates) if candidates else None


def newer_major(tags: dict[Version, str], current: Version) -> int | None:
    majors = [v[0] for v in tags if v[0] > current[0]]
    return max(majors) if majors else None


def require_clean_repo(root: Path) -> None:
    top = _git(root, "rev-parse", "--show-toplevel", failure="this folder is not a git repository")
    # A hub nested in another repo would fetch kit refs into, and read status from, the outer repo.
    if Path(os.fsdecode(top.strip())).resolve() != root.resolve():
        raise KitGitError("this folder is not the top of its own git repository")
    out = _git(root, "status", "--porcelain", failure="could not read the working tree status")
    if out.strip():
        raise KitGitError("the working tree has uncommitted changes; commit or stash them first")


def fetch_commit(root: Path, repo: str, version: Version, expected: str) -> None:
    _require_repo(repo)
    tag = _ref(version)
    local = f"refs/skill-hub/{tag}"
    _git(
        root, "fetch", "--no-tags", "--force", "--", repo, f"refs/tags/{tag}:{local}",
        failure="could not fetch the kit release",
    )
    got = _git(root, "rev-parse", f"{local}^{{commit}}", failure="could not resolve the fetched kit release")
    if got.decode().strip() != expected:
        raise KitGitError("the fetched kit release does not match the commit recorded for it")


def tree_entries(root: Path, commit: str) -> dict[str, Entry]:
    out = _git(
        root, "ls-tree", "-r", "-z", "--full-tree", commit, failure="could not read the kit release's files"
    )
    entries: dict[str, Entry] = {}
    for record in out.split(b"\0"):
        if not record:
            continue
        meta, _, path = record.partition(b"\t")
        mode, _, blob = meta.decode().split(" ")
        entries[os.fsdecode(path)] = Entry(mode, blob)
    return entries


def read_blob(root: Path, blob: str) -> bytes:
    return _git(root, "cat-file", "blob", blob, failure="could not read a file from the kit release")
