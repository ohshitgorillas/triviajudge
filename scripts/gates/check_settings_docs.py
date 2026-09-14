#!/usr/bin/env python3
"""Gate: every setting a repository may state is documented, and every documented one exists.

``Settings`` in ``triviajudge/config.py`` is the whole surface a judged
repository configures, and the README's ``[tool.triviajudge]`` block is where a
reader finds out what to write. The two drift in both directions, and neither
drift shows up anywhere else: a field added to the dataclass ships undocumented,
and a key the README still lists is one ``config.read`` now refuses outright,
since an unknown key fails the gate rather than being ignored. The second is the
worse of the two — the README tells the reader to write a line that stops their
commits.

So the pairing is enforced both ways. The README block is read with the same
TOML parser the gate itself uses, so a key is what the reader would actually be
writing, and a comment beside it costs nothing.

Usage: ``python scripts/gates/check_settings_docs.py [README.md]``
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

from triviajudge.config import Settings

ROOT = Path(__file__).resolve().parent.parent.parent
README = ROOT / "README.md"

#: The fence the documented block opens with, and the table that marks it.
FENCE = "```"
TABLE = "[tool.triviajudge]"


def documented_block(text: str) -> str | None:
    """The body of the fenced block carrying the settings table, or None when there is none."""
    block: list[str] = []
    inside = False
    for line in text.splitlines():
        if line.startswith(FENCE):
            if inside and any(TABLE in held for held in block):
                return "\n".join(block)
            inside = not inside
            block = []
            continue
        if inside:
            block.append(line)
    return None


def documented(path: Path) -> set[str]:
    """Every settings key the README's table states."""
    body = documented_block(path.read_text(encoding="utf-8"))
    if body is None:
        return set()
    table = tomllib.loads(body)
    found = table.get("tool", {}).get("triviajudge", {})
    return set(found)


def fields() -> set[str]:
    """Every field ``Settings`` carries."""
    return set(Settings.__dataclass_fields__)


def check(path: Path) -> int:
    """Refuse a settings field the README omits, or a README key ``Settings`` has no field for.

    Both directions run every time, so one fix per run is never the shape of this.
    """
    body = documented_block(path.read_text(encoding="utf-8"))
    if body is None:
        print(f"{path}: no fenced block carrying {TABLE} — the settings are undocumented")
        return 1

    shown = documented(path)
    known = fields()
    problems = [f"{name}: a Settings field {path.name} does not document" for name in sorted(known - shown)]
    problems += [
        f"{name}: documented in {path.name}, and Settings carries no such field" for name in sorted(shown - known)
    ]

    for problem in problems:
        print(problem)
    if problems:
        print(f"\n{len(problems)} problem(s). Every setting is in both {path.name} and Settings, or in neither.")
        return 1
    print(f"[ok] all {len(known)} settings are documented in {path.name}")
    return 0


def main() -> int:
    """Check this repo's README, or one named on argv."""
    args = sys.argv[1:]
    return check(Path(args[0]) if args else README)


if __name__ == "__main__":
    sys.exit(main())
