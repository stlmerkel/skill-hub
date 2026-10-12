import json

import pytest

from skill_hub.catalog import SCHEMA_VERSION, BuildError, build_catalog, require_clean_qa
from tests.conftest import GOOD_HUB, make_skill, skill_md, sync_manifests, write_hub

REPO = "https://github.com/acme/skills"


def catalog_for(root):
    return build_catalog(root, require_clean_qa(root))


def test_full_shape_and_key_order(tmp_path):
    write_hub(tmp_path)
    make_skill(tmp_path)
    sync_manifests(tmp_path)
    catalog = catalog_for(tmp_path)
    assert list(catalog) == ["schema_version", "hub", "skills"]
    assert catalog["schema_version"] == SCHEMA_VERSION == 1
    assert catalog["hub"] == {
        "name": "acme-skills",
        "display_name": "Acme Skills",
        "owner": "Acme Platform Team",
        "description": "Skills for Acme engineers.",
        "repo_url": REPO,
    }
    assert catalog["skills"] == [
        {
            "name": "changelog-formatter",
            "description": "Formats changelog entries. Use when the user asks to write or tidy a changelog.",
            "version": "1.0.0",
            "license": None,
            "compatibility": None,
            "links": {
                "source": f"{REPO}/tree/HEAD/skills/changelog-formatter",
                "changelog": None,
                "release": None,
            },
            "install": {
                "claude_code": "claude plugin install changelog-formatter --marketplace acme/skills",
                "gh_skill": None,
            },
        }
    ]
    assert list(catalog["skills"][0]) == [
        "name", "description", "version", "license", "compatibility", "links", "install",
    ]
    assert json.loads(json.dumps(catalog)) == catalog


def test_skills_sorted_by_name(tmp_path):
    write_hub(tmp_path)
    for name in ("zeta-skill", "alpha-skill", "mid-skill"):
        make_skill(tmp_path, name)
    sync_manifests(tmp_path)
    assert [s["name"] for s in catalog_for(tmp_path)["skills"]] == ["alpha-skill", "mid-skill", "zeta-skill"]


def test_license_and_compatibility_when_present(tmp_path):
    write_hub(tmp_path)
    extra = 'license: "MIT"\ncompatibility: "Needs git on PATH"\n'
    make_skill(tmp_path, text=skill_md(extra_frontmatter=extra))
    sync_manifests(tmp_path)
    (skill,) = catalog_for(tmp_path)["skills"]
    assert skill["license"] == "MIT" and skill["compatibility"] == "Needs git on PATH"


def test_changelog_link_only_with_a_changelog_file(tmp_path):
    write_hub(tmp_path)
    make_skill(tmp_path, "with-log")
    make_skill(tmp_path, "without-log")
    (tmp_path / "skills" / "with-log" / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    (tmp_path / "skills" / "without-log" / "CHANGELOG.md").mkdir()  # a folder is not a changelog
    sync_manifests(tmp_path)
    links = {s["name"]: s["links"]["changelog"] for s in catalog_for(tmp_path)["skills"]}
    assert links == {"with-log": f"{REPO}/blob/HEAD/skills/with-log/CHANGELOG.md", "without-log": None}


def test_release_link_from_the_manifest(tmp_path):
    write_hub(tmp_path)
    make_skill(tmp_path, "released")
    make_skill(tmp_path, "unreleased")
    packages = {"skills/released": {}, "skills/unreleased": {}}
    (tmp_path / "release-please-config.json").write_text(json.dumps({"packages": packages}), encoding="utf-8")
    (tmp_path / ".release-please-manifest.json").write_text('{"skills/released": "1.0.0"}', encoding="utf-8")
    sync_manifests(tmp_path)
    links = {s["name"]: s["links"]["release"] for s in catalog_for(tmp_path)["skills"]}
    assert links == {"released": f"{REPO}/releases/tag/released-v1.0.0", "unreleased": None}


def test_trailing_slash_on_repo_url_is_dropped(tmp_path):
    write_hub(tmp_path, GOOD_HUB.replace(f"repo_url: {REPO}", f"repo_url: {REPO}/"))
    make_skill(tmp_path)
    sync_manifests(tmp_path)
    catalog = catalog_for(tmp_path)
    assert catalog["skills"][0]["links"]["source"] == f"{REPO}/tree/HEAD/skills/changelog-formatter"


def test_bom_and_crlf_skill_builds_clean(tmp_path):
    write_hub(tmp_path)
    skill_dir = make_skill(tmp_path)
    text = skill_md().replace("\n", "\r\n").encode("utf-8")
    (skill_dir / "SKILL.md").write_bytes(bytes([0xEF, 0xBB, 0xBF]) + text)
    sync_manifests(tmp_path)
    (skill,) = catalog_for(tmp_path)["skills"]
    assert "\r" not in skill["description"] and skill["name"] == "changelog-formatter"


def test_qa_error_blocks_the_build(tmp_path):
    write_hub(tmp_path)
    make_skill(tmp_path, "foo", skill_md("Foo"))
    with pytest.raises(BuildError, match=r"QA found 1 error; run `skill-hub qa`"):
        require_clean_qa(tmp_path)


def test_qa_warnings_do_not_block(tmp_path):
    write_hub(tmp_path, GOOD_HUB.replace("name: acme-skills", "name: my-skill-hub"))
    make_skill(tmp_path)
    sync_manifests(tmp_path)
    assert require_clean_qa(tmp_path).name == "my-skill-hub"


def test_install_gh_skill_pinned_once_released(tmp_path):
    write_hub(tmp_path)
    make_skill(tmp_path, "released")
    (tmp_path / "release-please-config.json").write_text(
        json.dumps({"packages": {"skills/released": {}}}), encoding="utf-8"
    )
    (tmp_path / ".release-please-manifest.json").write_text('{"skills/released": "1.0.0"}', encoding="utf-8")
    sync_manifests(tmp_path)
    (skill,) = catalog_for(tmp_path)["skills"]
    assert skill["install"]["gh_skill"] == "gh skill install acme/skills released@released-v1.0.0"


def test_install_is_null_for_a_non_github_repo(tmp_path):
    write_hub(tmp_path, GOOD_HUB.replace("https://github.com/acme/skills", "https://gitlab.com/acme/skills"))
    make_skill(tmp_path)
    sync_manifests(tmp_path)
    (skill,) = catalog_for(tmp_path)["skills"]
    assert skill["install"] is None
