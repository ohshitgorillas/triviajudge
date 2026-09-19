#!/usr/bin/env python3
"""Gate: the package version, the plugin manifests, the changelog and the tags name one release.

(CONTRIBUTING.md "Cutting a release")

Five places state which version this tree is: ``version`` in ``pyproject.toml``,
``version`` in ``.claude-plugin/plugin.json``, ``metadata.version`` in
``.claude-plugin/marketplace.json``, the newest released ``## [x.y.z]`` heading
in ``CHANGELOG.md``, and the ``vx.y.z`` tags in git. Each is edited by hand, and
nothing else compares them, so a release can ship with a version no changelog
section describes, a section describing a version no tag ever carried, or a
plugin whose manifest names the release before last. All of them fail silently:
the package installs, the changelog renders, ``claude plugin validate --strict``
passes on shape alone, and the mismatch surfaces to whoever is reading the
release notes against the artifact.

Four rules hold them together:

1. ``version`` equals the newest released changelog heading. ``[Unreleased]`` is
   not a release and never satisfies it.
2. Each plugin manifest states that same version at the key ``MANIFESTS`` names
   for it. A manifest missing the key is a failure, not an exemption.
3. A tag pointing at ``HEAD`` is exactly ``v<version>``. Anything else means the
   tag and the tree disagree about what was cut.
4. Every released heading other than the newest carries a ``v`` tag. The newest
   is the one exemption, because the commit that cuts a release exists before the
   tag that names it does; the next release is what brings it under the rule.

Usage: ``python scripts/gates/check_release.py``
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

#: A released section heading: ``## [x.y.z]``, date and all. ``[Unreleased]`` misses it.
HEADING = re.compile(r"^## \[(\d+\.\d+\.\d+)\]")

#: Each plugin manifest, repo-relative, to the key path holding its version.
#: Seconds a local ``git`` call may take; past that it is wedged, and this gate runs on a
#: commit path whose output is captured.
GIT_TIMEOUT = 30

MANIFESTS = {
    ".claude-plugin/plugin.json": ("version",),
    ".claude-plugin/marketplace.json": ("metadata", "version"),
}


def git(*args: str) -> list[str]:
    """The lines ``git`` printed, or none when it refused or is absent."""
    binary = shutil.which("git")
    if binary is None:
        return []
    finished = subprocess.run(  # noqa: S603 — argv is the git on PATH and this module's own flags
        [binary, *args], cwd=ROOT, capture_output=True, text=True, check=False, timeout=GIT_TIMEOUT
    )
    if finished.returncode != 0:
        return []
    return [line.strip() for line in finished.stdout.splitlines() if line.strip()]


def declared(pyproject: Path) -> str:
    """The version ``pyproject.toml`` declares."""
    table = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    return str(table["project"]["version"])


def stated(manifest: Path, keys: tuple[str, ...]) -> str | None:
    """The version a plugin manifest states at ``keys``, or None when it states none there."""
    found: object = json.loads(manifest.read_text(encoding="utf-8"))
    for key in keys:
        if not isinstance(found, dict) or key not in found:
            return None
        found = found[key]
    return str(found)


def manifests(root: Path, version: str) -> list[str]:
    """Every plugin manifest whose version is absent or is not ``version``."""
    problems = []
    for name, keys in MANIFESTS.items():
        where = ".".join(keys)
        says = stated(root / name, keys)
        if says is None:
            problems.append(f"{name}: no {where}, so nothing names the release it ships")
        elif says != version:
            problems.append(f"{name}: {where} {says}, pyproject.toml version {version}")
    return problems


def released(changelog: Path) -> list[str]:
    """Every released version the changelog names, newest first."""
    lines = changelog.read_text(encoding="utf-8").splitlines()
    return [match.group(1) for line in lines if (match := HEADING.match(line))]


def check(root: Path) -> int:
    """Refuse a tree whose version, manifests, changelog and tags name different releases."""
    version = declared(root / "pyproject.toml")
    sections = released(root / "CHANGELOG.md")
    tags = set(git("tag", "--list"))
    problems: list[str] = []

    if not sections:
        problems.append("CHANGELOG.md: no released section, so nothing states what version is out")
    elif sections[0] != version:
        problems.append(f"pyproject.toml: version {version}, newest CHANGELOG.md section [{sections[0]}]")

    problems.extend(manifests(root, version))
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
        print(f"\n{len(problems)} problem(s). The version, the plugin manifests, the newest changelog")
        print("section and the tags name one release; a section older than the newest carries its tag.")
        return 1
    print(f"[ok] version {version} is the newest of {len(sections)} changelog section(s); manifests and tags agree")
    return 0


def main() -> int:
    """Check this repo."""
    return check(ROOT)


if __name__ == "__main__":
    sys.exit(main())
