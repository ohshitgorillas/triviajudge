#!/usr/bin/env python3
"""Gate: no test sleeps on a real clock or holds a small real deadline.

(CONTRIBUTING.md "Real clocks in tests")

Two patterns, one AST pass.

A ``time.sleep`` or ``asyncio.sleep`` call is flagged unless its argument is the
literal ``0``, which is a scheduler yield rather than a wait. Anything else is
flagged, literal or not: the house spelling for a wait is often a module constant
or an attribute, and a literal-only match reads a paced fake as clean.

A ``timeout`` or ``*_timeout`` keyword or mapping key given a numeric literal
above zero and below ``SMALL`` is flagged. Every such knob in this tree is either
a ceiling a test never reaches, at seconds, or a deadline the code waits out, at a
fraction of a second; the value is what separates them.

The whole suite is in scope and there is no carve-out directory. Every clock a
test here reads belongs to a seam the test owns — a fake the fixtures build, a
monkeypatched call — so a real wait in any test file is a test pacing itself
against the machine it runs on.

A per-test duration threshold sees neither pattern: a ten millisecond poll spread
over seventy call sites lifts no test over any threshold, and a deadline waited
out inside a spawned gate reads as CPU rather than as idle.

Usage: ``python scripts/gates/check_test_clocks.py <file>...``
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

#: Seconds below which a real deadline is a wait rather than a ceiling.
SMALL = 0.5

#: The modules that hold a real clock. A ``.sleep`` on anything else is a seam the
#: test controls and waits on no clock at all.
CLOCKS = ("time", "asyncio")


def sleeps(node: ast.Call) -> bool:
    """Whether the call is a real-clock sleep, by the module it is called on."""
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "sleep"
        and isinstance(func.value, ast.Name)
        and func.value.id in CLOCKS
    )


def waits(node: ast.Call) -> bool:
    """Whether a sleep call waits, rather than yielding to the scheduler."""
    if not node.args:
        return False
    first = node.args[0]
    return not (isinstance(first, ast.Constant) and isinstance(first.value, int | float) and first.value == 0)


def deadline(name: str | None, value: ast.expr) -> bool:
    """Whether a name and its value spell a small real deadline.

    Zero is no deadline: it is the spelling for a socket or a queue that answers
    on the first pass, and it waits on nothing, as a zero sleep does.
    """
    if name is None or not (name == "timeout" or name.endswith("_timeout")):
        return False
    return isinstance(value, ast.Constant) and isinstance(value.value, int | float) and 0 < value.value < SMALL


def call_faults(name: str, node: ast.Call) -> list[str]:
    """One line per real clock a call holds: its own wait, and its deadline keywords."""
    found = [f"{name}:{node.lineno}: sleeps on a real clock"] if sleeps(node) and waits(node) else []
    found += [
        f"{name}:{keyword.value.lineno}: {keyword.arg}= is a real deadline under {SMALL}s"
        for keyword in node.keywords
        if deadline(keyword.arg, keyword.value)
    ]
    return found


def mapping_faults(name: str, node: ast.Dict) -> list[str]:
    """One line per deadline a mapping literal carries under a string key."""
    pairs = zip(node.keys, node.values, strict=True)
    return [
        f"{name}:{key.lineno}: {key.value!r} is a real deadline under {SMALL}s"
        for key, value in pairs
        if isinstance(key, ast.Constant) and isinstance(key.value, str) and deadline(key.value, value)
    ]


def faults(name: str, source: str) -> list[str]:
    """One line per real clock in a module source, sorted."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source, filename=name)):
        if isinstance(node, ast.Call):
            found += call_faults(name, node)
        elif isinstance(node, ast.Dict):
            found += mapping_faults(name, node)
    return sorted(found)


def check(names: list[str]) -> int:
    """Refuse a suite whose tests pace themselves against the machine's clock."""
    problems = [problem for name in names for problem in faults(name, Path(name).read_text(encoding="utf-8"))]
    for problem in problems:
        print(problem)
    if problems:
        print(f"\n{len(problems)} real clock(s) under tests/. A poll waits on a condition and a deadline")
        print("comes from a seam the test controls; CONTRIBUTING.md is the rule.")
        return 1
    print(f"[ok] {len(names)} test file(s) read no real clock")
    return 0


def main() -> int:
    """Check the files named on argv."""
    return check(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
