#!/usr/bin/env python3
"""Gate: the package imports the standard library and itself, and nothing else.

(CONTRIBUTING.md "Setup")

``dependencies`` in ``pyproject.toml`` is empty, and that empty list is the
whole reason a consumer installs this package with no resolver and no wheel
build beyond its own. Nothing holds the code to it: import-linter reads the
layers inside ``triviajudge`` and says nothing about what comes from outside,
vulture reads names, and a third-party import is a clean install on the machine
that added it and an ``ImportError`` on every machine that did not.

So every ``import`` under ``triviajudge/`` names a module in
``sys.stdlib_module_names`` or the package itself. The sweep is over the AST, so
an import inside a function body counts the same as one at module scope, and a
``TYPE_CHECKING`` block counts too: a type-only import of a package the wheel
does not require still ships a file mypy cannot read from a fresh checkout.

The gate reads the interpreter it runs under, so a module added to the standard
library in a version above ``requires-python`` would pass here and fail for a
consumer on the floor version. That floor is 3.12 and this gate runs under it in
CI.

Usage: ``python scripts/gates/check_stdlib_only.py [path ...]``
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

#: The package's own name; an import of it is an import of this tree.
PACKAGE = "triviajudge"


def roots(tree: ast.AST) -> list[tuple[int, str]]:
    """Every imported top-level module name in the file, with the line that imports it."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name.split(".")[0]) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.append((node.lineno, node.module.split(".")[0]))
    return found


def foreign(path: Path) -> list[str]:
    """Every line of the file importing something that is neither the standard library nor this package."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        f"{path}:{line}: imports {name!r}, which is neither the standard library nor {PACKAGE}"
        for line, name in roots(tree)
        if name != PACKAGE and name not in sys.stdlib_module_names
    ]


def check(paths: list[Path]) -> int:
    """Refuse a package file importing anything the standard library does not carry."""
    problems = [problem for path in paths for problem in foreign(path)]
    for problem in problems:
        print(problem)
    if problems:
        print(f"\n{len(problems)} problem(s). The package is the standard library alone, which is what")
        print("keeps `dependencies` in pyproject.toml empty. A third-party import belongs in the dev extra.")
        return 1
    print(f"[ok] {len(paths)} package file(s) import the standard library and {PACKAGE} only")
    return 0


def main() -> int:
    """Check the files named on argv, or the whole package."""
    args = [Path(arg) for arg in sys.argv[1:]]
    return check(args or sorted((ROOT / PACKAGE).glob("*.py")))


if __name__ == "__main__":
    sys.exit(main())
