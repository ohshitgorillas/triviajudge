#!/usr/bin/env python3
"""Gate: the ``[Unreleased]`` section holds its shape with no model call.

(CONTRIBUTING.md "Changelog shape")

``triviajudge-changelog`` holds the same mechanical rules over the bullets a
commit adds, and it is a judge: it needs the ``claude`` CLI and the network, so it
sits outside ``make check``, which is offline by contract. That leaves the offline
half of the rule unenforced over the section as a whole. A bullet reshaped by a
later commit that adds no line to it, a heading a rebase duplicates, a kind order
a merge scrambles: each reaches a release with nothing offline to say so.

This gate is the offline half, over the whole section rather than over added
lines, and it makes no model call:

* a bullet runs to at most ``CAP`` words
* a bullet opens with a bold lead clause: what it does now, in a clause
* no second person
* one heading per kind, in Keep a Changelog order

Register and tone stay with the judge. A wordlist is a proxy for register and a
poor one, and the section that holds both would then state the rule twice.

Released sections are history and are never rewritten, so nothing below the first
``##`` heading under ``[Unreleased]`` is read.

Usage: ``python scripts/gates/check_changelog.py [CHANGELOG.md ...]``
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

#: The one section this gate reads. Everything below it has shipped.
UNRELEASED = "## [Unreleased]"

#: Words per bullet. Enough for the change and the symptom that recognizes it.
CAP = 75

#: Keep a Changelog's kinds, in its order, plus the ``Internal`` bucket this
#: repository uses for a change with no user-visible face.
KINDS = ("Added", "Changed", "Deprecated", "Removed", "Fixed", "Security", "Internal")

OPENS = re.compile(r"^## \[Unreleased\]")
CLOSES = re.compile(r"^## ")
KIND = re.compile(r"^### (.+?)\s*$")
BULLET = re.compile(r"^- ")
INDENTED = re.compile(r"^[ \t]+\S")
SPAN = re.compile(r"`[^`]*`")
EMPHASIS = re.compile(r"[*_]")
PERSON = re.compile(r"\b(?:you|your|yours|yourself|you're|you've|you'd|you'll)\b", re.IGNORECASE)

#: The lead a bullet opens with: a bold clause, immediately.
LEAD = "- **"


def body(lines: list[str]) -> list[tuple[int, str]]:
    """The ``[Unreleased]`` section's lines, each with its 1-indexed number."""
    opens = [index for index, line in enumerate(lines) if OPENS.match(line)]
    if not opens:
        return []
    first = opens[0] + 1
    closes = [index for index, line in enumerate(lines) if index > opens[0] and CLOSES.match(line)]
    last = closes[0] if closes else len(lines)
    return [(number + 1, lines[number]) for number in range(first, last)]


def blocks(section: list[tuple[int, str]]) -> list[tuple[int, list[str]]]:
    """Every bullet in the section, keyed by the line it opens on, continuations included."""
    found: dict[int, list[str]] = {}
    open_at = 0
    for number, line in section:
        if BULLET.match(line):
            open_at = number
            found[open_at] = [line]
        elif open_at and INDENTED.match(line):
            found[open_at].append(line)
        elif not line.strip():
            open_at = 0
    return sorted(found.items())


def length(text: str) -> int:
    """Words in a bullet, code spans, emphasis markers and bare punctuation aside.

    A dash standing between two clauses is punctuation the author chose over a
    comma, and pricing it as a word taxes the punctuation rather than the prose.
    """
    bare = EMPHASIS.sub("", SPAN.sub(" ", text))
    return len([token for token in bare.split() if any(char.isalnum() for char in token)])


def bullet_faults(number: int, lines: list[str]) -> list[str]:
    """Every rule the bullet opening at ``number`` breaks."""
    text = " ".join(line.strip() for line in lines)
    found = []
    if (count := length(text)) > CAP:
        found.append(f"line {number}: {count} words, and {CAP} is the cap")
    if not text.startswith(LEAD):
        found.append(f"line {number}: no bold lead clause, which a bullet opens with as `{LEAD}…**`")
    if reader := PERSON.search(text):
        found.append(f"line {number}: {reader.group(0)!r} addresses the reader — state the change impersonally")
    return found


def kinds(section: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """(line number, kind) for every ``###`` heading the section carries."""
    return [(number, match.group(1)) for number, line in section if (match := KIND.match(line))]


def repeated(found: list[tuple[int, str]]) -> list[str]:
    """A complaint per heading whose kind a heading above it already opened."""
    above: dict[str, int] = {}
    faults = []
    for number, kind in found:
        if kind in above:
            faults.append(f"line {number}: '### {kind}' repeats line {above[kind]} — one heading per kind, merged")
        above.setdefault(kind, number)
    return faults


def misordered(found: list[tuple[int, str]]) -> list[str]:
    """A complaint per heading naming no known kind, or sitting above a kind that outranks it."""
    faults = []
    rank = -1
    for number, kind in found:
        if kind not in KINDS:
            faults.append(f"line {number}: '### {kind}' names no kind — one of {list(KINDS)}")
            continue
        place = KINDS.index(kind)
        if place < rank:
            faults.append(f"line {number}: '### {kind}' sits out of order — {list(KINDS)}")
        rank = max(rank, place)
    return faults


def check(path: Path) -> int:
    """Report every shape rule the file's ``[Unreleased]`` section breaks."""
    section = body(path.read_text(encoding="utf-8").splitlines())
    headings = kinds(section)
    faults = repeated(headings) + misordered(headings)
    for number, lines in blocks(section):
        faults += bullet_faults(number, lines)

    for fault in faults:
        print(f"{path}:{fault}")
    if faults:
        print(f"\n{len(faults)} problem(s) under {UNRELEASED}. See CONTRIBUTING.md.")
        return 1
    print(f"[ok] {path} holds its shape under {UNRELEASED}")
    return 0


def main() -> int:
    """Check the paths named on argv, or this repository's changelog."""
    paths = [Path(argument) for argument in sys.argv[1:]] or [ROOT / "CHANGELOG.md"]
    return max(check(path) for path in paths)


if __name__ == "__main__":
    sys.exit(main())
