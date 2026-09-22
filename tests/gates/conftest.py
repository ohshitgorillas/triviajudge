"""Import path for the gate scripts, which are modules by filename rather than a package.

``scripts/gates/`` holds one subdirectory per concern and one standalone script
per gate inside it, run as ``python scripts/gates/<concern>/<name>.py``. There is
no ``__init__.py`` and no import path into it, so a test that drives a gate in
process puts every concern directory on ``sys.path`` and imports the script by
its filename.
"""

from __future__ import annotations

import sys
from pathlib import Path

#: The directory holding one subdirectory per concern.
GATES = Path(__file__).resolve().parents[2] / "scripts" / "gates"

for concern in sorted(path for path in GATES.iterdir() if path.is_dir()):
    if str(concern) not in sys.path:
        sys.path.insert(0, str(concern))


def written(name: str, source: str) -> str:
    """Write a module source at ``name``, relative to the current directory, and return the name.

    Several gates read a path as the tree it sits in — ``tests/`` against
    anything else — so a case hands them a relative name and runs from the
    directory it wrote that name under.
    """
    path = Path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return name
