"""Field-path resolution for comparison protocols.

Protocols use a small dotted path language:

    experiment                       top-level key
    config.jobs                      nested key
    trials[].b1.params.f0            every element of the ``trials`` list
    trials[].b1.params.*             every key of that object
    conditions[].success.rate        nested aggregate field

`[]` expands a list; `*` expands a mapping (or a list) by key/index. Matching is read-only
unless the caller explicitly uses :func:`delete_concrete`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

_NAME = r"[A-Za-z_][A-Za-z0-9_]*"
_PATH_SEGMENT = re.compile(rf"^(?:(\*)|({_NAME}))(\[\])?$")
_CONCRETE_TOKEN = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


class PathError(ValueError):
    """Raised when a protocol path is malformed."""


@dataclass(frozen=True)
class Segment:
    """One parsed protocol-path segment."""

    name: str
    expand_list: bool = False


@dataclass(frozen=True)
class Match:
    """One concrete resolution result: JSON path plus value."""

    path: str
    value: Any


def parse_path(path: str) -> tuple[Segment, ...]:
    """Parses a protocol path, rejecting malformed segments."""
    if not isinstance(path, str) or not path:
        raise PathError("protocol path must be a non-empty string")
    if path.startswith(".") or path.endswith(".") or ".." in path:
        raise PathError(f"malformed protocol path {path!r}")
    segments: list[Segment] = []
    for raw in path.split("."):
        match = _PATH_SEGMENT.fullmatch(raw)
        if match is None:
            raise PathError(f"malformed protocol path segment {raw!r} in {path!r}")
        name = match.group(1) or match.group(2)
        segments.append(Segment(name=name, expand_list=match.group(3) is not None))
    return tuple(segments)


def resolve(document: Any, path: str) -> list[Match]:
    """Resolves a protocol path against a parsed JSON document."""
    matches = [Match("", document)]
    for segment in parse_path(path):
        next_matches: list[Match] = []
        for match in matches:
            value = match.value
            if segment.name == "*":
                if isinstance(value, Mapping):
                    for key, item in value.items():
                        next_matches.append(Match(_join(match.path, str(key)), item))
                elif isinstance(value, list):
                    for index, item in enumerate(value):
                        next_matches.append(Match(_index(match.path, index), item))
                continue
            if not isinstance(value, Mapping):
                continue
            if segment.name not in value:
                continue
            child = value[segment.name]
            if segment.expand_list:
                if not isinstance(child, list):
                    continue
                for index, item in enumerate(child):
                    next_matches.append(
                        Match(_index(_join(match.path, segment.name), index), item)
                    )
            else:
                next_matches.append(Match(_join(match.path, segment.name), child))
        matches = next_matches
    return matches


def flatten(value: Any, base: str = "") -> dict[str, Any]:
    """Flattens a JSON value to leaf paths. Empty containers count as leaves."""
    leaves: dict[str, Any] = {}

    def walk(item: Any, path: str) -> None:
        if isinstance(item, Mapping):
            if not item:
                leaves[path or "$"] = item
                return
            for key, child in item.items():
                walk(child, _join(path, str(key)))
        elif isinstance(item, list):
            if not item:
                leaves[path or "$"] = item
                return
            for index, child in enumerate(item):
                walk(child, _index(path, index))
        else:
            leaves[path] = item

    walk(value, base)
    return leaves


def delete_concrete(document: Any, concrete_path: str) -> bool:
    """Removes one concrete path (for example ``config.jobs``) from a document."""
    tokens: list[tuple[str, str]] = []
    for match in _CONCRETE_TOKEN.finditer(concrete_path):
        if match.group(1) is not None:
            tokens.append(("key", match.group(1)))
        else:
            tokens.append(("index", match.group(2)))
    if not tokens:
        return False
    current = document
    for kind, token in tokens[:-1]:
        if kind == "key":
            if not isinstance(current, Mapping) or token not in current:
                return False
            current = current[token]
        else:
            if not isinstance(current, list):
                return False
            index = int(token)
            if index >= len(current):
                return False
            current = current[index]
    kind, token = tokens[-1]
    if kind == "key":
        if not isinstance(current, dict) or token not in current:
            return False
        del current[token]
        return True
    if not isinstance(current, list):
        return False
    index = int(token)
    if index >= len(current):
        return False
    del current[index]
    return True


def delete_order(path: str) -> tuple[tuple[int, int, str], ...]:
    """Sort key for deleting list elements from the highest index first."""
    order: list[tuple[int, int, str]] = []
    for match in _CONCRETE_TOKEN.finditer(path):
        if match.group(1) is not None:
            order.append((0, 0, match.group(1)))
        else:
            order.append((1, int(match.group(2)), ""))
    return tuple(order)


def path_specificity(path: str) -> tuple[int, int]:
    """Sort key for overlapping patterns: more literal segments win."""
    literal_segments = 0
    literal_characters = 0
    for raw in path.split("."):
        name = raw[:-2] if raw.endswith("[]") else raw
        if name != "*":
            literal_segments += 1
            literal_characters += len(name)
    return literal_segments, literal_characters


def _join(prefix: str, name: str) -> str:
    return f"{prefix}.{name}" if prefix else name


def _index(prefix: str, index: int) -> str:
    return f"{prefix}[{index}]"


def unique_sorted(paths: Iterable[str]) -> list[str]:
    """Deduplicates concrete paths and returns a deterministic order."""
    return sorted(set(paths))
