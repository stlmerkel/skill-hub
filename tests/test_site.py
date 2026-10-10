import json
import os
from pathlib import Path

import pytest

from skill_hub.catalog import BuildError
from skill_hub.config import SiteSettings
from skill_hub.site import MARKER_FILE, build_site, render_theme, write_site
from tests.conftest import GOOD_HUB, make_skill, make_theme, skill_md, sync_manifests, write_hub

CATALOG = {
    "schema_version": 1,
    "hub": {
        "name": "acme-skills",
        "display_name": "Acme Skills",
        "owner": "Acme",
        "description": "Skills for Acme.",
        "repo_url": "https://github.com/acme/skills",
    },
    "skills": [
        {
            "name": "alpha",
            "description": "First <b>&",
            "version": "1.0.0",
            "license": None,
            "compatibility": None,
            "links": {
                "source": "https://github.com/acme/skills/tree/HEAD/skills/alpha",
                "changelog": None,
                "release": None,
            },
        }
    ],
}


def render(tmp_path, theme, site=None):
    dest = tmp_path / "dest"
    dest.mkdir(exist_ok=True)
    warnings = render_theme(CATALOG, site or SiteSettings(), theme, dest)
    return dest, warnings


def test_renders_context_and_partials(tmp_path):
    theme = make_theme(tmp_path, index='{% include "_card.j2" %}|{{ site.accent }}\n')
    (theme / "_card.j2").write_text("{% for s in catalog.skills %}{{ s.name }}{% endfor %}", encoding="utf-8")
    dest, warnings = render(tmp_path, theme, SiteSettings(accent="#123456"))
    assert (dest / "index.html").read_text(encoding="utf-8") == "alpha|#123456\n"
    assert warnings == []
    assert not (dest / "_card.j2").exists() and not (dest / "index.html.j2").exists()


def test_autoescape_is_on(tmp_path):
    theme = make_theme(tmp_path, index="{{ catalog.skills[0].description }}")
    dest, _ = render(tmp_path, theme)
    assert (dest / "index.html").read_text(encoding="utf-8") == "First &lt;b&gt;&amp;"


def test_static_files_copied_byte_for_byte_with_subfolders(tmp_path):
    theme = make_theme(tmp_path)
    (theme / "img").mkdir()
    (theme / "img" / "logo.png").write_bytes(bytes(range(256)))
    (theme / "style.css").write_text("body{}", encoding="utf-8")
    dest, _ = render(tmp_path, theme)
    assert (dest / "img" / "logo.png").read_bytes() == bytes(range(256))
    assert (dest / "style.css").read_text(encoding="utf-8") == "body{}"


def test_dot_entries_are_not_copied(tmp_path):
    theme = make_theme(tmp_path)
    (theme / ".DS_Store").write_bytes(b"x")
    (theme / ".git").mkdir()
    (theme / ".git" / "config").write_text("x", encoding="utf-8")
    dest, warnings = render(tmp_path, theme)
    assert sorted(p.name for p in dest.iterdir()) == ["index.html"] and warnings == []


def test_symlinks_are_skipped_with_warnings(tmp_path):
    theme = make_theme(tmp_path)
    (tmp_path / "real.css").write_text("x", encoding="utf-8")
    (tmp_path / "real-dir").mkdir()
    os.symlink(tmp_path / "real.css", theme / "linked.css")
    os.symlink(tmp_path / "real-dir", theme / "linked-dir")
    dest, warnings = render(tmp_path, theme)
    assert not (dest / "linked.css").exists() and not (dest / "linked-dir").exists()
    assert warnings == [
        "theme/linked-dir: symlink in theme is not followed",
        "theme/linked.css: symlink in theme is not followed",
    ]


def test_undefined_variable_names_file_and_line(tmp_path):
    theme = make_theme(tmp_path, index="<p>ok</p>\n{{ skil.name }}\n")
    with pytest.raises(BuildError) as caught:
        render(tmp_path, theme)
    assert str(caught.value).startswith("theme/index.html.j2:2: ")
    assert "skil" in str(caught.value)


def test_undefined_in_a_partial_names_the_partial(tmp_path):
    theme = make_theme(tmp_path, index='{% include "_part.j2" %}\n')
    (theme / "_part.j2").write_text("a\nb\n{{ catalog.nope }}\n", encoding="utf-8")
    with pytest.raises(BuildError, match=r"^theme/_part\.j2:3: "):
        render(tmp_path, theme)


def test_syntax_error_names_file_and_line(tmp_path):
    theme = make_theme(tmp_path, index="fine\n{% if %}\n")
    with pytest.raises(BuildError, match=r"^theme/index\.html\.j2:2: "):
        render(tmp_path, theme)


def test_missing_partial_names_it(tmp_path):
    theme = make_theme(tmp_path, index='{% include "_missing.j2" %}\n')
    with pytest.raises(BuildError, match=r"^theme/index\.html\.j2:1: .*_missing\.j2"):
        render(tmp_path, theme)


def test_template_that_is_not_utf8(tmp_path):
    theme = make_theme(tmp_path)
    (theme / "index.html.j2").write_bytes(b"\xff\xfe")
    with pytest.raises(BuildError, match="a template could not be read"):
        render(tmp_path, theme)


@pytest.mark.parametrize(
    ("index", "error"),
    [
        ("ok\n{{ 1/0 }}\n", "ZeroDivisionError"),
        ("ok\n{{ catalog.hub.name + 1 }}\n", "TypeError"),
        ('ok\n{% include "index.html.j2" %}\n', "RecursionError"),
    ],
)
def test_runtime_template_error_names_file_and_line(tmp_path, index, error):
    theme = make_theme(tmp_path, index=index)
    catalog = {**CATALOG, "hub": {**CATALOG["hub"], "name": "zyzzyva-hub-name"}}
    with pytest.raises(BuildError) as caught:
        render_theme(catalog, SiteSettings(), theme, tmp_path)
    message = str(caught.value)
    assert message.startswith("theme/index.html.j2:2: ")
    assert error in message
    assert "zyzzyva" not in message


def test_missing_theme_folder(tmp_path):
    with pytest.raises(BuildError, match="theme folder nope not found"):
        render(tmp_path, tmp_path / "nope")


def test_theme_without_entry_point(tmp_path):
    (tmp_path / "bare").mkdir()
    with pytest.raises(BuildError, match="theme bare has no index.html.j2"):
        render(tmp_path, tmp_path / "bare")


@pytest.mark.parametrize("name", ["index.html", "catalog.json"])
def test_static_file_colliding_with_generated_output(tmp_path, name):
    theme = make_theme(tmp_path)
    (theme / name).write_text("x", encoding="utf-8")
    with pytest.raises(BuildError, match=f"would overwrite the generated {name}"):
        render(tmp_path, theme)


def themed_hub(root, theme="theme"):
    make_theme(root, theme, index="{% for s in catalog.skills %}<p>{{ s.name }}</p>{% endfor %}\n")
    write_hub(root, GOOD_HUB + f'site:\n  theme: "{theme}"\n')
    make_skill(root)
    sync_manifests(root)
    return root


def entries(folder):
    return sorted(p.name for p in folder.iterdir())


def test_write_site_into_a_new_folder(tmp_path):
    theme = make_theme(tmp_path)
    out = tmp_path / "out"
    assert write_site(CATALOG, SiteSettings(), theme, out) == []
    assert entries(out) == [".skill-hub-build", "catalog.json", "index.html"]
    assert json.loads((out / "catalog.json").read_text(encoding="utf-8")) == CATALOG
    assert (out / "catalog.json").read_bytes().endswith(b"}\n")


def test_write_site_into_an_empty_folder(tmp_path):
    (tmp_path / "out").mkdir()
    write_site(CATALOG, SiteSettings(), make_theme(tmp_path), tmp_path / "out")
    assert (tmp_path / "out" / "index.html").is_file()


def test_marked_folder_is_replaced_and_stale_files_go(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / MARKER_FILE).write_bytes(b"")
    (out / "stale.html").write_text("old", encoding="utf-8")
    write_site(CATALOG, SiteSettings(), make_theme(tmp_path), out)
    assert "stale.html" not in entries(out) and (out / "index.html").is_file()


def test_unmarked_folder_is_refused_and_untouched(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "notes.txt").write_text("mine", encoding="utf-8")
    with pytest.raises(BuildError, match="was not created by skill-hub build"):
        write_site(CATALOG, SiteSettings(), make_theme(tmp_path), out)
    assert entries(out) == ["notes.txt"]


def test_out_that_is_a_file_is_refused(tmp_path):
    (tmp_path / "out").write_text("x", encoding="utf-8")
    with pytest.raises(BuildError, match="was not created by skill-hub build"):
        write_site(CATALOG, SiteSettings(), make_theme(tmp_path), tmp_path / "out")


def test_out_that_is_a_symlink_is_refused(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (real / MARKER_FILE).write_bytes(b"")
    os.symlink(real, tmp_path / "out")
    with pytest.raises(BuildError, match="was not created by skill-hub build"):
        write_site(CATALOG, SiteSettings(), make_theme(tmp_path), tmp_path / "out")
    assert entries(real) == [MARKER_FILE]


def test_out_dot_is_refused(tmp_path, monkeypatch):
    themed_hub(tmp_path)
    monkeypatch.chdir(tmp_path)
    before = entries(tmp_path)
    with pytest.raises(BuildError, match="was not created by skill-hub build"):
        build_site(tmp_path, tmp_path / ".")
    assert entries(tmp_path) == before


def test_render_failure_keeps_previous_output_and_leaves_no_temp_folders(tmp_path):
    good = make_theme(tmp_path, "good")
    out = tmp_path / "out"
    write_site(CATALOG, SiteSettings(), good, out)
    previous = (out / "index.html").read_bytes()
    bad = make_theme(tmp_path, "bad", index="{{ nope }}")
    before = entries(tmp_path)
    with pytest.raises(BuildError):
        write_site(CATALOG, SiteSettings(), bad, out)
    assert (out / "index.html").read_bytes() == previous
    assert entries(tmp_path) == before


def test_build_site_end_to_end(tmp_path):
    root = themed_hub(tmp_path / "hub")
    result = build_site(root, tmp_path / "out")
    assert result.skill_count == 1 and result.warnings == []
    assert (tmp_path / "out" / "index.html").read_text(encoding="utf-8") == "<p>changelog-formatter</p>\n"


def test_build_site_refuses_a_hub_with_qa_errors(tmp_path):
    root = themed_hub(tmp_path / "hub")
    make_skill(root, "foo", skill_md("Foo"))
    with pytest.raises(BuildError, match="QA found"):
        build_site(root, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_theme_folder_as_out_is_refused_and_kept(tmp_path):
    root = themed_hub(tmp_path, theme="site")
    with pytest.raises(BuildError, match="was not created by skill-hub build"):
        build_site(root, root / "site")
    assert (root / "site" / "index.html.j2").is_file()


def test_theme_inside_a_marked_out_is_refused_and_kept(tmp_path):
    root = themed_hub(tmp_path)
    build_site(root, root / "site")
    theme = make_theme(root / "site", "mytheme")
    write_hub(root, GOOD_HUB + 'site:\n  theme: "site/mytheme"\n')
    with pytest.raises(BuildError, match="overlaps the theme folder"):
        build_site(root, root / "site")
    assert entries(theme) == ["index.html.j2"]
    assert (root / "site" / MARKER_FILE).is_file()


def test_out_inside_the_theme_is_refused_and_nothing_is_created(tmp_path):
    theme = make_theme(tmp_path)
    with pytest.raises(BuildError, match="overlaps the theme folder"):
        write_site(CATALOG, SiteSettings(), theme, theme / "out")
    assert entries(theme) == ["index.html.j2"]
    assert entries(tmp_path) == ["theme"]


def test_lone_surrogate_is_a_build_error_not_a_traceback(tmp_path):
    root = themed_hub(tmp_path / "hub")
    escape = "\\" + "ud800"  # built by concatenation so no tool turns it into a character (L72)
    text = skill_md().replace('description: "Formats', f'description: "{escape} Formats')
    (root / "skills" / "changelog-formatter" / "SKILL.md").write_text(text, encoding="utf-8")
    with pytest.raises(BuildError):
        build_site(root, tmp_path / "out")
    assert not (tmp_path / "out").exists()
    assert [p.name for p in tmp_path.iterdir()] == ["hub"]


@pytest.mark.parametrize("failing_call", [1, 2])
def test_failed_swap_rolls_back_and_leaves_no_temp_folders(tmp_path, monkeypatch, failing_call):
    theme = make_theme(tmp_path)
    out = tmp_path / "out"
    write_site(CATALOG, SiteSettings(), theme, out)
    previous = (out / "index.html").read_bytes()
    real_rename = Path.rename
    calls = []

    def flaky(self, target):
        calls.append(self)
        if len(calls) == failing_call:
            raise PermissionError("denied")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", flaky)
    with pytest.raises(BuildError, match="could not replace the output folder"):
        write_site(CATALOG, SiteSettings(), theme, out)
    monkeypatch.undo()
    assert (out / "index.html").read_bytes() == previous
    assert (out / MARKER_FILE).is_file()
    assert entries(tmp_path) == ["out", "theme"]
