# skill_hub/qa.py
"""Skill checks (S1-S14), run checks (R1-R4), and the QA runner."""

import os
import stat
import warnings
from dataclasses import dataclass
from pathlib import Path

from skill_hub.config import check_hub
from skill_hub.contract import (
    COMPATIBILITY_MAX,
    DESCRIPTION_MAX,
    NAME_RULE,
    SCAFFOLD_DESCRIPTION,
    SPEC_KEYS,
    is_blank,
    is_valid_name,
    is_valid_semver,
    type_name,
)
from skill_hub.findings import ERROR, WARNING, Finding
from skill_hub.frontmatter import FRONTMATTER_LINE_OFFSET, FrontmatterError, split_frontmatter
from skill_hub.secrets import scan_text
from skill_hub.yamlutil import load_yaml

SKILL_FILE = "SKILL.md"
SRC_DIR = "src"
BINARY_WARN_BYTES = 1_000_000


@dataclass(frozen=True)
class QaResult:
    findings: list[Finding]
    skill_count: int

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.level == ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.level == WARNING]


def run_qa(root: Path) -> QaResult:
    findings, config = check_hub(root)
    allow_keys = config.allow_keys if config is not None else ()

    src = root / SRC_DIR
    if not src.exists():
        return QaResult([*findings, Finding(ERROR, "R1", SRC_DIR, "src/ not found")], 0)
    if not src.is_dir():
        return QaResult([*findings, Finding(ERROR, "R1", SRC_DIR, "src is not a directory")], 0)

    skills = []
    try:
        entries = sorted(src.iterdir())
    except OSError:
        return QaResult([*findings, Finding(ERROR, "R1", SRC_DIR, "src/ could not be read")], 0)
    for entry in entries:
        if entry.name.startswith("."):
            continue
        rel = f"{SRC_DIR}/{entry.name}"
        # os.lstat, not Path.is_dir(): on Python 3.14 pathlib returns False on EACCES instead of raising.
        try:
            mode = os.lstat(entry).st_mode
            is_symlink = stat.S_ISLNK(mode)
            is_dir = stat.S_ISDIR(mode)
        except OSError:
            findings.append(Finding(ERROR, "S13", rel, "entry could not be read"))
            continue
        if is_symlink:
            findings.append(Finding(WARNING, "R4", rel, "symlink in src/ is not followed"))
        elif is_dir:
            skills.append(entry)
        else:
            findings.append(Finding(WARNING, "R3", rel, "file directly in src/ is not a skill; skills are directories"))
    if not skills:
        findings.append(Finding(ERROR, "R2", SRC_DIR, "src/ contains no skill directories"))

    for skill_dir in skills:
        findings.extend(check_skill(skill_dir, allow_keys))
    return QaResult(findings, len(skills))


def check_skill(skill_dir: Path, allow_keys: tuple[str, ...]) -> list[Finding]:
    rel = f"{SRC_DIR}/{skill_dir.name}"
    try:
        (skill_dir / SKILL_FILE).lstat()
    except FileNotFoundError:
        pass
    except OSError:
        return [Finding(ERROR, "S13", rel, "directory could not be read")]
    return [*_check_skill_md(skill_dir, rel, allow_keys), *_check_files(skill_dir, rel)]


def _check_skill_md(skill_dir: Path, rel: str, allow_keys: tuple[str, ...]) -> list[Finding]:
    path = skill_dir / SKILL_FILE
    md = f"{rel}/{SKILL_FILE}"

    def error(check_id, message, line=None):
        return Finding(ERROR, check_id, md, message, line)

    if not path.exists() and not path.is_symlink():
        return [Finding(ERROR, "S1", rel, "SKILL.md not found")]
    if path.is_symlink() or not path.is_file():
        return [error("S1", "SKILL.md is not a regular file")]
    try:
        raw = path.read_bytes()
    except OSError:
        return []  # reported as S13 by _check_files
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return [error("S2", "SKILL.md is not valid UTF-8")]
    try:
        split = split_frontmatter(text)
    except FrontmatterError as exc:
        return [error("S2", f"SKILL.md {exc}")]

    findings = []
    if is_blank(split.body):
        findings.append(Finding(WARNING, "S11", md, "SKILL.md has no instructions after the frontmatter"))

    loaded = load_yaml(split.frontmatter)
    if loaded.error is not None:
        line = loaded.error.line + FRONTMATTER_LINE_OFFSET if loaded.error.line else None
        return [*findings, error("S3", f"frontmatter {loaded.error.message}", line)]
    if not isinstance(loaded.data, dict):
        return [*findings, error("S3", "frontmatter must be a mapping")]

    return [*findings, *_check_fields(loaded.data, loaded.key_lines, skill_dir.name, md, allow_keys)]


def _check_fields(fm: dict, key_lines, dir_name: str, md: str, allow_keys: tuple[str, ...]) -> list[Finding]:
    findings = []

    def error(check_id, message, line=None):
        findings.append(Finding(ERROR, check_id, md, message, line))

    # S4 name
    name = fm.get("name")
    if "name" not in fm:
        error("S4", "name is missing")
    elif not isinstance(name, str):
        error("S4", f"name must be a string, found {type_name(name)}; quote it")
    elif not is_valid_name(name):
        error("S4", NAME_RULE)
    elif name != dir_name:
        error("S4", f'name does not match directory "{dir_name}"')

    # S5 description
    description = fm.get("description")
    if "description" not in fm:
        error("S5", "description is missing")
    elif not isinstance(description, str):
        error("S5", f"description must be a string, found {type_name(description)}; quote it")
    elif is_blank(description):
        error("S5", "description is empty")
    elif len(description) > DESCRIPTION_MAX:
        error("S5", f"description is {len(description)} characters; the limit is {DESCRIPTION_MAX}")

    # S14 scaffold placeholder
    if isinstance(description, str) and description.strip() == SCAFFOLD_DESCRIPTION:
        findings.append(Finding(WARNING, "S14", md, "description is still the scaffold placeholder; replace it"))

    # S6 top-level keys, checked as written
    allowed = SPEC_KEYS | set(allow_keys)
    for raw_key, line in key_lines:
        if raw_key in allowed:
            continue
        file_line = line + FRONTMATTER_LINE_OFFSET
        if raw_key == "version":
            message = 'move "version" to metadata.version; a top-level version is not part of the Agent Skills spec'
        else:
            message = "unexpected top-level key; allowed are the Agent Skills spec keys plus qa.allow_keys in hub.yml"
        error("S6", message, file_line)

    # S7 metadata.version
    metadata = fm.get("metadata")
    version = metadata.get("version") if isinstance(metadata, dict) else None
    if not isinstance(metadata, dict) or "version" not in metadata:
        error("S7", "metadata.version is missing")
    elif not isinstance(version, str):
        error("S7", f"metadata.version must be a string, found {type_name(version)}; quote it")
    elif not is_valid_semver(version):
        error("S7", "metadata.version is not a valid SemVer 2.0.0 version (for example \"1.2.3\")")

    # S8 other field types
    if "metadata" in fm:
        if not isinstance(metadata, dict):
            error("S8", f"metadata must be a mapping, found {type_name(metadata)}")
        else:
            for key, value in metadata.items():
                if not isinstance(key, str):
                    error("S8", f"metadata keys must be strings, found {type_name(key)}")
                elif key != "version" and not isinstance(value, str):
                    error("S8", f"metadata values must be strings, found {type_name(value)}; quote it")
    if "compatibility" in fm:
        compatibility = fm["compatibility"]
        if not isinstance(compatibility, str):
            error("S8", f"compatibility must be a string, found {type_name(compatibility)}; quote it")
        elif is_blank(compatibility) or len(compatibility) > COMPATIBILITY_MAX:
            error("S8", f"compatibility must be 1-{COMPATIBILITY_MAX} characters and not blank")
    for key in ("license", "allowed-tools"):
        if key in fm and not isinstance(fm[key], str):
            error("S8", f"{key} must be a string, found {type_name(fm[key])}; quote it")

    return findings


def _check_files(skill_dir: Path, rel: str) -> list[Finding]:
    findings = []

    def on_error(err: OSError) -> None:
        path_rel = _rel(skill_dir, Path(err.filename), rel) if err.filename else rel
        findings.append(Finding(ERROR, "S13", path_rel, "directory could not be read"))

    for dirpath, dirnames, filenames in os.walk(skill_dir, onerror=on_error):
        base = Path(dirpath)
        for name in sorted(dirnames):
            try:
                linked = (base / name).is_symlink()
            except OSError:
                linked = False  # os.walk reports the unreadable directory itself via onerror
            if linked:
                dirnames.remove(name)
                link_rel = _rel(skill_dir, base / name, rel)
                findings.append(Finding(WARNING, "S12", link_rel, "symlink is not followed or scanned"))
        dirnames.sort()
        for name in sorted(filenames):
            path = base / name
            path_rel = _rel(skill_dir, path, rel)
            try:
                mode = path.lstat().st_mode
            except OSError:
                findings.append(Finding(ERROR, "S13", path_rel, "file could not be read"))
                continue
            if stat.S_ISLNK(mode):
                findings.append(Finding(WARNING, "S12", path_rel, "symlink is not followed or scanned"))
                continue
            if not stat.S_ISREG(mode):
                findings.append(Finding(WARNING, "S12", path_rel, "not a regular file; not scanned"))
                continue
            try:
                raw = path.read_bytes()
            except OSError:
                findings.append(Finding(ERROR, "S13", path_rel, "file could not be read"))
                continue
            if path.suffix == ".py":
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        compile(raw, str(path), "exec")
                except (SyntaxError, ValueError, MemoryError, RecursionError) as exc:
                    lineno = getattr(exc, "lineno", None)
                    findings.append(Finding(ERROR, "S9", path_rel, "Python file does not compile", lineno))
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                if len(raw) > BINARY_WARN_BYTES:
                    message = "binary file over 1 MB was not scanned for secrets"
                    findings.append(Finding(WARNING, "S10", path_rel, message))
                continue
            for hit in scan_text(text):
                message = (
                    f"possible secret ({hit.kind}); remove it, "
                    "or mark a deliberate example with 'skill-hub: allow-secret'"
                )
                findings.append(Finding(ERROR, "S10", path_rel, message, hit.line))
    return findings


def _rel(skill_dir: Path, path: Path, rel: str) -> str:
    inner = path.relative_to(skill_dir).as_posix()
    return rel if inner == "." else f"{rel}/{inner}"


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def format_report(result: QaResult) -> str:
    lines = []
    for f in sorted(result.findings, key=lambda f: (f.path, f.line or 0, f.check_id)):
        label = "ERROR" if f.level == ERROR else "WARN"
        location = f"{f.path}:{f.line}" if f.line else f.path
        lines.append(f"{label} {f.check_id} {location}: {f.message}")
    lines.append(
        f"QA: {_plural(len(result.errors), 'error')}, {_plural(len(result.warnings), 'warning')}"
        f" across {_plural(result.skill_count, 'skill')}"
    )
    return "\n".join(lines)
