"""The clock gate: a test that sleeps on a real clock, or holds a deadline the code waits out.

A sleep counts whatever its argument is spelled as, and a zero sleep is a
scheduler yield rather than a wait. A deadline counts by its value: seconds is a
ceiling, a fraction of a second is a wait. There is no carve-out directory.

Each case that should pass sits in a source with one real clock on the next line,
so the verdict under test is the single finding naming that one line rather than
an empty list. The expected findings and the gate's two verdict lines are seeded
here as text, so a reworded sentence or a shifted line number fails.
"""

import sys
from pathlib import Path

import check_test_clocks as GATE
import pytest

NAME = "test_case.py"

SLEEP_FAULT = "{name}:{line}: sleeps on a real clock"

KEYWORD_FAULT = "{name}:{line}: {arg}= is a real deadline under 0.5s"

MAPPING_FAULT = "{name}:{line}: 'timeout' is a real deadline under 0.5s"

REFUSAL_TAIL = (
    "\n1 real clock(s) under tests/. A poll waits on a condition and a deadline\n"
    "comes from a seam the test controls; CONTRIBUTING.md is the rule.\n"
)

CLEAN_LINE = "[ok] 1 test file(s) read no real clock\n"

SLEEPS = "import time\n\ntime.sleep(1)\n"

YIELD_THEN_SLEEP = "import time\n\ntime.sleep(0)\ntime.sleep(1)\n"

ON_A_NAME = "import time\n\nPAUSE = 0.01\ntime.sleep(PAUSE)\n"

ON_A_FAKE_THEN_SLEEP = "import time\n\nclock.sleep(1)\ntime.sleep(1)\n"

DEADLINE = "poll(timeout=0.05)\n"

CEILING_THEN_DEADLINE = "poll(timeout=5)\npoll(timeout=0.05)\n"

NAMED_DEADLINE = "connect(read_timeout=0.2)\n"

MAPPING = "CONFIG = {'timeout': 0.05}\n"

CLEAN = "def test_a_verdict() -> None:\n    assert judge() == 1\n"


def written(tmp_path: Path, source: str) -> str:
    """Put one test module in a throwaway tree and answer with its path."""
    path = tmp_path / NAME
    path.write_text(source, encoding="utf-8")
    return str(path)


# --- behavior 1: a sleep on a real clock ------------------------------------


def test_a_sleep_on_a_real_clock_is_named_by_its_line() -> None:
    assert GATE.faults(NAME, SLEEPS) == [SLEEP_FAULT.format(name=NAME, line=3)]


def test_a_zero_sleep_passes_and_only_the_waiting_sleep_below_it_is_named() -> None:
    assert GATE.faults(NAME, YIELD_THEN_SLEEP) == [
        SLEEP_FAULT.format(name=NAME, line=4)
    ]


def test_a_sleep_on_a_name_is_named_by_its_line_as_a_literal_one_is() -> None:
    assert GATE.faults(NAME, ON_A_NAME) == [SLEEP_FAULT.format(name=NAME, line=4)]


def test_a_sleep_on_a_seam_the_test_owns_passes_and_only_the_real_clock_is_named() -> (
    None
):
    assert GATE.faults(NAME, ON_A_FAKE_THEN_SLEEP) == [
        SLEEP_FAULT.format(name=NAME, line=4)
    ]


# --- behavior 2: a deadline the code waits out ------------------------------


def test_a_deadline_under_half_a_second_names_its_keyword_and_line() -> None:
    assert GATE.faults(NAME, DEADLINE) == [
        KEYWORD_FAULT.format(name=NAME, line=1, arg="timeout")
    ]


def test_a_deadline_in_seconds_passes_and_only_the_fraction_below_it_is_named() -> None:
    assert GATE.faults(NAME, CEILING_THEN_DEADLINE) == [
        KEYWORD_FAULT.format(name=NAME, line=2, arg="timeout")
    ]


def test_a_suffixed_keyword_is_named_by_the_keyword_it_was_spelled_with() -> None:
    assert GATE.faults(NAME, NAMED_DEADLINE) == [
        KEYWORD_FAULT.format(name=NAME, line=1, arg="read_timeout")
    ]


def test_a_mapping_key_is_named_by_the_key_it_was_spelled_with() -> None:
    assert GATE.faults(NAME, MAPPING) == [MAPPING_FAULT.format(name=NAME, line=1)]


# --- behavior 3: what the run prints is the verdict over the files handed over


def test_a_file_reading_no_clock_prints_the_clean_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = GATE.check([written(tmp_path, CLEAN)])
    assert (code, capsys.readouterr().out) == (0, CLEAN_LINE)


def test_one_real_clock_prints_its_line_and_the_refusal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = written(tmp_path, SLEEPS)
    code = GATE.check([path])
    assert (code, capsys.readouterr().out) == (
        1,
        SLEEP_FAULT.format(name=path, line=3) + "\n" + REFUSAL_TAIL,
    )


# --- behavior 4: argv names the files ----------------------------------------


def test_main_names_the_clock_in_the_file_argv_gave(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = written(tmp_path, ON_A_NAME)
    monkeypatch.setattr(sys, "argv", ["check_test_clocks.py", path])
    code = GATE.main()
    assert (code, capsys.readouterr().out) == (
        1,
        SLEEP_FAULT.format(name=path, line=4) + "\n" + REFUSAL_TAIL,
    )
