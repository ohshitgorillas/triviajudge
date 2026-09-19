"""The timeout gate: every call that waits on a process or a socket states its own bound.

The sweep is over the AST and matches on how the call site spells the call, so
the cases here vary the spelling: ``subprocess.run`` against a bare ``run``,
``urlopen`` under one dotted prefix or another, a stated ``timeout=`` against
none, and ``timeout=None`` as the explicit way to wait forever.

A refusal is matched on the path the test wrote and the line number it put the
call on, never on the sentence the gate wraps around them.
"""

import sys
from pathlib import Path

import check_call_timeouts as GATE
import pytest

BOUNDED = "import subprocess\n\nsubprocess.run(['git', 'status'], timeout=30)\n"

UNBOUNDED_RUN = "import subprocess\n\nsubprocess.run(['git', 'status'])\n"

UNBOUNDED_URLOPEN = "import urllib.request\n\nurllib.request.urlopen('https://example.invalid')\n"

BARE_URLOPEN = "from urllib.request import urlopen\n\nurlopen('https://example.invalid')\n"

BOUNDED_URLOPEN = "import urllib.request\n\nurllib.request.urlopen('https://example.invalid', timeout=5)\n"

FOREVER_BY_NAME = "import subprocess\n\nsubprocess.run(['git', 'status'], timeout=None)\n"

SOME_OTHER_RUN = "runner = object()\n\nrunner.run(['git', 'status'])\n"

CALL_ON_A_SUBSCRIPT = "handlers = {}\n\nhandlers['a']()\n"


def written(tmp_path: Path, source: str) -> Path:
    """The source written to a file the gate can read."""
    path = tmp_path / "module.py"
    path.write_text(source, encoding="utf-8")
    return path


# --- behavior 1: a call that states its bound passes, one that does not is named ---


@pytest.mark.parametrize(
    ("source", "faults"),
    [
        (BOUNDED, 0),
        (BOUNDED_URLOPEN, 0),
        (FOREVER_BY_NAME, 0),
        (SOME_OTHER_RUN, 0),
        (CALL_ON_A_SUBSCRIPT, 0),
        (UNBOUNDED_RUN, 1),
        (UNBOUNDED_URLOPEN, 1),
        (BARE_URLOPEN, 1),
    ],
)
def test_only_a_waiting_call_with_no_timeout_is_a_fault(tmp_path: Path, source: str, faults: int) -> None:
    assert len(GATE.unbounded(written(tmp_path, source))) == faults


def test_the_fault_names_the_line_the_call_sits_on(tmp_path: Path) -> None:
    path = written(tmp_path, UNBOUNDED_RUN)
    assert GATE.unbounded(path)[0].startswith(f"{path}:3:")


# --- behavior 2: the exit code is the verdict over every file handed over ----


def test_a_tree_that_bounds_every_wait_exits_clean(tmp_path: Path) -> None:
    assert GATE.check([written(tmp_path, BOUNDED)]) == 0


def test_one_unbounded_call_fails_the_run(tmp_path: Path) -> None:
    assert GATE.check([written(tmp_path, UNBOUNDED_RUN)]) == 1


# --- behavior 3: argv names the files, and its absence names the tree --------


def test_main_judges_the_file_argv_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = written(tmp_path, UNBOUNDED_URLOPEN)
    monkeypatch.setattr(sys, "argv", ["check_call_timeouts.py", str(path)])
    assert GATE.main() == 1


def test_main_with_no_argv_judges_the_package_and_the_gates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "triviajudge").mkdir()
    (tmp_path / "triviajudge" / "mod.py").write_text(UNBOUNDED_RUN, encoding="utf-8")
    (tmp_path / "scripts" / "gates").mkdir(parents=True)
    monkeypatch.setattr(GATE, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["check_call_timeouts.py"])
    assert GATE.main() == 1
