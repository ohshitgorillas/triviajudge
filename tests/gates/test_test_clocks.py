"""The clock gate: a test that sleeps on a real clock, or holds a deadline the code waits out.

A sleep counts whatever its argument is spelled as, and a zero sleep is a
scheduler yield rather than a wait. A deadline counts by its value: seconds is a
ceiling, a fraction of a second is a wait. There is no carve-out directory.
"""

from pathlib import Path

import check_test_clocks as GATE

NAME = "test_case.py"

SLEEPS = "import time\n\ntime.sleep(1)\n"

YIELDS = "import time\n\ntime.sleep(0)\n"

ON_A_NAME = "import time\n\nPAUSE = 0.01\ntime.sleep(PAUSE)\n"

ON_A_FAKE = "clock.sleep(1)\n"

DEADLINE = "poll(timeout=0.05)\n"

CEILING = "poll(timeout=5)\n"

NAMED_DEADLINE = "connect(read_timeout=0.2)\n"

MAPPING = "CONFIG = {'timeout': 0.05}\n"

CLEAN = "def test_a_verdict() -> None:\n    assert judge() == 1\n"


def written(tmp_path: Path, source: str) -> str:
    """Put one test module in a throwaway tree and answer with its path."""
    path = tmp_path / NAME
    path.write_text(source, encoding="utf-8")
    return str(path)


# --- behavior 1: a sleep on a real clock ------------------------------------


def test_a_sleep_on_a_real_clock_is_a_finding() -> None:
    assert len(GATE.faults(NAME, SLEEPS)) == 1


def test_a_zero_sleep_is_a_scheduler_yield() -> None:
    assert GATE.faults(NAME, YIELDS) == []


def test_a_sleep_on_a_name_counts_the_same_as_one_on_a_literal() -> None:
    assert len(GATE.faults(NAME, ON_A_NAME)) == 1


def test_a_sleep_on_a_seam_the_test_owns_waits_on_no_clock() -> None:
    assert GATE.faults(NAME, ON_A_FAKE) == []


# --- behavior 2: a deadline the code waits out ------------------------------


def test_a_deadline_under_half_a_second_is_a_finding() -> None:
    assert len(GATE.faults(NAME, DEADLINE)) == 1


def test_a_deadline_in_seconds_is_a_ceiling_a_test_never_reaches() -> None:
    assert GATE.faults(NAME, CEILING) == []


def test_a_suffixed_keyword_carries_a_deadline_too() -> None:
    assert len(GATE.faults(NAME, NAMED_DEADLINE)) == 1


def test_a_mapping_key_carries_a_deadline_too() -> None:
    assert len(GATE.faults(NAME, MAPPING)) == 1


# --- behavior 3: the gate's verdict over files ------------------------------


def test_a_file_holding_a_real_clock_fails_the_gate(tmp_path: Path) -> None:
    assert GATE.check([written(tmp_path, SLEEPS)]) == 1


def test_a_file_reading_no_clock_passes_the_gate(tmp_path: Path) -> None:
    assert GATE.check([written(tmp_path, CLEAN)]) == 0
