"""`skill-hub update`: merge a newer kit release into the hub, then rewrite kit.yml and regenerate manifests."""

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from skill_hub.contract import DERIVED_PATHS, KIT_FILE, WORKFLOWS_DIR, is_hub_owned, parse_version
from skill_hub.kitfile import KitFile, read_kit_file, write_kit_file
from skill_hub.kitgit import (
    Entry,
    Version,
    fetch_commit,
    list_kit_tags,
    newer_major,
    read_blob,
    require_clean_repo,
    select_target,
    tree_entries,
)
from skill_hub.manifests import ManifestError, update_manifests
from skill_hub.merge import UNREADABLE, Outcome, merge_path
from skill_hub.qa import run_qa

CURRENT_TAG_MISSING = "the kit repo has no release tag for the version in kit.yml; the update stopped"
TAG_MOVED = (
    "the kit release tag this hub is on now points at a different commit than kit.yml records; the update stopped"
)
NOT_PENDING = "no workflow files are pending; there is nothing to apply"
LOCK_FAILED = "`uv lock` could not regenerate uv.lock; the hub's copy was kept"
WORKFLOWS_COMMAND = "uv run skill-hub update --workflows-only"
LOCK_FILE = "uv.lock"
PYPROJECT = "pyproject.toml"
# Runs on the merged, unreviewed pyproject.toml, possibly holding a write token: never build an sdist (its
# build code would run). A resolution that needs a build fails into LOCK_FAILED and keeps the hub's lock.
UV_LOCK = ["uv", "lock", "--no-build"]
_CHANGELOG_HEADING = re.compile(r"^## \[?(\d+\.\d+\.\d+)", re.MULTILINE)


class UpdateError(Exception):
    """Fixed message only."""


@dataclass
class UpdateResult:
    from_version: str
    to_version: str | None
    outcomes: list[Outcome] = field(default_factory=list)
    pending_workflows: list[str] = field(default_factory=list)
    changelog: str = ""
    manifests_note: str = ""
    qa_errors: int = 0
    qa_warnings: int = 0
    newer_major: int | None = None


def _text(version: Version) -> str:
    return ".".join(map(str, version))


def run_update(
    root: Path,
    *,
    major: bool = False,
    skip_workflows: bool = False,
    workflows_only: bool = False,
    check_only: bool = False,
) -> UpdateResult:
    kit = read_kit_file(root)
    if workflows_only:
        return _apply_workflows(root, kit)
    current = parse_version(kit.version)
    if not check_only:
        require_clean_repo(root)
    tags = list_kit_tags(kit.repo)
    if current not in tags:
        raise UpdateError(CURRENT_TAG_MISSING)
    if kit.commit and tags[current] != kit.commit:
        raise UpdateError(TAG_MOVED)
    target = select_target(tags, current, major)
    result = UpdateResult(kit.version, target and _text(target), newer_major=newer_major(tags, target or current))
    if check_only or target is None:
        return result

    fetch_commit(root, kit.repo, current, tags[current])
    fetch_commit(root, kit.repo, target, tags[target])
    base, new = tree_entries(root, tags[current]), tree_entries(root, tags[target])
    workflow_base = base
    if kit.pending:
        fetch_commit(root, kit.repo, parse_version(kit.workflows_version), kit.workflows_commit)
        workflow_base = tree_entries(root, kit.workflows_commit)

    paths = set(base) | set(new) | {p for p in workflow_base if p.startswith(WORKFLOWS_DIR)}
    for path in sorted(p for p in paths if _is_kit_owned(p)):
        if path.startswith(WORKFLOWS_DIR):
            if skip_workflows:
                if workflow_base.get(path) != new.get(path):
                    result.pending_workflows.append(path)
                continue
            result.outcomes.append(_merge(root, path, workflow_base.get(path), new.get(path)))
        else:
            result.outcomes.append(_merge(root, path, base.get(path), new.get(path)))
    if LOCK_FILE in base or LOCK_FILE in new:
        pyproject = next((o for o in result.outcomes if o.path == PYPROJECT), None)
        pyproject_changed = pyproject is not None and pyproject.action in {"updated", "added", "conflict"}
        result.outcomes.append(_update_lock(root, base.get(LOCK_FILE), new.get(LOCK_FILE), pyproject_changed))

    if skip_workflows and kit.pending:
        pair = (kit.workflows_version, kit.workflows_commit)
    elif skip_workflows and result.pending_workflows:  # equal workflow files make the target a correct base
        pair = (kit.version, tags[current])
    else:
        pair = ("", "")
    write_kit_file(root, KitFile(kit.repo, result.to_version, tags[target], *pair))
    result.changelog = _changelog(_blob_text(root, new.get("CHANGELOG.md")), current, target)
    _finish(root, result)
    return result


def _apply_workflows(root: Path, kit: KitFile) -> UpdateResult:
    """Apply workflow files an earlier update held back: base workflows_commit, target commit."""
    if not kit.pending:
        raise UpdateError(NOT_PENDING)
    require_clean_repo(root)
    fetch_commit(root, kit.repo, parse_version(kit.workflows_version), kit.workflows_commit)
    fetch_commit(root, kit.repo, parse_version(kit.version), kit.commit)
    base, new = tree_entries(root, kit.workflows_commit), tree_entries(root, kit.commit)
    result = UpdateResult(kit.workflows_version, kit.version)
    for path in sorted(p for p in set(base) | set(new) if p.startswith(WORKFLOWS_DIR) and _is_kit_owned(p)):
        result.outcomes.append(_merge(root, path, base.get(path), new.get(path)))
    write_kit_file(root, KitFile(kit.repo, kit.version, kit.commit))
    _finish(root, result)
    return result


def _is_kit_owned(path: str) -> bool:
    return not is_hub_owned(path) and path != KIT_FILE and path not in DERIVED_PATHS


def _merge(root: Path, path: str, base: Entry | None, target: Entry | None) -> Outcome:
    return merge_path(root, path, base, target, lambda blob: read_blob(root, blob))


def _update_lock(root: Path, base: Entry | None, target: Entry | None, pyproject_changed: bool) -> Outcome:
    """Derived file: take the kit's lock if the hub never changed it, else regenerate it with `uv lock`."""
    lock = root / LOCK_FILE
    try:
        ours = lock.read_bytes() if lock.is_file() else None
    except OSError:
        return Outcome(LOCK_FILE, "kept", reason=UNREADABLE)
    theirs_base = read_blob(root, base.blob) if base else None
    if ours == theirs_base:
        return _merge(root, LOCK_FILE, base, target)
    if base == target and not pyproject_changed:
        return Outcome(LOCK_FILE, "unchanged")
    try:
        done = subprocess.run(UV_LOCK, cwd=root, capture_output=True, check=False)
        ok = done.returncode == 0
    except OSError:
        ok = False
    now = lock.read_bytes() if lock.is_file() else None
    if not ok:
        if now != ours:  # put the hub's copy back exactly as it was
            if ours is None:
                lock.unlink()
            else:
                lock.write_bytes(ours)
        return Outcome(LOCK_FILE, "kept", reason=LOCK_FAILED)
    return Outcome(LOCK_FILE, "unchanged" if now == ours else "updated")


def _finish(root: Path, result: UpdateResult) -> None:
    try:
        update_manifests(root)
    except ManifestError as exc:
        result.manifests_note = str(exc)
    qa = run_qa(root)
    result.qa_errors, result.qa_warnings = len(qa.errors), len(qa.warnings)


def _blob_text(root: Path, entry: Entry | None) -> str:
    if entry is None:
        return ""
    try:
        return read_blob(root, entry.blob).decode("utf-8")
    except UnicodeDecodeError:
        return ""


def _changelog(text: str, after: Version, upto: Version) -> str:
    """The CHANGELOG.md sections for versions in (after, upto], newest first as the file orders them."""
    headings = list(re.finditer(r"^## ", text, re.MULTILINE))
    sections = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        section = text[heading.start():end]
        match = _CHANGELOG_HEADING.match(section)
        version = parse_version(match[1]) if match else None
        if version is not None and after < version <= upto:
            sections.append(section.strip())
    return "\n\n".join(sections)


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def format_summary(result: UpdateResult) -> str:
    if result.to_version is None:
        lines = [f"The hub is up to date with kit {result.from_version}."]
        if result.newer_major is not None:
            lines.append(f"Kit {result.newer_major}.x is available; update with `skill-hub update --major`.")
        return "\n".join(lines) + "\n"
    out = [f"## Kit update: {result.from_version} → {result.to_version}", ""]
    if result.newer_major is not None:
        out += [f"Kit {result.newer_major}.x is also available; it needs `skill-hub update --major`.", ""]
    out += ["### Changelog", "", result.changelog or "No changelog entries for these releases.", ""]
    changed = [o for o in result.outcomes if o.action in {"updated", "added", "deleted"}]
    if changed:
        out += ["### Changed files", ""] + [f"- `{o.path}`: {o.action}" for o in changed] + [""]
    conflicts = [o for o in result.outcomes if o.action == "conflict"]
    if conflicts:
        out += ["### Conflicts", "", "Resolve the conflict markers in these files before merging:", ""]
        out += [f"- `{o.path}` ({_plural(o.conflicts, 'conflict')})" for o in conflicts] + [""]
    kept = [o for o in result.outcomes if o.action == "kept"]
    if kept:
        out += ["### Files left alone", ""] + [f"- `{o.path}`: {o.reason}" for o in kept] + [""]
    if result.pending_workflows:
        out += ["### Pending workflow files", "", "These workflow files were not updated (no token could write them):"]
        out += [""]
        out += [f"- `{path}`" for path in result.pending_workflows]
        out += ["", f"Apply them locally after merging with `{WORKFLOWS_COMMAND}`, then push.", ""]
    out += ["### Manifests", "", result.manifests_note or "Regenerated the marketplace manifests.", ""]
    out += ["### QA", "", f"QA: {_plural(result.qa_errors, 'error')}, {_plural(result.qa_warnings, 'warning')}"]
    return "\n".join(out) + "\n"


def render_update_outputs(result: UpdateResult) -> str:
    major = "" if result.newer_major is None else str(result.newer_major)
    changed = "false" if result.to_version is None else "true"
    return f"target={result.to_version or ''}\nnewer_major={major}\nchanged={changed}\n"
