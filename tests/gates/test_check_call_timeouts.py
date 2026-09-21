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

import os
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

BOUNDED_URLOPEN = "import urllib.request\n\nurllib.request.urlopen('https://example.invalid', timeout=5)\n"

BOUNDED_URLOPEN_THEN_UNBOUNDED = (
    "import urllib.request\n\n"
    "urllib.request.urlopen('https://example.invalid', timeout=5)\n"
    "urllib.request.urlopen('https://example.invalid')\n"
)

UNBOUNDED_URLOPEN_THEN_BOUNDED = (
    "import urllib.request\n\n"
    "urllib.request.urlopen('https://example.invalid')\n"
    "urllib.request.urlopen('https://example.invalid', timeout=5)\n"
)

BARE_URLOPEN = "from urllib.request import urlopen\n\nurlopen('https://example.invalid')\n"

BOUNDED_BARE_URLOPEN = "from urllib.request import urlopen\n\nurlopen('https://example.invalid', timeout=5)\n"


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


@pytest.mark.parametrize(
    ("source", "line"),
    [
        (BOUNDED_URLOPEN_THEN_UNBOUNDED, 4),
        (UNBOUNDED_URLOPEN_THEN_BOUNDED, 3),
    ],
    ids=["bounded first names the second", "unbounded first names the first"],
)
def test_the_unbounded_urlopen_is_named_and_the_bounded_one_above_it_is_not(
    tmp_path: Path, source: str, line: int
) -> None:
    path = written(tmp_path, source)
    assert located(GATE.unbounded(path)) == [f"{path}:{line}"]


@pytest.mark.parametrize(
    ("source", "lines"),
    [
        (BARE_URLOPEN, [3]),
        (BOUNDED_BARE_URLOPEN, []),
    ],
    ids=["bare and unbounded is named", "bare with timeout is not"],
)
def test_a_bare_urlopen_is_named_by_its_dotted_spelling(tmp_path: Path, source: str, lines: list[int]) -> None:
    path = written(tmp_path, source)
    assert located(GATE.unbounded(path)) == [f"{path}:{line}" for line in lines]


# --- behavior 2: what the run prints is the verdict over the files handed over


@pytest.mark.parametrize(
    ("source", "code", "lines"),
    [
        (BOUNDED, 0, []),
        (UNBOUNDED_RUN, 1, [3]),
    ],
    ids=["timeout stated passes", "nothing stated refuses at the call"],
)
def test_a_tree_that_bounds_every_wait_prints_the_clean_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], source: str, code: int, lines: list[int]
) -> None:
    path = written(tmp_path, source)
    exit_code = GATE.check([path])
    printed = [line for line in capsys.readouterr().out.splitlines() if line.startswith(f"{path}:")]
    assert (exit_code, located(printed)) == (code, [f"{path}:{line}" for line in lines])


def test_one_unbounded_call_prints_its_line_and_the_refusal(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = written(tmp_path, UNBOUNDED_RUN)
    code = GATE.check([path])
    assert (code, capsys.readouterr().out) == (1, RUN_FAULT.format(path=path, line=3) + "\n" + REFUSAL_TAIL)


# --- behavior 3: argv names the files, and its absence names the tree --------


def findings_under(root: Path, out: str) -> list[str]:
    """The ``path:line`` of every printed line naming a file under ``root``."""
    return located([line for line in out.splitlines() if line.startswith(f"{root}{os.sep}")])


@pytest.mark.parametrize(
    ("source", "code", "lines"),
    [
        (BOUNDED_URLOPEN, 0, []),
        (UNBOUNDED_URLOPEN, 1, [3]),
    ],
    ids=["timeout stated in the argv file passes", "nothing stated in the argv file is named there"],
)
def test_main_names_the_call_in_the_file_argv_gave(
    tmp_path: Path,
    *,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    source: str,
    code: int,
    lines: list[int],
) -> None:
    (tmp_path / "triviajudge").mkdir()
    (tmp_path / "triviajudge" / "mod.py").write_text(UNBOUNDED_RUN, encoding="utf-8")
    (tmp_path / "scripts" / "gates").mkdir(parents=True)
    (tmp_path / "bounded.py").write_text(BOUNDED_URLOPEN, encoding="utf-8")
    (tmp_path / "unbounded.py").write_text(UNBOUNDED_URLOPEN, encoding="utf-8")
    path = tmp_path / ("bounded.py" if source == BOUNDED_URLOPEN else "unbounded.py")
    monkeypatch.setattr(GATE, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["check_call_timeouts.py", str(path)])
    exit_code = GATE.main()
    assert (exit_code, findings_under(tmp_path, capsys.readouterr().out)) == (
        code,
        [f"{path}:{line}" for line in lines],
    )


@pytest.mark.parametrize(
    ("source", "code", "lines"),
    [
        (BOUNDED, 0, []),
        (UNBOUNDED_RUN, 1, [3]),
    ],
    ids=["timeout stated in the package module passes", "nothing stated in the package module is named there"],
)
def test_main_with_no_argv_names_the_call_in_the_package(
    tmp_path: Path,
    *,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    source: str,
    code: int,
    lines: list[int],
) -> None:
    (tmp_path / "triviajudge").mkdir()
    path = tmp_path / "triviajudge" / "mod.py"
    path.write_text(source, encoding="utf-8")
    (tmp_path / "scripts" / "gates").mkdir(parents=True)
    (tmp_path / "outside.py").write_text(UNBOUNDED_URLOPEN, encoding="utf-8")
    monkeypatch.setattr(GATE, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["check_call_timeouts.py"])
    exit_code = GATE.main()
    assert (exit_code, findings_under(tmp_path, capsys.readouterr().out)) == (
        code,
        [f"{path}:{line}" for line in lines],
    )
