"""Split SKILL.md text into its YAML frontmatter and markdown body."""

from dataclasses import dataclass

DELIMITER = "---"
FRONTMATTER_LINE_OFFSET = 1  # frontmatter line n is file line n + 1


class FrontmatterError(ValueError):
    pass


@dataclass(frozen=True)
class SplitResult:
    frontmatter: str
    body: str


def split_frontmatter(text: str) -> SplitResult:
    lines = text.removeprefix("\ufeff").replace("\r\n", "\n").split("\n")
    if lines[0] != DELIMITER:
        raise FrontmatterError("must start with a '---' line")
    for index in range(1, len(lines)):
        if lines[index] == DELIMITER:
            return SplitResult("\n".join(lines[1:index]), "\n".join(lines[index + 1 :]))
    raise FrontmatterError("frontmatter is not closed by a '---' line")
