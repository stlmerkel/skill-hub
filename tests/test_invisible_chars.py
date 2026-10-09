"""Repo self-test: no committed file outside src/ contains a literal U+FEFF.

File-write tools can turn a "\ufeff" escape into the invisible character itself, and ruff
only notices when it lands in code, not in a string or comment. src/ is excluded because
QA deliberately tolerates a BOM in an adopter's SKILL.md.
"""

import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent
BOM = b"\xef\xbb\xbf"


def test_no_literal_bom_in_tracked_files():
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    offenders = [p for p in tracked if not p.startswith("src/") and BOM in (ROOT / p).read_bytes()]
    assert offenders == [], "write U+FEFF as the escape \\ufeff instead"
