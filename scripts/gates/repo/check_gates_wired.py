#!/usr/bin/env python3
"""Gate: every gate script in ``scripts/gates/`` runs in the Makefile and in pre-commit.

Each gate is wired in by hand, one line per script, and nothing else notices
when a script never acquires that line — or keeps it after a target is
rewritten. An uninvoked gate stops running, and a gate that stops running rots
silently: it can drift all the way to crashing on import while ``make check``
stays green.

There are two wirings, not one. ``make check`` is run by hand; pre-commit runs
on every commit. A gate present in the first and absent from the second still
looks wired, and the two have drifted apart before. Absence from pre-commit can
be correct — a gate too slow for the commit path belongs in ``make check``
only — but nothing distinguished a deliberate absence from a forgotten one,
because both are spelled as silence.

So Makefile wiring is mandatory with no exemption: a gate that should not run
is a gate that should be deleted. Pre-commit wiring is mandatory *or* exempt,
and an exemption is a line of prose in ``PRECOMMIT_EXEMPT`` saying why. An
exemption naming no gate is itself a failure — a stale reason is the same drift
one layer up. This file polices itself: its own filename in both configs is
what satisfies its own rule.

One gate is no script under ``scripts/gates/`` and so falls outside the sweep
above: the duplication gate is an ``npx`` invocation, ``JSCPD``, and a filename
sweep cannot see it. It drifts the same way and in both configs, so it is named
here and required in both by the same rule.

That invocation carries no arguments — its whole configuration is ``CONFIG`` —
which puts the gate's scope in a third file that neither config reads. A ``path``
entry naming a directory the tree does not track measures nothing and reports
nothing: jscpd walks what it is given and prints a percentage over what it found,
so a renamed directory reads as a clean tree rather than as a gate that stopped
looking. Every entry therefore names a directory holding a file git tracks.

Usage: ``python scripts/gates/repo/check_gates_wired.py``
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[3]

#: The duplication gate's invocation, which no filename sweep can find.
JSCPD = "npx jscpd"

#: The file holding that gate's whole configuration, including its directory list.
CONFIG = ".jscpd.json"

#: The key in that file naming the directories the gate reads.
PATHS = "path"

#: Seconds a local ``git`` call may take; past that it is wedged, and this gate runs on a
#: commit path whose output is captured.
GIT_TIMEOUT = 30

#: Gates that run in the Makefile only, filename to the reason they stay off the
#: commit path. Empty is the healthy state: every gate here reads files and is
#: fast enough for a commit.
PRECOMMIT_EXEMPT: dict[str, str] = {}


def gate_scripts(gates: Path) -> list[str]:
    """Path of every gate script under the directory, relative to it, sorted.

    The gates sit in one subdirectory per concern, so the sweep descends: a gate
    one level down is as much a gate as one at the top.
    """
    return sorted(
        path.relative_to(gates).as_posix()
        for path in gates.rglob("*.py")
        if path.is_file()
    )


def live(text: str) -> str:
    """Drop comment lines, which wire nothing.

    A gate commented out is a gate that stopped running, which is the case this
    exists to catch. Both configs mark comments with ``#``.
    """
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )


def unwired(config: str, names: list[str]) -> list[str]:
    """Return the gates whose filename appears in no live line of ``config``."""
    body = live(config)
    return [name for name in names if name not in body]


def tracked_directories(root: Path) -> set[str]:
    """Every directory holding a file git tracks, as a posix path relative to the root."""
    binary = shutil.which("git")
    if binary is None:
        return set()
    finished = subprocess.run(  # noqa: S603 — argv is this module's own constants and a resolved binary
        [binary, "-C", str(root), "ls-files"],
        capture_output=True,
        text=True,
        check=False,
        timeout=GIT_TIMEOUT,
    )
    return {
        str(parent)
        for name in finished.stdout.splitlines()
        for parent in PurePosixPath(name).parents
    }


def duplication(makefile: str, precommit: str) -> list[str]:
    """Return a complaint per config holding no live line that invokes the duplication gate."""
    return [
        f"{name}: no live line invokes `{JSCPD}`"
        for name, text in (
            ("Makefile", makefile),
            (".pre-commit-config.yaml", precommit),
        )
        if JSCPD not in live(text)
    ]


def untracked(root: Path) -> list[str]:
    """Return a complaint per configured duplication path naming no directory git tracks."""
    table = json.loads((root / CONFIG).read_text(encoding="utf-8"))
    directories = tracked_directories(root)
    return [
        f"{CONFIG}: {PATHS} {entry!r} names no directory the tree tracks"
        for entry in table.get(PATHS, [])
        if str(entry) not in directories
    ]


def stale(names: list[str], exempt: dict[str, str]) -> list[str]:
    """Return exemption keys naming no gate script, sorted."""
    return sorted(key for key in exempt if key not in names)


def check(root: Path, exempt: dict[str, str] | None = None) -> int:
    """Refuse a gate that no live Makefile recipe invokes, or that pre-commit forgot.

    Both checks run every time: a tree failing one still reports the other, so
    one fix per run is never the shape of this.
    """
    if exempt is None:
        exempt = PRECOMMIT_EXEMPT
    names = gate_scripts(root / "scripts" / "gates")
    problems = 0

    makefile = (root / "Makefile").read_text(encoding="utf-8")
    for name in unwired(makefile, names):
        print(f"scripts/gates/{name}: no Makefile target invokes it")
        problems += 1
    precommit = (root / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    for name in unwired(precommit, [n for n in names if n not in exempt]):
        print(f"scripts/gates/{name}: not in .pre-commit-config.yaml and not exempt")
        problems += 1
    for name in stale(names, exempt):
        print(f"PRECOMMIT_EXEMPT[{name!r}]: names no gate script")
        problems += 1
    for complaint in duplication(makefile, precommit) + untracked(root):
        print(complaint)
        problems += 1

    if problems:
        print(
            f"\n{problems} problem(s). Every gate runs in a live Makefile recipe, and in"
        )
        print(
            ".pre-commit-config.yaml unless PRECOMMIT_EXEMPT gives a reason it should not."
        )
        print(
            f"`{JSCPD}` runs in both, and every {CONFIG} {PATHS} entry names a tracked directory."
        )
        return 1
    print(
        f"[ok] all {len(names)} gate scripts are wired into the Makefile and pre-commit"
    )
    return 0


def main() -> int:
    """Check this repo."""
    return check(ROOT)


if __name__ == "__main__":
    sys.exit(main())
