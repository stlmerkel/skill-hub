import pytest

from skill_hub.frontmatter import FrontmatterError, split_frontmatter


def test_splits_frontmatter_and_body():
    result = split_frontmatter("---\nname: a\n---\n# Title\n")
    assert result.frontmatter == "name: a"
    assert result.body == "# Title\n"


def test_body_may_contain_delimiter():
    result = split_frontmatter("---\nname: a\n---\nintro\n---\nmore\n")
    assert result.frontmatter == "name: a"
    assert result.body == "intro\n---\nmore\n"


def test_bom_and_crlf_tolerated():
    result = split_frontmatter("\ufeff---\r\nname: a\r\n---\r\nbody\r\n")
    assert result.frontmatter == "name: a"
    assert result.body == "body\n"


@pytest.mark.parametrize("text", ["name: a\n---\n", "", "--- \nname: a\n---\n", "\n---\nname: a\n---\n"])
def test_missing_opening_delimiter(text):
    with pytest.raises(FrontmatterError, match="must start"):
        split_frontmatter(text)


def test_unclosed_frontmatter():
    with pytest.raises(FrontmatterError, match="not closed"):
        split_frontmatter("---\nname: a\n")
