"""Repo self-test: no committed kit file contains a literal U+FEFF.

File-write tools can turn a "\ufeff" escape into the invisible character itself, and ruff
only notices when it lands in code, not in a string or comment. Adopter-owned files are
excluded: QA deliberately tolerates a BOM in SKILL.md and hub.yml, and an adopter's editor
may add one to any of them.
"""

import subprocess
from pathlib import Path

from skill_hub.config import HUB_FILE
from skill_hub.manifests import MANIFEST_PATHS
from skill_hub.skills import SKILLS_DIR
from skill_hub.releases import RELEASE_CONFIG, RELEASE_MANIFEST

ROOT = Path(__file__).parent.parent
BOM = b"\xef\xbb\xbf"
ADOPTER_FILES = {HUB_FILE, RELEASE_CONFIG, RELEASE_MANIFEST, *MANIFEST_PATHS}


def test_no_literal_bom_in_tracked_files():
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    kit_files = [p for p in tracked if p not in ADOPTER_FILES and not p.startswith(f"{SKILLS_DIR}/")]
    # A kit update deletes files before the deletion is staged: git still lists them, the disk no longer has them.
    offenders = [p for p in kit_files if (ROOT / p).is_file() and BOM in (ROOT / p).read_bytes()]
    assert offenders == [], "write U+FEFF as the escape \\ufeff instead"
