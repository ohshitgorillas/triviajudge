"""Suite-wide wiring: a gate the suite runs as a process measures into the same coverage data.

Several behaviors here are only observable across a process boundary — a hook
mode reading a payload on stdin, an exit code a pre-commit run sees — so those
tests spawn the gate module rather than calling it. Coverage reaches such a
child through ``COVERAGE_PROCESS_START``, which names the config the child
reads, and ``COVERAGE_FILE``, which keeps its data beside the parent's instead
of in whatever temporary directory it runs in.
"""

from __future__ import annotations

import os
from pathlib import Path

import coverage

REPO_ROOT = Path(__file__).resolve().parents[1]

#: The environment variables a measured child needs, forwarded by the test helpers that
#: build a scrubbed environment for it.
COVERAGE_VARS = ("COVERAGE_PROCESS_START", "COVERAGE_FILE")


def pytest_configure() -> None:
    """Point a child at this repository's coverage config, when the parent is measuring."""
    if coverage.Coverage.current() is None:
        return
    os.environ["COVERAGE_PROCESS_START"] = str(REPO_ROOT / "pyproject.toml")
    os.environ.setdefault("COVERAGE_FILE", str(REPO_ROOT / ".coverage"))


def coverage_environment() -> dict[str, str]:
    """The measurement variables a spawned gate needs; empty when the suite runs unmeasured."""
    return {name: os.environ[name] for name in COVERAGE_VARS if name in os.environ}
