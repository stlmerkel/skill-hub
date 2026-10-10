import os

import pytest

from skill_hub.catalog import BuildError
from skill_hub.config import SiteSettings
from skill_hub.site import render_theme
from tests.conftest import make_theme

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
                "source": "https://github.com/acme/skills/tree/HEAD/src/alpha",
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
    with pytest.raises(BuildError, match="could not be read as UTF-8"):
        render(tmp_path, theme)


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
