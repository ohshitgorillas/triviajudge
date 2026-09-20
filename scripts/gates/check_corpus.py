#!/usr/bin/env python3
"""Gate: the calibration corpus parses, and no line is filed under both verdicts.

(CONTRIBUTING.md "The calibration corpus")

``make calibrate`` measures a judge against a corpus whose verdict is already
settled: one file per label, each line a record in the ``path:line<TAB>text`` form
``triviajudge-md --lines`` reads. The corpus is edited by hand, one line at a
time, and both ways of breaking it are silent.

A record that does not parse is dropped by the reader rather than refused, so the
run measures a smaller corpus than the file states and reports a rate over it. A
line filed under both labels is worse: it is a disagreement inside the answer key,
so the judge is scored wrong whichever verdict it returns, and the run cannot
report better than one error.

Two rules, then. Every line of every ``*.txt`` under the corpus directory parses
as ``RECORD``. And across each pair in ``PAIRS`` no text appears on both sides,
compared on the record's text alone: the same sentence cited from two files is one
claim about that sentence.

Usage: ``python scripts/gates/check_corpus.py [corpus-directory]``
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

#: Where the corpus lives, relative to the repository root.
CORPUS = "corpus"

#: The separator between a record's citation and its text.
TAB = "\t"

#: Each label pair, trivia first. A text on both sides of one pair is a contradiction.
PAIRS = (("trivia.txt", "clean.txt"), ("changelog-trivia.txt", "changelog-clean.txt"))


def record(line: str) -> str | None:
    """The text a record carries, or None when the line is no record.

    A record is a citation, a tab, and text: the citation names a file and a line
    number, both non-empty, and the text after the tab is non-empty as well.
    """
    citation, tab, text = line.partition(TAB)
    if not tab or not text.strip():
        return None
    name, colon, number = citation.rpartition(":")
    if not colon or not name or not number.isdigit():
        return None
    return text.strip()


def unparsed(path: Path) -> list[str]:
    """One line per line of the file that is no record."""
    lines = enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
    return [
        f"{path}:{number}: no record — a line reads `path:line<TAB>text`"
        for number, line in lines
        if record(line) is None
    ]


def texts(path: Path) -> dict[str, list[int]]:
    """Every text the file files, to the line numbers filing it."""
    found: dict[str, list[int]] = defaultdict(list)
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if (text := record(line)) is not None:
            found[text].append(number)
    return found


def contradictions(directory: Path, trivia: str, clean: str) -> list[str]:
    """One line per text both sides of a pair file, which is a disagreement in the answer key."""
    left = texts(directory / trivia)
    right = texts(directory / clean)
    return [
        f"{directory / trivia}:{left[text][0]}: also {clean}:{right[text][0]} — one text, two verdicts"
        for text in sorted(set(left) & set(right))
    ]


def check(directory: Path) -> int:
    """Refuse a corpus that does not parse, or that files one text under both labels."""
    problems = [problem for path in sorted(directory.glob("*.txt")) for problem in unparsed(path)]
    problems += [problem for trivia, clean in PAIRS for problem in contradictions(directory, trivia, clean)]
    for problem in problems:
        print(problem)
    if problems:
        print(f"\n{len(problems)} problem(s) in {directory}. A dropped record shrinks the corpus in silence,")
        print("and a text under both labels scores the judge wrong whichever verdict it gives.")
        return 1
    print(f"[ok] {directory} parses whole, and every text holds one verdict")
    return 0


def main() -> int:
    """Check the directory named on argv, or this repository's corpus."""
    given = sys.argv[1:]
    return check(Path(given[0]) if given else ROOT / CORPUS)


if __name__ == "__main__":
    sys.exit(main())
