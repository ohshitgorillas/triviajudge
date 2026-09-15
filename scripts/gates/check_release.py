#!/usr/bin/env python3
"""Gate: the package version, the changelog and the tags name one release.

(CONTRIBUTING.md "Cutting a release")

Three places state which version this tree is: ``version`` in ``pyproject.toml``,
the newest released ``## [x.y.z]`` heading in ``CHANGELOG.md``, and the ``vx.y.z``
tags in git. Each is edited by hand, and nothing compares them, so a release can
ship with a version no changelog section describes, or a section describing a
version no tag ever carried. Both fail silently: the package installs, the
changelog renders, and the mismatch surfaces to whoever is reading the release
notes against the artifact.

Three rules hold them together:

1. ``version`` equals the newest released changelog heading. ``[Unreleased]`` is
   not a release and never satisfies it.
2. A tag pointing at ``HEAD`` is exactly ``v<version>``. Anything else means the
   tag and the tree disagree about what was cut.
3. Every released heading other than the newest carries a ``v`` tag. The newest
   is the one exemption, because the commit that cuts a release exists before the
   tag that names it does; the next release is what brings it under the rule.

Usage: ``python scripts/gates/check_release.py``
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

#: A released section heading: ``## [x.y.z]``, date and all. ``[Unreleased]`` misses it.
HEADING = re.compile(r"^## \[(\d+\.\d+\.\d+)\]")


def git(*args: str) -> list[str]:
    """The lines ``git`` printed, or none when it refused or is absent."""
    binary = shutil.which("git")
    if binary is None:
        return []
    finished = subprocess.run([binary, *args], cwd=ROOT, capture_output=True, text=True, check=False)  # noqa: S603
    if finished.returncode != 0:
        return []
    return [line.strip() for line in finished.stdout.splitlines() if line.strip()]


def declared(pyproject: Path) -> str:
    """The version ``pyproject.toml`` declares."""
    table = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    return str(table["project"]["version"])


def released(changelog: Path) -> list[str]:
    """Every released version the changelog names, newest first."""
    lines = changelog.read_text(encoding="utf-8").splitlines()
    return [match.group(1) for line in lines if (match := HEADING.match(line))]


def check(root: Path) -> int:
    """Refuse a tree whose version, changelog and tags name different releases."""
    version = declared(root / "pyproject.toml")
    sections = released(root / "CHANGELOG.md")
    tags = set(git("tag", "--list"))
    problems: list[str] = []

    if not sections:
        problems.append("CHANGELOG.md: no released section, so nothing states what version is out")
    elif sections[0] != version:
        problems.append(f"pyproject.toml: version {version}, newest CHANGELOG.md section [{sections[0]}]")

    problems.extend(
        f"{tag}: tag on HEAD, version {version}" for tag in git("tag", "--points-at", "HEAD") if tag != f"v{version}"
    )
    problems.extend(
        f"CHANGELOG.md: [{section}] is released and carries no v{section} tag"
        for section in sections[1:]
        if f"v{section}" not in tags
    )

    for problem in problems:
        print(problem)
    if problems:
        print(f"\n{len(problems)} problem(s). The version, the newest changelog section and the")
        print("tags name one release; a section older than the newest carries its tag.")
        return 1
    print(f"[ok] version {version} is the newest of {len(sections)} changelog section(s), and the tags agree")
    return 0


def main() -> int:
    """Check this repo."""
    return check(ROOT)


if __name__ == "__main__":
    sys.exit(main())
