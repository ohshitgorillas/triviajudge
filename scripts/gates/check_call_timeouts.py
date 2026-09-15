#!/usr/bin/env python3
"""Gate: every call that waits on another process or a socket states its own timeout.

``subprocess.run`` and ``urllib.request.urlopen`` both wait forever by default.
A gate runs inside a pre-commit hook with its output captured, so a wedged
``git`` or a server that accepts the connection and never answers hangs the
commit with nothing printed: no prompt, no error, no line saying which call is
waiting. The commit looks slow rather than stuck, which is the reading that
keeps someone waiting longest.

So a ``timeout=`` keyword is mandatory at each such call site in the package and
the gates. The value is the caller's to choose — a local ``git`` needs seconds
and a model call needs minutes — and passing ``timeout=None`` explicitly is the
one way to say a call may wait forever, which puts that decision on the line
that makes it rather than in the default.

The sweep is over the AST and matches on the call's spelling: ``subprocess.run``
and ``urlopen`` by any dotted prefix. A call reached through an alias is not
matched, which is the gate's edge; the import style in this tree is the dotted
one.

Usage: ``python scripts/gates/check_call_timeouts.py [path ...]``
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

#: Call names that wait, by the attribute the call site spells last.
WAITING = {"run": "subprocess.run", "urlopen": "urllib.request.urlopen"}

#: The keyword that bounds the wait.
TIMEOUT = "timeout"


def on_subprocess(func: ast.expr) -> bool:
    """Whether the call spells its own module, which is what tells ``subprocess.run`` from any other ``run``."""
    return isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "subprocess"


def called(node: ast.Call) -> str | None:
    """The waiting call this node makes, or None when it makes none."""
    func = node.func
    if isinstance(func, ast.Attribute):
        tail = func.attr
    elif isinstance(func, ast.Name):
        tail = func.id
    else:
        return None
    if tail == "run" and not on_subprocess(func):
        return None
    return WAITING.get(tail)


def unbounded(path: Path) -> list[str]:
    """Every waiting call in the file that states no ``timeout=``."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = called(node)
        if name and not any(keyword.arg == TIMEOUT for keyword in node.keywords):
            found.append(f"{path}:{node.lineno}: {name} with no {TIMEOUT}=, so the call may wait forever")
    return found


def check(paths: list[Path]) -> int:
    """Refuse a call that waits on a process or a socket with no bound on the wait."""
    problems = [problem for path in paths for problem in unbounded(path)]
    for problem in problems:
        print(problem)
    if problems:
        print(f"\n{len(problems)} problem(s). Every subprocess.run and urlopen states timeout=;")
        print("timeout=None is how a call says out loud that it may wait forever.")
        return 1
    print(f"[ok] {len(paths)} file(s) bound every call that waits")
    return 0


def main() -> int:
    """Check the files named on argv, or the package and the gates."""
    args = [Path(arg) for arg in sys.argv[1:]]
    if args:
        return check(args)
    return check(sorted((ROOT / "triviajudge").glob("*.py")) + sorted((ROOT / "scripts" / "gates").glob("*.py")))


if __name__ == "__main__":
    sys.exit(main())
