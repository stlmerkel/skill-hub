"""Build throwaway kit and hub git repos for tests (identity passed with -c, never global config)."""

import os
import subprocess
from pathlib import Path

from skill_hub.kitfile import KitFile, write_kit_file

_ID = [
    "-c", "user.name=Test",
    "-c", "user.email=test@example.com",
    "-c", "commit.gpgsign=false",
    "-c", "tag.gpgsign=false",
]


class Exec(bytes):
    """File content committed with the executable bit."""


class Link(bytes):
    """A symlink; the bytes are its target."""


def git(path: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", *_ID, "-C", str(path), *args], capture_output=True, text=True, check=True
    )
    return done.stdout.strip()


def _write(root: Path, rel: str, data: bytes | None) -> None:
    target = root / rel
    if data is None:
        if target.is_symlink() or target.exists():
            target.unlink()
        return
    if target.is_symlink() or target.exists():
        target.unlink()
    target.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, Link):
        os.symlink(data.decode(), target)
        return
    target.write_bytes(bytes(data))
    target.chmod(0o755 if isinstance(data, Exec) else 0o644)


def commit_files(path: Path, files: dict[str, bytes | None], message: str) -> str:
    for rel, data in files.items():
        _write(path, rel, data)
    git(path, "add", "-A")
    git(path, "commit", "-q", "--allow-empty", "-m", message)
    return git(path, "rev-parse", "HEAD")


def make_kit_repo(path: Path, releases: list[tuple[str, dict[str, bytes | None]]]) -> str:
    """One commit per release, tagged kit-v<version>; returns the repo's file:// URL."""
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "-b", "main")
    for version, files in releases:
        commit_files(path, files, f"release {version}")
        git(path, "tag", f"kit-v{version}")
    return path.resolve().as_uri()


def make_hub(path: Path, kit_url: str, version: str, files: dict[str, bytes]) -> Path:
    """A committed hub repo holding `files` plus a kit.yml naming `version`."""
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "-b", "main")
    write_kit_file(path, KitFile(repo=kit_url, version=version))
    commit_files(path, dict(files), "hub")
    return path
