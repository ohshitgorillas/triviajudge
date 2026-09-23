"""The shared machinery both trivia gates run on: input and verdict.

A gate is a prompt, a way of collecting candidates, and a decision about
whether the judge runs at ``Stop``. Reading what a change added, remembering
what the judge passed and printing the verdict are the same for every gate and
live here. Calling the model lives in ``triviajudge.transport``. The flow that
strings them together — screen, chunk, judge, exit code — lives in
``triviajudge.gate``, which imports both.

The repository under judgment is found from the current working directory, not
from this file's own location, so an installed package judges the tree it is
run in.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from fnmatch import fnmatch
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

if TYPE_CHECKING:
    from collections.abc import Callable

CACHE_CAP = 20000

#: Seconds a local ``git`` call may take. It reads objects on this machine, so anything past this is a
#: wedged process rather than a slow one, and a hook that captures output has no way to say it is waiting.
GIT_TIMEOUT = 30

#: Set in the environment of the judge's own ``claude`` call, and read by any gate the
#: inner session's hooks start. The inner session runs in the same working directory as
#: the outer one, so without it a hook mode that shells out to the CLI re-enters itself.
#: ``stop_hook_active`` cannot serve here: it marks the outer turn, not the inner process.
INNER = "TRIVIAJUDGE_INNER"

HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


class NotARepositoryError(RuntimeError):
    """Raised when the working directory is in no git work tree."""


@dataclass(frozen=True)
class Line:
    """One added line, addressed as the judge will echo it back."""

    path: str
    number: int
    text: str

    @property
    def id(self) -> str:
        """``path:line``, the id sent to the judge and printed on a flag."""
        return f"{self.path}:{self.number}"


def inner_session() -> bool:
    """Whether this process runs under a judge's own ``claude`` call, where a hook mode does nothing."""
    return bool(os.environ.get(INNER))


def binary(name: str) -> str:
    """Absolute path of a tool on PATH, or a RuntimeError naming what is missing."""
    if (path := shutil.which(name)) is None:
        raise RuntimeError(f"`{name}` not on PATH")
    return path


@cache
def root() -> Path:
    """The work tree the current directory sits in, or a NotARepositoryError naming that it does not."""
    cmd = [binary("git"), "rev-parse", "--show-toplevel"]
    proc = subprocess.run(  # noqa: S603 — argv is git's own path and two read-only flags, written here
        cmd, capture_output=True, text=True, check=False, timeout=GIT_TIMEOUT
    )
    if proc.returncode != 0:
        raise NotARepositoryError(
            f"{Path.cwd()} is in no git work tree; every input mode reads git objects"
        )
    return Path(proc.stdout.strip())


def git(*args: str) -> str:
    """Stdout of a read-only git command run at the repository root."""
    cmd = [binary("git"), *args]
    finished = subprocess.run(  # noqa: S603 — argv is git's own path and the caller's read-only flags
        cmd, check=True, capture_output=True, text=True, cwd=root(), timeout=GIT_TIMEOUT
    )
    return finished.stdout


def git_diff(*args: str) -> str:
    """Zero-context diff, so every ``+`` line is an added line.

    Pathspecs after ``--`` filter the whole diff instead of limiting it: git
    pairs a moved file with its old path only when it sees both, so a limited
    diff reports a move as a new file and every line of it as added.
    """
    if "--" not in args:
        return git("diff", "-U0", "--no-color", "-M", *args)
    cut = args.index("--")
    specs = args[cut + 1 :]
    whole = git("diff", "-U0", "--no-color", "-M", *args[:cut])
    sections = re.split(r"(?m)^(?=diff --git )", whole)
    return "".join(part for part in sections if matches(new_path(part), specs))


def new_path(section: str) -> str:
    """The post-image path of one file's diff section, empty when it adds nothing."""
    for raw in section.splitlines():
        if raw.startswith("+++ "):
            return raw[4:].removeprefix("b/")
    return ""


def matches(path: str, specs: tuple[str, ...]) -> bool:
    """Whether a path falls under any of git's literal, directory or glob pathspecs."""
    return bool(path) and any(
        path == spec or path.startswith(spec.rstrip("/") + "/") or fnmatch(path, spec)
        for spec in specs
    )


def added_lines(diff: str) -> list[Line]:
    """Every added line in a unified diff, with the path and new-file line number."""
    out: list[Line] = []
    path = ""
    number = 0
    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            path = raw[4:].removeprefix("b/")
        elif match := HUNK.match(raw):
            number = int(match.group(1))
        elif raw.startswith("+"):
            out.append(Line(path, number, raw[1:]))
            number += 1
        elif not raw.startswith("-"):
            number += 1
    return out


def from_records(path: Path) -> list[Line]:
    """Calibration input: one ``path:line<TAB>text`` record per line."""
    out: list[Line] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        ident, _, text = raw.partition("\t")
        file, _, number = ident.rpartition(":")
        out.append(Line(file, int(number), text))
    return out


def report(lines: list[Line], flags: list[dict[str, str]], out: TextIO) -> bool:
    """Print every flag against its line; whether anything was flagged."""
    by_id = {line.id: line for line in lines}
    for flag in flags:
        line = by_id.get(str(flag.get("id")))
        where = line.id if line else f"?:{flag.get('id')}"
        print(f"{where}: {flag.get('reason', '').strip()}", file=out)
        if line:
            print(f"    {line.text.strip()}", file=out)
    if flags:
        print(
            f"\n{len(flags)} line(s) narrate history. State what holds now, or delete the remark.",
            file=out,
        )
    else:
        print(f"[ok] {len(lines)} line(s) state what holds now", file=out)
    return bool(flags)


def stop_already_ran() -> bool:
    """Read whether the Stop payload on stdin says this hook has already blocked this turn."""
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return False
    return bool(payload.get("stop_hook_active"))


def digest(line: Line) -> str:
    """Hash of the line's text alone, so a passed line stays passed wherever it moves."""
    return hashlib.sha1(
        line.text.strip().encode("utf-8"), usedforsecurity=False
    ).hexdigest()


def clean_cache(cache_path: Path) -> list[str]:
    """Digests of lines the judge has already passed, oldest first; empty when there is no cache."""
    try:
        seen = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [str(item) for item in seen] if isinstance(seen, list) else []


def remember_clean(
    lines: list[Line], flags: list[dict[str, str]], cache_path: Path
) -> None:
    """Append every line the judge passed to the cache, capped at the newest ``CACHE_CAP``."""
    flagged = {str(flag.get("id")) for flag in flags}
    seen = clean_cache(cache_path)
    known = set(seen)
    for line in lines:
        if line.id not in flagged and digest(line) not in known:
            seen.append(digest(line))
            known.add(digest(line))
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(seen[-CACHE_CAP:]) + "\n", encoding="utf-8")


@dataclass(frozen=True)
class Gate:
    """What one trivia gate brings to the shared run flow: its text, its input, its cache.

    ``cache`` is last and optional because a gate that does not judge at
    ``Stop`` never reaches the only call that writes one.

    ``batch`` is how many lines one call carries, 0 for all of them, and
    ``exhaustive`` says the prompt asks for a verdict per input id rather than
    for the hits alone. Both default to the unchunked hit-list shape, so a gate
    names them only where its prompt asks for the other.

    ``screen_fails`` is whether the pattern screen's own complaints fail the
    run on their own, whatever the judge returns and even when the screen
    leaves nothing for the judge to see. Default False keeps the comment
    gate's commit rule, where ``archaeology.py`` is the authority on its own
    complaints; markdown has no such authority.
    """

    prompt: str
    collect: Callable[[argparse.Namespace], tuple[list[Line], list[str]]]
    empty: str
    judge_at_stop: bool
    cache: Path | None = None
    batch: int = 0
    exhaustive: bool = False
    screen_fails: bool = False


def parse_args(doc: str, noun: str) -> argparse.Namespace:
    """Read the five input modes both trivia gates take."""
    parser = argparse.ArgumentParser(
        description=doc, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("files", nargs="*", help=f"staged {noun} (pre-commit)")
    parser.add_argument(
        "--head", action="store_true", help=f"judge the {noun} HEAD added"
    )
    parser.add_argument(
        "--stop",
        action="store_true",
        help="judge the working tree; reads a Stop payload on stdin",
    )
    parser.add_argument("--lines", help="calibration records, path:line<TAB>text")
    parser.add_argument("--out", help="write the judge's raw answer here")
    return parser.parse_args()
