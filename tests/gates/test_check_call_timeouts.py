"""The timeout gate: every call that waits on a process or a socket states its own bound.

The sweep is over the AST and matches on how the call site spells the call, so
the cases here vary the spelling: ``subprocess.run`` against a bare ``run``,
``urlopen`` under one dotted prefix or another, a stated ``timeout=`` against
none, and ``timeout=None`` as the explicit way to wait forever.

Each case that should pass sits in a file with one unbounded call after it, so
the verdict under test is the single finding naming that one call's line rather
than an empty list. The expected finding and the gate's two verdict lines are
seeded here as text, so a reworded sentence or a shifted line number fails.
"""

import sys
from pathlib import Path

import check_call_timeouts as GATE
import pytest

RUN_FAULT = "{path}:{line}: subprocess.run with no timeout=, so the call may wait forever"

URLOPEN_FAULT = "{path}:{line}: urllib.request.urlopen with no timeout=, so the call may wait forever"

REFUSAL_TAIL = (
    "\n1 problem(s). Every subprocess.run and urlopen states timeout=;\n"
    "timeout=None is how a call says out loud that it may wait forever.\n"
)

CLEAN_LINE = "[ok] 1 file(s) bound every call that waits\n"

BOUNDED = "import subprocess\n\nsubprocess.run(['git', 'status'], timeout=30)\n"

BOUNDED_THEN_UNBOUNDED = (
    "import subprocess\n\nsubprocess.run(['git', 'status'], timeout=30)\nsubprocess.run(['git', 'log'])\n"
)

FOREVER_BY_NAME_THEN_UNBOUNDED = (
    "import subprocess\n\nsubprocess.run(['git', 'status'], timeout=None)\nsubprocess.run(['git', 'log'])\n"
)

OTHER_RUN_THEN_UNBOUNDED = (
    "import subprocess\n\nrunner = object()\nrunner.run(['git', 'status'])\nsubprocess.run(['git', 'log'])\n"
)

SUBSCRIPT_CALL_THEN_UNBOUNDED = "import subprocess\n\nhandlers = {}\nhandlers['a']()\nsubprocess.run(['git', 'log'])\n"

UNBOUNDED_RUN = "import subprocess\n\nsubprocess.run(['git', 'status'])\n"

UNBOUNDED_URLOPEN = "import urllib.request\n\nurllib.request.urlopen('https://example.invalid')\n"

BOUNDED_URLOPEN_THEN_UNBOUNDED = (
    "import urllib.request\n\n"
    "urllib.request.urlopen('https://example.invalid', timeout=5)\n"
    "urllib.request.urlopen('https://example.invalid')\n"
)

BARE_URLOPEN = "from urllib.request import urlopen\n\nurlopen('https://example.invalid')\n"


def written(tmp_path: Path, source: str) -> Path:
    """The source written to a file the gate can read."""
    path = tmp_path / "module.py"
    path.write_text(source, encoding="utf-8")
    return path


def located(findings: list[str]) -> list[str]:
    """The ``path:line`` each finding opens with, the wording after it dropped."""
    return [finding.partition(": ")[0] for finding in findings]


# --- behavior 1: the finding names the call, its spelling and its line -------


def test_the_unbounded_run_is_named_and_the_bounded_one_above_it_is_not(tmp_path: Path) -> None:
    path = written(tmp_path, BOUNDED_THEN_UNBOUNDED)
    assert located(GATE.unbounded(path)) == [f"{path}:4"]


def test_timeout_none_passes_and_only_the_call_stating_nothing_is_named(tmp_path: Path) -> None:
    path = written(tmp_path, FOREVER_BY_NAME_THEN_UNBOUNDED)
    assert located(GATE.unbounded(path)) == [f"{path}:4"]


def test_a_run_on_something_other_than_subprocess_is_not_the_named_call(tmp_path: Path) -> None:
    path = written(tmp_path, OTHER_RUN_THEN_UNBOUNDED)
    assert located(GATE.unbounded(path)) == [f"{path}:5"]


def test_a_call_on_a_subscript_is_not_the_named_call(tmp_path: Path) -> None:
    path = written(tmp_path, SUBSCRIPT_CALL_THEN_UNBOUNDED)
    assert located(GATE.unbounded(path)) == [f"{path}:5"]


def test_the_unbounded_urlopen_is_named_and_the_bounded_one_above_it_is_not(tmp_path: Path) -> None:
    path = written(tmp_path, BOUNDED_URLOPEN_THEN_UNBOUNDED)
    assert GATE.unbounded(path) == [URLOPEN_FAULT.format(path=path, line=4)]


def test_a_bare_urlopen_is_named_by_its_dotted_spelling(tmp_path: Path) -> None:
    path = written(tmp_path, BARE_URLOPEN)
    assert GATE.unbounded(path) == [URLOPEN_FAULT.format(path=path, line=3)]


# --- behavior 2: what the run prints is the verdict over the files handed over


def test_a_tree_that_bounds_every_wait_prints_the_clean_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = GATE.check([written(tmp_path, BOUNDED)])
    assert (code, capsys.readouterr().out) == (0, CLEAN_LINE)


def test_one_unbounded_call_prints_its_line_and_the_refusal(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = written(tmp_path, UNBOUNDED_RUN)
    code = GATE.check([path])
    assert (code, capsys.readouterr().out) == (1, RUN_FAULT.format(path=path, line=3) + "\n" + REFUSAL_TAIL)


# --- behavior 3: argv names the files, and its absence names the tree --------


def test_main_names_the_call_in_the_file_argv_gave(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = written(tmp_path, UNBOUNDED_URLOPEN)
    monkeypatch.setattr(sys, "argv", ["check_call_timeouts.py", str(path)])
    code = GATE.main()
    assert (code, capsys.readouterr().out) == (1, URLOPEN_FAULT.format(path=path, line=3) + "\n" + REFUSAL_TAIL)


def test_main_with_no_argv_names_the_call_in_the_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "triviajudge").mkdir()
    path = tmp_path / "triviajudge" / "mod.py"
    path.write_text(UNBOUNDED_RUN, encoding="utf-8")
    (tmp_path / "scripts" / "gates").mkdir(parents=True)
    monkeypatch.setattr(GATE, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["check_call_timeouts.py"])
    code = GATE.main()
    assert (code, capsys.readouterr().out) == (1, RUN_FAULT.format(path=path, line=3) + "\n" + REFUSAL_TAIL)
