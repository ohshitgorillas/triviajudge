"""The suite-time ratchet: what is judged, what is recorded, and what the owner has to say.

The gate reads the junit report the suite writes and compares its wall time with
the last green run's. Every case here pins the verdict the user reads: the exit
code together with the line printed, and the baseline value left behind. A report
that is missing, carries no ``<testsuite>``, or came from a red suite is refused
and records nothing, because an aborted run looks fast. A missing baseline is
seeded from the report, so a fresh checkout is not red on its first run. A run
within the escalate band passes and becomes the new baseline; one past it needs
``--accept``; one at or past the reject band is refused either way. And the
baseline is resolved to the main checkout, so a worktree compares against the
tree it was cut from.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import check_suite_time as GATE
import pytest

if TYPE_CHECKING:
    from pathlib import Path

#: The lines the gate prints, as the user reads them, one per verdict under test.
NO_REPORT = "{report}: no junit report; the suite must run before this gate"
NOTHING_MEASURED = "{report}: no <testsuite time=...> in the report; nothing was measured"
SUITE_RED = "{report}: suite red, time not judged"
SEEDED_4S = "[ok] suite 4.0s, no baseline yet: recorded as the bar"
SEEDED_3S = "[ok] suite 3.0s, no baseline yet: recorded as the bar"
INSIDE_BAND_11S = "[ok] suite 11.0s, last green 10.0s (+1.0s)"
ESCALATE_16S = "suite 16.0s, last green 10.0s: +6.0s, escalate to owner (--accept)"
ACCEPTED_16S = "suite 16.0s, last green 10.0s: +6.0s accepted by the owner"
REJECTED_25S = "suite 25.0s, last green 10.0s: +15.0s, rejected (limit 10s)"


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


def verdict(
    report: Path,
    baseline: Path,
    capsys: pytest.CaptureFixture[str],
    *,
    accept: bool = False,
) -> tuple[int, str, float | None]:
    """The gate's whole verdict: exit code, the line printed, and the baseline left behind."""
    code = GATE.check(report, baseline, accept=accept)
    return code, capsys.readouterr().out.strip(), GATE.read_baseline(baseline)


# --- behavior 1: an unjudgeable report is a refusal, and records nothing -----


def test_a_report_that_was_never_written_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    report = tmp_path / "absent.xml"
    assert verdict(report, tmp_path / "baseline.json", capsys) == (1, NO_REPORT.format(report=report), None)


def test_a_report_with_no_testsuite_element_measured_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = tmp_path / "junit.xml"
    report.write_text("<?xml version='1.0'?><testsuites></testsuites>", encoding="utf-8")
    expected = NOTHING_MEASURED.format(report=report)
    assert verdict(report, tmp_path / "baseline.json", capsys) == (1, expected, None)


def test_a_report_stating_no_time_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    report = report_of(tmp_path, 'name="pytest" errors="0" failures="0"')
    expected = NOTHING_MEASURED.format(report=report)
    assert verdict(report, tmp_path / "baseline.json", capsys) == (1, expected, None)


@pytest.mark.parametrize("attrs", ['errors="0" failures="2" time="3.0"', 'errors="1" failures="0" time="3.0"'])
def test_a_red_suite_is_not_judged_and_records_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], attrs: str
) -> None:
    report = report_of(tmp_path, attrs)
    assert verdict(report, tmp_path / "baseline.json", capsys) == (1, SUITE_RED.format(report=report), None)


# --- behavior 2: no baseline yet is seeded rather than refused ---------------


def test_a_first_run_is_recorded_as_the_bar(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert verdict(timed(tmp_path, 4.0), tmp_path / "baseline.json", capsys) == (0, SEEDED_4S, 4.0)


# --- behavior 3: the bands, and which of them the owner can wave through -----


@pytest.mark.parametrize(
    ("seconds", "accept", "expected"),
    [
        (9.0, False, (True, "[ok] suite 9.0s, last green 10.0s (-1.0s)")),
        (14.9, False, (True, "[ok] suite 14.9s, last green 10.0s (+4.9s)")),
        (15.0, False, (True, "[ok] suite 15.0s, last green 10.0s (+5.0s)")),
        (16.0, False, (False, ESCALATE_16S)),
        (16.0, True, (True, ACCEPTED_16S)),
        (19.9, True, (True, "suite 19.9s, last green 10.0s: +9.9s accepted by the owner")),
        (20.0, True, (False, "suite 20.0s, last green 10.0s: +10.0s, rejected (limit 10s)")),
        (25.0, False, (False, REJECTED_25S)),
    ],
)
def test_a_run_is_judged_against_the_last_green_run(seconds: float, accept: bool, expected: tuple[bool, str]) -> None:
    assert GATE.judge(seconds, 10.0, accept=accept) == expected


def test_a_run_inside_the_band_becomes_the_new_baseline(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    baseline = baseline_of(tmp_path, 10.0)
    assert verdict(timed(tmp_path, 11.0), baseline, capsys) == (0, INSIDE_BAND_11S, 11.0)


def test_a_run_past_the_band_is_escalated_and_records_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    baseline = baseline_of(tmp_path, 10.0)
    assert verdict(timed(tmp_path, 16.0), baseline, capsys) == (1, ESCALATE_16S, 10.0)


def test_a_run_the_owner_accepts_becomes_the_new_baseline(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    baseline = baseline_of(tmp_path, 10.0)
    assert verdict(timed(tmp_path, 16.0), baseline, capsys, accept=True) == (0, ACCEPTED_16S, 16.0)


def test_a_rejected_run_leaves_the_baseline_where_it_was(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    baseline = baseline_of(tmp_path, 10.0)
    assert verdict(timed(tmp_path, 25.0), baseline, capsys, accept=True) == (1, REJECTED_25S, 10.0)


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


def test_the_cli_judges_this_tree_s_report_and_seeds_beside_the_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(GATE, "ROOT", tmp_path)
    timed(tmp_path, 3.0).rename(tmp_path / GATE.REPORT_NAME)
    code = GATE.main([])
    printed = capsys.readouterr().out.strip()
    assert (code, printed, GATE.read_baseline(tmp_path / GATE.BASELINE_NAME)) == (0, SEEDED_3S, 3.0)


def test_the_cli_takes_the_accept_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(GATE, "ROOT", tmp_path)
    timed(tmp_path, 16.0).rename(tmp_path / GATE.REPORT_NAME)
    baseline_of(tmp_path, 10.0).rename(tmp_path / GATE.BASELINE_NAME)
    code = GATE.main(["--accept"])
    printed = capsys.readouterr().out.strip()
    assert (code, printed, GATE.read_baseline(tmp_path / GATE.BASELINE_NAME)) == (0, ACCEPTED_16S, 16.0)


def test_the_cli_reads_argv_when_it_is_handed_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(GATE, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["check_suite_time.py"])
    timed(tmp_path, 3.0).rename(tmp_path / GATE.REPORT_NAME)
    code = GATE.main()
    assert (code, capsys.readouterr().out.strip()) == (0, SEEDED_3S)
