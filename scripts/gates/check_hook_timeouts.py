#!/usr/bin/env python3
"""Gate: a hook's timeout covers the longest wait the module it runs can make.

(CONTRIBUTING.md "Hook timeouts")

``hooks/hooks.json`` gives each hook a ``timeout`` in seconds, and the harness
kills the hook at it. The gate modules bound their own waits with constants —
``GIT_TIMEOUT`` in ``triviajudge/core.py`` is the one every mode reaches, through
the diff each gate reads. The two numbers are edited in different files by
different changes, and nothing compares them.

Where the hook's timeout is the smaller of the two, the constant is unreachable:
the harness kills the gate before its own bound can fire, so the wait ends with
the hook killed and no line about the call that was waiting. The gate's own
handling — the message naming the command that did not answer — never runs. That
reads as a flaky hook rather than as a wedged ``git``.

So each hook's timeout is at least the largest timeout constant its module can
reach: the constants that module states, and the engine's, which every mode calls
into. A hook naming a module the package does not carry is reported too, since a
timeout cannot be judged against a module nobody can run.

The comparison is over constants, not over call sites. A call that states
``timeout=None`` waits forever and no hook timeout covers it; that decision is the
call site's to make and ``check_call_timeouts.py`` is where it is held.

Usage: ``python scripts/gates/check_hook_timeouts.py [hooks.json]``
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

#: The hook table, relative to the repository root.
TABLE = "hooks/hooks.json"

#: The package holding the gate modules a hook runs.
PACKAGE = "triviajudge"

#: The module every gate mode calls into, so its waits are every module's waits.
ENGINE = "core"

#: The suffix a timeout constant's name ends in.
SUFFIX = "TIMEOUT"

#: How ``run-gate.sh`` is handed the gate it should run: one bare word.
RUNNER = re.compile(r"run-gate\.sh[\"']?\s+(?P<gate>[a-z_]+)")


def waits(module: Path) -> dict[str, float]:
    """Every timeout constant the module states at module scope, qualified name to seconds."""
    tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
    found: dict[str, float] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
            continue
        value = node.value.value
        if isinstance(value, bool) or not isinstance(value, int | float):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id.endswith(SUFFIX):
                found[f"{module.stem}.{target.id}"] = float(value)
    return found


def longest(root: Path, gate: str) -> tuple[str, float] | None:
    """The longest wait the named module can make, as the constant naming it."""
    module = root / PACKAGE / f"{gate}.py"
    if not module.is_file():
        return None
    reach = waits(root / PACKAGE / f"{ENGINE}.py") | waits(module)
    if not reach:
        return "", 0.0
    name = max(reach, key=lambda constant: reach[constant])
    return name, reach[name]


def commands(table: dict[str, object]) -> list[tuple[str, str, float]]:
    """(event, gate, timeout) for every hook in the table that names a gate through the runner."""
    found: list[tuple[str, str, float]] = []
    events = table.get("hooks", {})
    if not isinstance(events, dict):
        return found
    for event, groups in events.items():
        for group in groups:
            found += entries(event, group)
    return found


def entries(event: str, group: dict[str, object]) -> list[tuple[str, str, float]]:
    """(event, gate, timeout) for one matcher group's hooks."""
    hooks = group.get("hooks", [])
    if not isinstance(hooks, list):
        return []
    return [
        (event, match.group("gate"), float(hook.get("timeout", 0)))
        for hook in hooks
        if (match := RUNNER.search(str(hook.get("command", ""))))
    ]


def faults(root: Path, path: Path) -> list[str]:
    """One line per hook whose timeout a constant in its module outruns."""
    table = json.loads(path.read_text(encoding="utf-8"))
    found = []
    for event, gate, timeout in commands(table):
        reach = longest(root, gate)
        if reach is None:
            found.append(f"{path}: {event} hook {gate} names no module under {PACKAGE}/")
        elif timeout < reach[1]:
            found.append(f"{path}: {event} hook {gate} has timeout {timeout:g}s, under {reach[0]} at {reach[1]:g}s")
    return found


def check(root: Path, path: Path | None = None) -> int:
    """Refuse a hook the harness kills before the wait it runs can bound itself."""
    problems = faults(root, path or root / TABLE)
    for problem in problems:
        print(problem)
    if problems:
        print(f"\n{len(problems)} hook(s) undercut a wait they can make. Raise the timeout to the constant,")
        print("or lower the constant: a killed hook prints no line about the call that was waiting.")
        return 1
    print("[ok] every hook timeout covers the longest wait its module can make")
    return 0


def main() -> int:
    """Check the table named on argv, or this repository's."""
    given = sys.argv[1:]
    return check(ROOT, Path(given[0]) if given else None)


if __name__ == "__main__":
    sys.exit(main())
