"""Template self-test: the shipped defaults pass QA with only the H6 warnings.

Runs on a committed snapshot, never on the adopter's live hub.yml or skills/, so
renaming the hub or replacing the example cannot break this test. When the
template's shipped defaults change, update the snapshot in the same commit.
"""

from pathlib import Path

from skill_hub.config import check_hub
from skill_hub.deploy import DeploySettings
from skill_hub.qa import run_qa

SNAPSHOT = Path(__file__).parent / "fixtures" / "default-clone"


def test_default_clone_passes_with_only_identity_warnings():
    result = run_qa(SNAPSHOT)
    assert result.errors == []
    assert sorted(f.check_id for f in result.warnings) == ["H6", "H6"]
    assert result.skill_count == 1


def test_default_clone_builds(tmp_path):
    from skill_hub.site import build_site

    assert build_site(SNAPSHOT, tmp_path / "out").skill_count == 1


def test_default_clone_never_deploys():
    assert check_hub(SNAPSHOT)[1].deploy == DeploySettings()
