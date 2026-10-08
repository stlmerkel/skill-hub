"""Strict YAML loading: safe types only, no duplicate or merge keys, errors as data."""

from dataclasses import dataclass

import yaml

_MERGE_TAG = "tag:yaml.org,2002:merge"


@dataclass(frozen=True)
class YamlError:
    message: str  # fixed text; never contains input
    line: int | None  # 1-based, relative to the loaded text


@dataclass(frozen=True)
class Loaded:
    data: object = None
    key_lines: tuple[tuple[str | None, int], ...] = ()
    error: YamlError | None = None


class _Problem(Exception):
    def __init__(self, message: str, mark: yaml.Mark):
        super().__init__(message)
        self.message = message
        self.line = mark.line + 1


class _StrictLoader(yaml.SafeLoader):
    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            if key_node.tag == _MERGE_TAG:
                raise _Problem("uses a merge key (<<), which is not allowed", key_node.start_mark)
            key = self.construct_object(key_node, deep=True)
            try:
                duplicate = key in seen
            except TypeError:
                raise _Problem("has a mapping key that is not a plain value", key_node.start_mark) from None
            if duplicate:
                raise _Problem("has a duplicate key", key_node.start_mark)
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def load_yaml(text: str) -> Loaded:
    loader = _StrictLoader(text)
    try:
        node = loader.get_single_node()
        data = loader.construct_document(node) if node is not None else None
    except _Problem as problem:
        return Loaded(error=YamlError(problem.message, problem.line))
    except yaml.MarkedYAMLError as exc:
        mark = exc.problem_mark or exc.context_mark
        return Loaded(error=YamlError("is not valid YAML", mark.line + 1 if mark else None))
    except (yaml.YAMLError, ValueError, TypeError, OverflowError):
        return Loaded(error=YamlError("contains a value YAML cannot construct (for example an invalid date); quote it", None))
    finally:
        loader.dispose()

    key_lines: tuple[tuple[str | None, int], ...] = ()
    if isinstance(node, yaml.MappingNode):
        key_lines = tuple(
            (key.value if isinstance(key, yaml.ScalarNode) else None, key.start_mark.line + 1)
            for key, _ in node.value
        )
    return Loaded(data=data, key_lines=key_lines)
