"""Kit-only checks that committed fixtures still equal the kit's live files.

A hub may delete deploy targets or change its defaults, so these run only where the repository variable
SKILL_HUB_KIT_RELEASES is "true" (the kit repo), passed to the pytest step through env.
"""

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("SKILL_HUB_KIT_RELEASES") != "true", reason="kit repo only")

REPO = Path(__file__).parent.parent
FIXTURES = Path(__file__).parent / "fixtures"


def test_workflow_fixtures_match_live_workflows():
    for fixture in sorted((FIXTURES / "kit-workflows").iterdir()):
        live = REPO / ".github" / "workflows" / fixture.name
        assert fixture.read_bytes() == live.read_bytes(), fixture.name


def test_default_clone_matches_root_defaults():
    clone = FIXTURES / "default-clone"
    assert (clone / "hub.yml").read_bytes() == (REPO / "hub.yml").read_bytes()
    skill = clone / "skills" / "example-skill"
    live = REPO / "skills" / "example-skill"
    # The live folder also holds a release-generated CHANGELOG.md the snapshot deliberately leaves out.
    for fixture in sorted(p for p in skill.rglob("*") if p.is_file()):
        name = fixture.relative_to(skill)
        assert fixture.read_bytes() == (live / name).read_bytes(), str(name)
