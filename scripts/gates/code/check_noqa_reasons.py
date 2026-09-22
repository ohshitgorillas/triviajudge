#!/usr/bin/env python3
"""Gate: a suppression names the codes it silences and states why it stands.

(CONTRIBUTING.md "Exemptions carry reasons")

Two suppressions in this tree turn a checker off for one line: a ``noqa`` comment
naming ruff codes, and a ``type: ignore`` comment naming mypy codes. Ruff's own
``PGH`` rules hold each to naming its codes, which stops a blanket suppression
from swallowing whatever the next edit breaks. Nothing holds either to saying why.

A code is not a reason. ``S603`` states which check is off, and the next reader
already has that from the checker; what the line cannot recover is the argument
that the check is wrong here — that the argv is this module's own constants, that
the field is a dataclass keyword mypy cannot see through. Absent that, the only
safe reading of a suppression is that somebody wanted the gate quiet, so it
survives every review and multiplies.

So a suppression carries ``REASON`` — an em dash and a clause — after its codes.
The em dash is the separator because a comma or a colon reads as more codes. A
mypy suppression puts that clause behind a second ``#``, which is the only tail
mypy accepts after its codes.

The sweep reads comment tokens, so a suppression spelled inside a string is data:
the test that feeds this gate a bad line, and this docstring, are both invisible
to it. A suppression naming no codes is ruff's to refuse, not this gate's.

Usage: ``python scripts/gates/code/check_noqa_reasons.py <file>...``
"""

from __future__ import annotations

import io
import re
import sys
import tokenize
from pathlib import Path

#: A ruff suppression and its codes, with whatever follows them.
NOQA = re.compile(
    r"#\s*noqa:\s*(?P<codes>[A-Z]+[0-9]+(?:\s*,\s*[A-Z]+[0-9]+)*)(?P<tail>.*)$"
)

#: A mypy suppression and its codes, with whatever follows them.
IGNORE = re.compile(r"#\s*type:\s*ignore\[(?P<codes>[^]\n]*)\](?P<tail>.*)$")

#: What a stated reason looks like after the codes: an em dash, then a clause. A
#: ``type: ignore`` puts it behind a second ``#``, because mypy reads anything else
#: after its codes as a malformed directive and refuses the line.
REASON = re.compile(r"^\s*(?:#\s*)?— \S")

#: Each suppression, with the name a complaint calls it by.
SUPPRESSIONS = ((NOQA, "noqa"), (IGNORE, "type: ignore"))


def comments(source: str) -> list[tuple[int, str]]:
    """(line number, text) for every ``#`` comment the source holds."""
    return [
        (token.start[0], token.string)
        for token in tokenize.generate_tokens(io.StringIO(source).readline)
        if token.type == tokenize.COMMENT
    ]


def silent(comment: str) -> list[tuple[str, str]]:
    """(name, codes) for every suppression in the comment that states no reason."""
    return [
        (name, match.group("codes"))
        for pattern, name in SUPPRESSIONS
        if (match := pattern.search(comment)) and not REASON.match(match.group("tail"))
    ]


def faults(path: Path) -> list[str]:
    """One line per suppression in the file that silences a checker without saying why."""
    source = path.read_text(encoding="utf-8")
    return [
        f"{path}:{number}: {name} {codes} states no reason — add ' — <why the check is wrong here>'"
        for number, comment in comments(source)
        for name, codes in silent(comment)
    ]


def check(paths: list[Path]) -> int:
    """Refuse a file whose suppression turns a checker off and says nothing."""
    problems = [problem for path in paths for problem in faults(path)]
    for problem in problems:
        print(problem)
    if problems:
        print(
            f"\n{len(problems)} silent suppression(s). A code names the check; the reason names the argument."
        )
        return 1
    print(f"[ok] {len(paths)} file(s) state a reason at every suppression")
    return 0


def main() -> int:
    """Check the files named on argv."""
    return check([Path(argument) for argument in sys.argv[1:]])


if __name__ == "__main__":
    sys.exit(main())
