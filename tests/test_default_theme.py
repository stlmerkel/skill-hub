from html.parser import HTMLParser
from pathlib import Path

from skill_hub.site import build_site
from tests.conftest import GOOD_HUB, make_skill, skill_md, write_hub

SNAPSHOT = Path(__file__).parent / "fixtures" / "default-clone"
HOSTILE = "<script>alert(\"x\")</script> 'q' & </article><b>"


class Page(HTMLParser):
    def __init__(self, html: str):
        super().__init__()
        self.tags: list[tuple[str, dict]] = []
        self.text: list[str] = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.text.append(data)

    def all(self, tag):
        return [attrs for name, attrs in self.tags if name == tag]


def page(out) -> Page:
    return Page((out / "index.html").read_text(encoding="utf-8"))


def test_default_clone_builds_one_card(tmp_path):
    result = build_site(SNAPSHOT, tmp_path / "out")
    assert result.skill_count == 1 and result.warnings == []
    built = page(tmp_path / "out")
    assert [a["data-name"] for a in built.all("article")] == ["example-skill"]
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == [".skill-hub-build", "catalog.json", "index.html"]


def test_page_is_self_contained(tmp_path):
    build_site(SNAPSHOT, tmp_path / "out")
    built = page(tmp_path / "out")
    assert built.all("link") == [] and built.all("img") == []
    assert [s for s in built.all("script") if "src" in s] == []
    assert len(built.all("script")) == 1


def test_search_is_hidden_until_script_runs(tmp_path):
    build_site(SNAPSHOT, tmp_path / "out")
    built = page(tmp_path / "out")
    (search,) = [a for a in built.all("div") if a.get("id") == "search"]
    assert "hidden" in search
    (label,) = built.all("label")
    assert label["for"] == "search-input"
    (status,) = [a for a in built.all("p") if a.get("id") == "no-results"]
    assert status["aria-live"] == "polite"


def test_hostile_text_is_escaped_everywhere(tmp_path):
    hub = GOOD_HUB.replace("display_name: Acme Skills", f"display_name: '{HOSTILE.replace(chr(39), chr(39) * 2)}'")
    write_hub(tmp_path, hub)
    description = HOSTILE.replace("\\", "\\\\").replace('"', '\\"')
    text = skill_md().replace(
        'description: "Formats changelog entries. Use when the user asks to write or tidy a changelog."',
        f'description: "{description}"',
    )
    make_skill(tmp_path, text=text)
    build_site(tmp_path, tmp_path / "out")
    built = page(tmp_path / "out")
    assert len(built.all("script")) == 1
    assert [t for t, _ in built.tags].count("article") == 1
    (card,) = built.all("article")
    assert card["data-description"] == HOSTILE
    assert HOSTILE in "".join(built.text)


def test_logo_accent_license_and_links(tmp_path):
    hub = GOOD_HUB + 'site:\n  accent: "#123456"\n  logo_url: "https://cdn.example.test/logo.png"\n'
    write_hub(tmp_path, hub)
    make_skill(tmp_path, text=skill_md(extra_frontmatter='license: "MIT"\n'))
    (tmp_path / "src" / "changelog-formatter" / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    build_site(tmp_path, tmp_path / "out")
    html = (tmp_path / "out" / "index.html").read_text(encoding="utf-8")
    built = Page(html)
    (logo,) = built.all("img")
    assert logo["src"] == "https://cdn.example.test/logo.png" and logo["alt"] == "Acme Skills"
    assert "--accent: #123456;" in html
    assert "License: MIT" in "".join(built.text)
    hrefs = [a["href"] for a in built.all("a")]
    base = "https://github.com/acme/skills"
    assert f"{base}/tree/HEAD/src/changelog-formatter" in hrefs
    assert f"{base}/blob/HEAD/src/changelog-formatter/CHANGELOG.md" in hrefs
    assert not any("/releases/tag/" in href for href in hrefs)
    assert "None" not in hrefs and "" not in hrefs


def test_default_accent_when_unset(tmp_path):
    build_site(SNAPSHOT, tmp_path / "out")
    assert "--accent: #4f46e5;" in (tmp_path / "out" / "index.html").read_text(encoding="utf-8")
