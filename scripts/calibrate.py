#!/usr/bin/env python3
"""Ask the configured judge about a corpus whose verdict is already known.

(CONTRIBUTING.md "Calibrating the judge")

Every gate in this repository holds the tree. None of them holds the judge: the
model decides what counts as trivia, and a change to the prompt, the model or
the backend moves that decision with nothing measuring the move. A judge that
flags every line and a judge that flags none both leave `make check` green.

So the corpus carries the verdict and this script carries the comparison. Two
record files in the ``path:line<TAB>text`` form ``--lines`` reads, one holding
lines a judge is expected to flag and one holding lines it is expected to pass.
The script asks the configured model about both and prints four numbers — the
flagged trivia, the trivia it let through, the clean lines it passed and the
clean lines it flagged — and then every line the two disagree about, so a
disagreement is read rather than counted.

It spends one call per batch of lines and needs the network, which is why it
lives beside ``make trivia`` rather than inside ``make check``.

Usage: ``python scripts/calibrate.py --trivia FILE --clean FILE [--gate md|comments|changelog]``
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from triviajudge import changelog_prompts, comment_trivia, md_trivia
from triviajudge.core import from_records
from triviajudge.gate import verdicts

if TYPE_CHECKING:
    from triviajudge.core import Line

#: The prompt each gate asks, by the name ``--gate`` takes.
PROMPTS = {
    "md": md_trivia.PROMPT,
    "comments": comment_trivia.PROMPT,
    "changelog": changelog_prompts.PROMPT,
}

#: Lines per call. A corpus arrives in one file and the judge answers per call, so the
#: batch is what keeps a whole run off a single answer.
BATCH = 50

#: Seconds one call may take before the run calls it lost.
TIMEOUT = 300.0


def flagged(
    lines: list[Line], prompt: str, model: str | None, batch: int, *, exhaustive: bool
) -> set[str]:
    """The id of every line the judge flags, over as many calls as the batch size asks for.

    The chunking is the gate's own, so a calibration run measures the shape the
    gate runs rather than a second one written here.
    """
    marked = verdicts(
        lines,
        prompt,
        exhaustive=exhaustive,
        batch=batch,
        parallel=1,
        model=model,
        timeout=TIMEOUT,
    )
    return {str(flag["id"]) for flag in marked}


def corpus(path: Path | None) -> list[Line]:
    """The records a corpus file holds; an unnamed file is an empty corpus."""
    if path is None:
        return []
    if not path.is_file():
        raise SystemExit(f"{path}: no such corpus")
    return from_records(path)


def disagreement(lines: list[Line], marked: set[str], *, expected: bool) -> list[Line]:
    """Every line whose verdict is not the one its corpus states."""
    return [line for line in lines if (line.id in marked) is not expected]


def report(trivia: list[Line], clean: list[Line], marked: set[str]) -> int:
    """Print the four counts and every line the judge and the corpus disagree about."""
    missed = disagreement(trivia, marked, expected=True)
    alarms = disagreement(clean, marked, expected=False)
    agreed = len(trivia) - len(missed) + len(clean) - len(alarms)
    total = len(trivia) + len(clean)

    print(f"trivia: {len(trivia) - len(missed)}/{len(trivia)} flagged")
    print(f"clean:  {len(clean) - len(alarms)}/{len(clean)} passed")
    if total:
        print(f"agreement: {agreed}/{total} ({100 * agreed / total:.1f}%)")
    for line in missed:
        print(f"missed     {line.id}\t{line.text}")
    for line in alarms:
        print(f"false alarm {line.id}\t{line.text}")
    return 0 if not total or agreed == total else 1


def parse_args(argv: list[str]) -> argparse.Namespace:
    """The corpora, the gate whose prompt is asked, and the model that answers."""
    parser = argparse.ArgumentParser(
        description="Measure the judge against a corpus whose verdict is known."
    )
    parser.add_argument(
        "--trivia", type=Path, help="records the judge is expected to flag"
    )
    parser.add_argument(
        "--clean", type=Path, help="records the judge is expected to pass"
    )
    parser.add_argument(
        "--gate", choices=sorted(PROMPTS), default="md", help="whose prompt to ask"
    )
    parser.add_argument(
        "--model", default=None, help="the model to ask, over the configured one"
    )
    parser.add_argument(
        "--batch", type=int, default=BATCH, help=f"lines per call (default {BATCH})"
    )
    return parser.parse_args(argv)


def main() -> int:
    """Ask the judge about both corpora and report where it and they disagree."""
    args = parse_args(sys.argv[1:])
    trivia = corpus(args.trivia)
    clean = corpus(args.clean)
    if not trivia and not clean:
        raise SystemExit("no corpus: name one with --trivia or --clean")
    marked = flagged(
        trivia + clean,
        PROMPTS[args.gate],
        args.model,
        args.batch,
        exhaustive=args.gate == "md",
    )
    return report(trivia, clean, marked)


if __name__ == "__main__":
    sys.exit(main())
