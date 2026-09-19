"""Import path for the gate scripts, which are modules by filename rather than a package.

``scripts/gates/`` holds one standalone script per gate, run as
``python scripts/gates/<name>.py``. There is no ``__init__.py`` and no import
path into it, so a test that drives a gate in process puts that directory on
``sys.path`` and imports the script by its filename.
"""

from __future__ import annotations

import sys
from pathlib import Path

#: The directory holding one script per gate.
GATES = Path(__file__).resolve().parents[2] / "scripts" / "gates"

if str(GATES) not in sys.path:
    sys.path.insert(0, str(GATES))


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
