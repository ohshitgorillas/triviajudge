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
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

#: Where a repository may state its table, in the order they are tried.
SOURCES = ("pyproject.toml", ".triviajudge.toml")

#: The table key inside ``pyproject.toml``; a ``.triviajudge.toml`` holds the keys at its top level.
SECTION = ("tool", "triviajudge")

#: The cache a ``triviajudge-sweep --baseline`` run writes, read by the markdown gate at
#: ``Stop`` beside its own. It is named here rather than in ``sweep`` so the gate can read
#: it without importing the sweep, which imports the gate.
SWEEP_CACHE = "sweep-clean.json"


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
    #: Which transport carries the judge's question: ``claude`` for the CLI in print mode,
    #: ``local`` for an OpenAI-compatible server named by ``base_url``. The default keeps a
    #: repository that says nothing on the CLI.
    backend: str = "claude"
    #: Root of the OpenAI-compatible server the ``local`` backend posts to, without a trailing
    #: slash — ``http://127.0.0.1:8080``. Empty under the ``claude`` backend, which reads it not
    #: at all.
    base_url: str = ""
    #: Name of the environment variable holding the bearer token for ``base_url``. Empty sends
    #: no ``Authorization`` header, which is what a local server on the loopback wants. The
    #: token itself is never written here.
    api_key_env: str = ""
    #: Path appended to ``base_url`` for the chat-completions call. The OpenAI default is what
    #: llama.cpp and vLLM serve. A hosted endpoint that serves the same API under a prefix of
    #: its own names its path here, so reaching one is a line in this table rather than a change
    #: to the transport.
    chat_path: str = "/v1/chat/completions"
    #: Lines per call at every gate's judge, and in a sweep. A judge reads a bounded number of the lines one
    #: call carries, so the chunk is what holds recall steady between runs over the same
    #: input. 0 asks every collected line in one call.
    gate_batch: int = 20
    #: Concurrent calls a gate makes over its chunks, capped at half the cores of the host it
    #: runs on. It is what keeps a chunked gate from costing the turn one call's latency per
    #: chunk.
    gate_parallel: int = 4
    #: Concurrent CLI calls in a sweep. One by default; a sweep caps whatever it is given at
    #: half the cores of the host it runs on.
    sweep_parallel: int = 1
    #: The model a sweep asks. Separate from ``model`` because a sweep asks it thousands of
    #: times over prose nobody is waiting on, and a gate asks it once on a commit.
    sweep_model: str = "claude-haiku-4-5"
    #: Whether the markdown judge's model call runs at ``Stop``. False makes that call a
    #: no-op, not the whole hook: the pattern screen in ``md_screen`` still runs and still
    #: fails the turn on its own complaints. A repository that will not spend a nested call
    #: on every turn that adds markdown turns it off, and keeps the commit and HEAD modes,
    #: which judge the same lines on finished work.
    md_judge_at_stop: bool = True


def _table(start: Path) -> dict[str, object]:
    """The raw table from the first source that carries one; empty when none does."""
    for name in SOURCES:
        path = start / name
        if not path.is_file():
            continue
        try:
            loaded = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise RuntimeError(
                f"{path} is present but unreadable, refusing to judge on defaults: {exc}"
            ) from exc
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
            given[name] = frozenset(cast("Iterable[str]", value))
        elif isinstance(default, tuple):
            given[name] = tuple(cast("Iterable[str]", value))
        else:
            given[name] = value
    return Settings(**given)  # type: ignore[arg-type]  # — keys checked above, values hold their fields' types


@cache
def settings() -> Settings:
    """The table for the repository the current directory sits in."""
    from triviajudge.core import root  # noqa: PLC0415 — core reads this table, so the import lands at call time

    return read(root())


def cache_path(name: str) -> Path:
    """Absolute path of one clean-line cache file inside the judged repository."""
    from triviajudge.core import root  # noqa: PLC0415 — core reads this table, so the import lands at call time

    return root() / settings().cache_dir / name
