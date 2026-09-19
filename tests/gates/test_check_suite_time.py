"""The suite-time ratchet: what is judged, what is recorded, and what the owner has to say.

The gate reads the junit report the suite writes and compares its wall time with
the last green run's. Four behaviors carry it. A report that is missing, carries
no time, or came from a red suite is not judged and not recorded, because an
aborted run looks fast. A missing baseline is seeded from the report, so a fresh
checkout is not red on its first run. A run within the escalate band passes and
becomes the new baseline; one past it needs ``--accept``; one at or past the
reject band is refused either way. And the baseline is resolved to the main
checkout, so a worktree compares against the tree it was cut from.
"""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING

import check_suite_time as GATE
import pytest

if TYPE_CHECKING:
    from pathlib import Path


def report_of(tmp_path: Path, attrs: str) -> Path:
    """A junit report whose ``<testsuite>`` element carries the given attributes."""
    report = tmp_path / "junit.xml"
    element = f"<testsuite {attrs}></testsuite>"
    report.write_text(f'<?xml version="1.0"?><testsuites>{element}</testsuites>', encoding="utf-8")
    return report


def timed(tmp_path: Path, seconds: float) -> Path:
    """A green junit report for a run of ``seconds``."""
    return report_of(tmp_path, f'name="pytest" errors="0" failures="0" time="{seconds}"')


def baseline_of(tmp_path: Path, seconds: float) -> Path:
    """A baseline file recording ``seconds`` as the last green run."""
    baseline = tmp_path / "suite-time.json"
    GATE.record(baseline, seconds)
    return baseline


# --- behavior 1: an unjudgeable report is a refusal, and records nothing -----


def test_a_report_that_was_never_written_is_refused(tmp_path: Path) -> None:
    assert GATE.check(tmp_path / "absent.xml", tmp_path / "baseline.json") == 1


def test_a_report_with_no_testsuite_element_carries_no_attributes(tmp_path: Path) -> None:
    report = tmp_path / "junit.xml"
    report.write_text("<?xml version='1.0'?><testsuites></testsuites>", encoding="utf-8")
    assert GATE.suite_attrs(report) == {}


def test_a_report_stating_no_time_is_refused(tmp_path: Path) -> None:
    report = report_of(tmp_path, 'name="pytest" errors="0" failures="0"')
    assert GATE.check(report, tmp_path / "baseline.json") == 1


@pytest.mark.parametrize("attrs", ['errors="0" failures="2" time="3.0"', 'errors="1" failures="0" time="3.0"'])
def test_a_red_suite_is_not_judged(tmp_path: Path, attrs: str) -> None:
    assert GATE.check(report_of(tmp_path, attrs), tmp_path / "baseline.json") == 1


def test_a_red_suite_records_no_baseline(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    GATE.check(report_of(tmp_path, 'errors="0" failures="2" time="3.0"'), baseline)
    assert not baseline.is_file()


# --- behavior 2: no baseline yet is seeded rather than refused ---------------


def test_a_first_run_is_recorded_as_the_bar(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    assert GATE.check(timed(tmp_path, 4.0), baseline) == 0


def test_a_first_run_leaves_its_own_time_behind(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    GATE.check(timed(tmp_path, 4.0), baseline)
    assert GATE.read_baseline(baseline) == 4.0


def test_an_unwritten_baseline_reads_as_nothing_recorded(tmp_path: Path) -> None:
    assert GATE.read_baseline(tmp_path / "baseline.json") is None


# --- behavior 3: the bands, and which of them the owner can wave through -----


@pytest.mark.parametrize(
    ("seconds", "accept", "passes"),
    [
        (9.0, False, True),
        (14.9, False, True),
        (15.0, False, True),
        (16.0, False, False),
        (16.0, True, True),
        (19.9, True, True),
        (20.0, True, False),
        (25.0, False, False),
    ],
)
def test_a_run_is_judged_against_the_last_green_run(seconds: float, accept: bool, passes: bool) -> None:
    assert GATE.judge(seconds, 10.0, accept=accept)[0] is passes


@pytest.mark.parametrize(("seconds", "code"), [(11.0, 0), (16.0, 1), (25.0, 1)])
def test_the_exit_code_follows_the_band(tmp_path: Path, seconds: float, code: int) -> None:
    baseline = baseline_of(tmp_path, 10.0)
    assert GATE.check(timed(tmp_path, seconds), baseline) == code


def test_a_run_inside_the_band_becomes_the_new_baseline(tmp_path: Path) -> None:
    baseline = baseline_of(tmp_path, 10.0)
    GATE.check(timed(tmp_path, 11.0), baseline)
    assert GATE.read_baseline(baseline) == 11.0


def test_a_run_the_owner_accepts_becomes_the_new_baseline(tmp_path: Path) -> None:
    baseline = baseline_of(tmp_path, 10.0)
    GATE.check(timed(tmp_path, 16.0), baseline, accept=True)
    assert GATE.read_baseline(baseline) == 16.0


def test_a_rejected_run_leaves_the_baseline_where_it_was(tmp_path: Path) -> None:
    baseline = baseline_of(tmp_path, 10.0)
    GATE.check(timed(tmp_path, 25.0), baseline, accept=True)
    assert GATE.read_baseline(baseline) == 10.0


# --- behavior 4: the baseline belongs to the main checkout -------------------


def test_a_plain_checkout_is_its_own_main_checkout(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    assert GATE.main_checkout(tmp_path) == tmp_path


@pytest.mark.parametrize("absolute", [True, False])
def test_a_worktree_resolves_to_the_tree_it_was_cut_from(tmp_path: Path, absolute: bool) -> None:
    main = tmp_path / "main"
    (main / ".git" / "worktrees" / "side").mkdir(parents=True)
    worktree = tmp_path / "side"
    worktree.mkdir()
    gitdir = main / ".git" / "worktrees" / "side"
    (gitdir / "commondir").write_text("../..\n", encoding="utf-8")
    named = str(gitdir) if absolute else "../main/.git/worktrees/side"
    (worktree / ".git").write_text(f"gitdir: {named}\n", encoding="utf-8")
    assert GATE.main_checkout(worktree) == main.resolve()


# --- behavior 5: the CLI resolves both files and reads --accept -------------


def test_the_cli_judges_this_tree_s_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(GATE, "ROOT", tmp_path)
    timed(tmp_path, 3.0).rename(tmp_path / GATE.REPORT_NAME)
    assert GATE.main([]) == 0


def test_the_cli_seeds_the_baseline_beside_the_checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(GATE, "ROOT", tmp_path)
    timed(tmp_path, 3.0).rename(tmp_path / GATE.REPORT_NAME)
    GATE.main([])
    assert json.loads((tmp_path / GATE.BASELINE_NAME).read_text(encoding="utf-8")) == {"seconds": 3.0}


def test_the_cli_takes_the_accept_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(GATE, "ROOT", tmp_path)
    timed(tmp_path, 16.0).rename(tmp_path / GATE.REPORT_NAME)
    baseline_of(tmp_path, 10.0).rename(tmp_path / GATE.BASELINE_NAME)
    assert GATE.main(["--accept"]) == 0


def test_the_cli_reads_argv_when_it_is_handed_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(GATE, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["check_suite_time.py"])
    timed(tmp_path, 3.0).rename(tmp_path / GATE.REPORT_NAME)
    assert GATE.main() == 0
