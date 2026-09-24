"""Gate: a changelog entry reads as the release note, not as the fix's autobiography.

The changelog is written by whoever made the change, which in this repo is
usually an agent that has just spent an hour inside the fix and wants to say
all of it. Left alone that produces entries carrying flag names, file paths and
the order a gate does things in — the note the author would write for the
author, not the one a reader hitting the problem needs.

The two passes run in order, as they do for comments. The pattern screen in
``triviajudge.changelog_screen`` holds the mechanical half. A bullet the screen
refuses is already refused, so sending it buys nothing but tokens, and the
judge reads only what the screen leaves. Its complaints fail the run in every
mode: nothing else holds them.

Two scopes divide the work by what each is for. The default judges the bullets
a change adds, one entry at a time, in the five standard modes, and remembers
what it passed in ``changelog-clean.json`` at ``--stop``. ``--release`` judges
the section as a whole before a cut: every bullet in one call, no cache, and a
different question — which entries must not ship beside each other. It refuses
the other modes rather than folding into them, because the two ask different
things of the same text, and it rewrites nothing.

Usage:

* ``triviajudge-changelog FILE...`` judges the bullets the staged diff adds
  (pre-commit)
* ``triviajudge-changelog --head`` judges the bullets HEAD added
* ``triviajudge-changelog --lines FILE`` judges ``path:line<TAB>text`` records,
  for calibration
* ``triviajudge-changelog --stop`` reads a Stop or SubagentStop payload on
  stdin and judges the bullets the working tree adds, exit 2 on a flag
* ``triviajudge-changelog --release`` judges every bullet under
  ``[Unreleased]`` in one call, naming duplicates, superseded entries and
  entries under the wrong kind, exit 1 on any flag
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import TextIO

from triviajudge.changelog_prompts import PROMPT, RELEASE_PROMPT
from triviajudge.changelog_screen import (
    CHANGELOG,
    screen,
    screen_records,
    whole_section,
)
from triviajudge.config import cache_path, settings
from triviajudge.core import (
    Gate,
    Line,
    NotARepositoryError,
    added_lines,
    clean_cache,
    digest,
    from_records,
    git,
    git_diff,
    inner_session,
    root,
    stop_already_ran,
)
from triviajudge.gate import screened

CACHE_NAME = "changelog-clean.json"

#: Printed when ``--release`` arrives beside a mode it refuses.
RELEASE_ALONE = (
    "--release judges the whole [Unreleased] section and takes no other mode"
)


def at(rev: str) -> str:
    """The changelog's content at a revision, empty when that revision does not carry it."""
    try:
        return git("show", f"{rev}:{CHANGELOG}")
    except subprocess.CalledProcessError:
        return ""


def worktree_text() -> str:
    """The changelog as the working tree holds it, empty when the tree carries none."""
    path = root() / CHANGELOG
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def added_numbers(diff: str) -> set[int]:
    """The changelog line numbers a diff adds."""
    return {line.number for line in added_lines(diff) if line.path == CHANGELOG}


def worktree_added(text: str) -> set[int]:
    """What the working tree adds: the diff against HEAD, or every line when the file is untracked."""
    if git("ls-files", "--others", "--exclude-standard", "--", CHANGELOG).split():
        return set(range(1, len(text.splitlines()) + 1))
    return added_numbers(git_diff("HEAD", "--", CHANGELOG))


def at_stop() -> tuple[list[Line], list[str]]:
    """The working tree's added bullets, minus the ones a previous turn's judge passed."""
    if stop_already_ran():
        return [], []
    text = worktree_text()
    keep, complaints = screen(text, worktree_added(text))
    seen = set(clean_cache(cache_path(CACHE_NAME)))
    return [line for line in keep if digest(line) not in seen], complaints


def collect(args: argparse.Namespace) -> tuple[list[Line], list[str]]:
    """Candidates and complaints, from whichever scope and input mode the arguments name."""
    if args.release:
        return whole_section(worktree_text())
    if args.stop:
        return at_stop()
    if args.lines:
        return screen_records(from_records(Path(args.lines)))
    if args.head:
        return screen(at("HEAD"), added_numbers(git_diff("HEAD~1", "--", CHANGELOG)))
    if args.files and CHANGELOG not in args.files:
        return [], []
    return screen(at(""), added_numbers(git_diff("--cached", "--", CHANGELOG)))


def gate(args: argparse.Namespace) -> Gate:
    """The changelog gate, in the scope the arguments name.

    The release scope keeps no cache and asks in one call, since its question is
    how the bullets relate to each other.
    """
    if args.release:
        return Gate(
            RELEASE_PROMPT,
            collect,
            "[ok] the section carries no bullet",
            judge_at_stop=False,
        )
    cache = cache_path(CACHE_NAME) if args.stop else None
    return Gate(
        PROMPT,
        collect,
        "[ok] no changelog entry added",
        judge_at_stop=True,
        cache=cache,
        batch=settings().gate_batch,
    )


def parse_args() -> argparse.Namespace:
    """Read the five standard input modes, and the release scope that refuses them."""
    parser = argparse.ArgumentParser(
        description=__doc__ or "", formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("files", nargs="*", help="staged paths (pre-commit)")
    parser.add_argument(
        "--head", action="store_true", help="judge the bullets HEAD added"
    )
    parser.add_argument(
        "--stop",
        action="store_true",
        help="judge the working tree; reads a Stop payload on stdin",
    )
    parser.add_argument("--lines", help="calibration records, path:line<TAB>text")
    parser.add_argument("--out", help="write the judge's raw answer here")
    parser.add_argument(
        "--release",
        action="store_true",
        help="judge the whole [Unreleased] section before a cut",
    )
    return parser.parse_args()


def conflicted(args: argparse.Namespace) -> bool:
    """Whether ``--release`` arrived beside a mode it refuses to fold into."""
    return bool(args.release and (args.stop or args.head or args.lines or args.files))


def verdict(
    args: argparse.Namespace, lines: list[Line], complaints: list[str], out: TextIO
) -> int:
    """Judge what the screen left, and answer with the exit code the screen and the judge earned."""
    fail = 2 if args.stop else 1
    if complaints and not lines:
        for complaint in complaints:
            print(complaint, file=out)
        return fail
    return screened(args, gate(args), lines, complaints, out) or (
        fail if complaints else 0
    )


def main() -> int:
    """Screen the added bullets and judge what is left, or judge the whole section under ``--release``."""
    args = parse_args()
    if conflicted(args):
        print(RELEASE_ALONE, file=sys.stderr)
        return 1
    if args.stop and inner_session():
        return 0
    out = sys.stderr if args.stop else sys.stdout
    try:
        lines, complaints = collect(args)
    except NotARepositoryError as exc:
        print(f"trivia judge: {exc}", file=sys.stderr)
        return 2 if args.stop else 1
    return verdict(args, lines, complaints, out)


if __name__ == "__main__":
    sys.exit(main())
