"""The table of values that belong to the repository being judged, not to the gates.

A gate's file scope, its skip lists, where it keeps its clean-line cache and
which model it asks are properties of the tree it runs over. They arrive from
that tree: a ``[tool.triviajudge]`` table in its ``pyproject.toml``, or a
``.triviajudge.toml`` at its root, whichever is found first.

Three readings at the edges, each a default rather than an error:

* No file, or a file with no table, or a table missing a key — the built-in
  defaults below, and the gate runs. A repository that says nothing gets the
  behavior a repository would most likely ask for.
* A file present but unparseable — the gate fails. Falling back to defaults
  over a corrupt table would judge a different file set than the one the
  repository asked for, and say nothing about it.
* A key present but empty — the empty value, honoured. An empty ``excluded``
  is the widest scope and an empty ``suffixes`` the narrowest; both are legal
  things to ask for, and neither is reachable by omitting a key.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from functools import cache
from pathlib import Path

#: Where a repository may state its table, in the order they are tried.
SOURCES = ("pyproject.toml", ".triviajudge.toml")

#: The table key inside ``pyproject.toml``; a ``.triviajudge.toml`` holds the keys at its top level.
SECTION = ("tool", "triviajudge")


@dataclass(frozen=True)
class Settings:
    """Everything a gate reads about the repository it is judging."""

    #: Markdown files with their own gate or their own owner-held style rule.
    md_skip: frozenset[str] = frozenset({"CHANGELOG.md"})
    #: Source files the comment gate does not read, by repo-relative path.
    comment_skip: frozenset[str] = frozenset()
    #: Suffixes the comment gate reads. Empty means it reads nothing.
    suffixes: tuple[str, ...] = (".py", ".js", ".css")
    #: Path prefixes the comment gate stays out of. Empty means it stays out of nothing.
    excluded: tuple[str, ...] = ("tests/",)
    #: Directory holding the clean-line caches, relative to the repository root.
    cache_dir: str = ".triviajudge"
    #: The model the judge asks.
    model: str = "claude-haiku-4-5"


def _table(start: Path) -> dict[str, object]:
    """The raw table from the first source that carries one; empty when none does."""
    for name in SOURCES:
        path = start / name
        if not path.is_file():
            continue
        try:
            loaded = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise RuntimeError(f"{path} is present but unreadable, refusing to judge on defaults: {exc}") from exc
        found: object = loaded
        for key in SECTION if name == "pyproject.toml" else ():
            if not isinstance(found, dict) or key not in found:
                found = {}
                break
            found = found[key]
        if isinstance(found, dict) and found:
            return found
    return {}


def read(start: Path) -> Settings:
    """The settings a repository states, over the defaults for everything it leaves out."""
    table = _table(start)
    known = {f.name for f in Settings.__dataclass_fields__.values()}
    unknown = sorted(set(table) - known)
    if unknown:
        raise RuntimeError(f"unknown triviajudge settings: {', '.join(unknown)}")
    given: dict[str, object] = {}
    for name, value in table.items():
        default = getattr(Settings(), name)
        if isinstance(default, frozenset):
            given[name] = frozenset(value)  # type: ignore[call-overload]
        elif isinstance(default, tuple):
            given[name] = tuple(value)  # type: ignore[call-overload]
        else:
            given[name] = value
    return Settings(**given)  # type: ignore[arg-type]


@cache
def settings() -> Settings:
    """The table for the repository the current directory sits in."""
    from triviajudge.core import root

    return read(root())


def cache_path(name: str) -> Path:
    """Absolute path of one clean-line cache file inside the judged repository."""
    from triviajudge.core import root

    return root() / settings().cache_dir / name
