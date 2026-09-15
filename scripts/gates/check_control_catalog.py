#!/usr/bin/env python3
"""Gate: the gate catalog agrees across the three tables that name it.

One gate is spelled out in three places, and nothing else checks that they still
agree:

- ``pyproject.toml`` ``[project.scripts]`` — console script -> module entry point
- ``.pre-commit-hooks.yaml`` — the hook id a consuming repository writes, and the
  entry point it runs
- ``hooks/hooks.json`` — the Claude Code plugin's wiring, which names the module
  through ``hooks/run-gate.sh``

Adding or renaming a gate touches all three. Miss one and nothing fails here:
the gate ships with no pre-commit id, or the plugin binds a module name that no
longer imports. Both are invisible until a consumer hits them.

``CATALOG`` below is the single statement of what exists. Each entry names the
console script and, where the gate is one a hook may run, its pre-commit id and
its place in the plugin. ``sweep`` carries neither: it judges the whole tree
rather than what a change adds, which is an explicit user act, so it is a
console script and must appear in no hook table. The gate holds that shape in
both directions — a catalog name missing from a table it belongs in fails, and
so does a name in a table that the catalog does not carry.

Usage: ``python scripts/gates/check_control_catalog.py``
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
PYPROJECT = ROOT / "pyproject.toml"
HOOKS_YAML = ROOT / ".pre-commit-hooks.yaml"
HOOKS_JSON = ROOT / "hooks" / "hooks.json"


@dataclass(frozen=True)
class Gate:
    """One gate, as the three tables have to spell it."""

    #: The console script ``[project.scripts]`` binds to ``triviajudge.<module>:main``.
    script: str
    #: The hook id ``.pre-commit-hooks.yaml`` carries, or None for a gate no commit runs.
    hook_id: str | None
    #: Whether ``hooks/hooks.json`` runs the module as a plugin hook.
    plugin: bool


#: Every gate this package ships, keyed by its module under ``triviajudge/``.
CATALOG: dict[str, Gate] = {
    "md_trivia": Gate(script="triviajudge-md", hook_id="md-trivia", plugin=True),
    "comment_trivia": Gate(script="triviajudge-comments", hook_id="comment-trivia", plugin=True),
    "changelog_trivia": Gate(script="triviajudge-changelog", hook_id="changelog-trivia", plugin=True),
    "archaeology": Gate(script="triviajudge-archaeology", hook_id="archaeology", plugin=True),
    "sweep": Gate(script="triviajudge-sweep", hook_id=None, plugin=False),
}

#: ``- id: <name>`` in the pre-commit manifest. The manifest is read by line rather
#: than by a YAML parser: the gates run wherever this package does, on the standard
#: library alone, and this file keeps that property.
HOOK_ID = re.compile(r"^-\s*id:\s*(\S+)\s*$")
#: ``entry: <console script>`` under one of those ids.
HOOK_ENTRY = re.compile(r"^\s+entry:\s*(\S+)\s*$")


def scripts() -> dict[str, str]:
    """Console script -> entry point, as ``[project.scripts]`` carries it."""
    table = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    found = table.get("project", {}).get("scripts", {})
    return {str(name): str(target) for name, target in found.items()}


def manifest() -> dict[str, str]:
    """Hook id -> the entry point it runs, as ``.pre-commit-hooks.yaml`` carries it."""
    found: dict[str, str] = {}
    current: str | None = None
    for line in HOOKS_YAML.read_text(encoding="utf-8").splitlines():
        if match := HOOK_ID.match(line):
            current = match.group(1)
            found[current] = ""
        elif current and (match := HOOK_ENTRY.match(line)):
            found[current] = match.group(1)
    return found


def plugin_modules() -> set[str]:
    """Every module name ``hooks/hooks.json`` runs, however many events run it."""
    payload = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    commands = [
        str(hook.get("command", ""))
        for matchers in payload.get("hooks", {}).values()
        for matcher in matchers
        for hook in matcher.get("hooks", [])
    ]
    return {command.rsplit(" ", 1)[-1].strip('"') for command in commands}


def check_modules(catalog: dict[str, Gate]) -> list[str]:
    """Every catalog name is a module that exists."""
    return [
        f"CATALOG[{name!r}]: names no module at triviajudge/{name}.py"
        for name in catalog
        if not (ROOT / "triviajudge" / f"{name}.py").is_file()
    ]


def check_scripts(catalog: dict[str, Gate], declared: dict[str, str]) -> list[str]:
    """Each gate has its console script, bound to its own module, and nothing else does."""
    problems = []
    for name, gate in catalog.items():
        want = f"triviajudge.{name}:main"
        if gate.script not in declared:
            problems.append(f"{gate.script}: no [project.scripts] entry")
        elif declared[gate.script] != want:
            problems.append(f"{gate.script}: [project.scripts] points at {declared[gate.script]!r}, not {want!r}")
    known = {gate.script for gate in catalog.values()}
    problems += [
        f"{name}: a [project.scripts] entry the catalog does not carry" for name in sorted(set(declared) - known)
    ]
    return problems


def check_manifest(catalog: dict[str, Gate], declared: dict[str, str]) -> list[str]:
    """Each hooked gate has its pre-commit id, running its own console script, and nothing else does."""
    problems = []
    for name, gate in catalog.items():
        if gate.hook_id is None:
            continue
        if gate.hook_id not in declared:
            problems.append(f"{gate.hook_id}: no id in .pre-commit-hooks.yaml, for gate {name}")
        elif declared[gate.hook_id] != gate.script:
            problems.append(f"{gate.hook_id}: runs {declared[gate.hook_id]!r}, not {gate.script!r}")
    known = {gate.hook_id for gate in catalog.values() if gate.hook_id}
    problems += [
        f"{name}: a .pre-commit-hooks.yaml id the catalog does not carry" for name in sorted(set(declared) - known)
    ]
    return problems


def check_plugin(catalog: dict[str, Gate], wired: set[str]) -> list[str]:
    """Each plugin gate is wired into hooks.json, each console-script-only gate is not."""
    problems = [
        f"{name}: hooks.json runs no such gate" for name, gate in catalog.items() if gate.plugin and name not in wired
    ]
    problems += [
        f"{name}: hooks.json wires it, and the catalog holds it off the hook path"
        for name, gate in catalog.items()
        if not gate.plugin and name in wired
    ]
    problems += [f"{name}: hooks.json runs a gate the catalog does not carry" for name in sorted(wired - set(catalog))]
    return problems


def check(catalog: dict[str, Gate] | None = None) -> int:
    """Refuse a gate whose name has drifted between the catalog and any of the three tables.

    Every check runs every time, so one fix per run is never the shape of this.
    """
    if catalog is None:
        catalog = CATALOG
    problems = (
        check_modules(catalog)
        + check_scripts(catalog, scripts())
        + check_manifest(catalog, manifest())
        + check_plugin(catalog, plugin_modules())
    )
    for problem in problems:
        print(problem)
    if problems:
        print(f"\n{len(problems)} catalog disagreement(s) across pyproject.toml, .pre-commit-hooks.yaml, hooks.json.")
        return 1
    print(f"[ok] all {len(catalog)} gates agree across the three tables")
    return 0


def main() -> int:
    """Check this repo."""
    return check()


if __name__ == "__main__":
    sys.exit(main())
