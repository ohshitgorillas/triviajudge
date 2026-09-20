"""The per-file coverage floor: what is under it, what is excused, and what the excuse must name.

The gate reads coverage.py's JSON report and refuses any file under the floor.
Three behaviors carry it. A report that is missing or measured nothing fails
rather than passing, because a tree that was never measured must not read as a
tree that measured clean. A file under the floor fails unless the exemption
table names it. An exemption naming no file in the report fails too, so an
excuse cannot outlive the file it excused.

Both checks run in one pass: a run that has a file under the floor and a stale
exemption reports both.

Every case here asserts the verdict the user reads — the file named, its
percentage against the floor, the exemption called stale — as the exit code
paired with the gate's whole stdout, against the text seeded below.
"""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING

import check_coverage_floor as GATE

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

#: The floor every case here holds files to, and the one the gate prints.
FLOOR = 90

#: What the gate prints when the report is missing, when it measured nothing,
#: and when everything cleared the floor.
NO_REPORT = "{report}: no coverage report — the suite must run before this gate\n"
MEASURED_NOTHING = "{report}: coverage report measured no files — nothing was checked\n"
ALL_CLEAR = "[ok] all {count} files cover at least {floor}%\n"

#: One line per file under the floor, worst first, and one per stale exemption.
EDGE_UNDER = "edge.py: 89.90% (floor 90%)\n"
COLD_UNDER = "cold.py: 10.00% (floor 90%)\n"
WARM_UNDER = "warm.py: 80.00% (floor 90%)\n"
ONE_UNDER = "one.py: 89.00% (floor 90%)\n"
GONE_STALE = "EXEMPT['gone.py']: names no file in the coverage report\n"

#: The closing block, which counts the problems and says what clears them.
SUMMARY = (
    "\n{problems} problem(s). Every file covers at least {floor}%, or carries a\n"
    "reason in EXEMPT saying what about it has no behavior to assert.\n"
)


def report_of(tmp_path: Path, measured: dict[str, float]) -> Path:
    """A coverage JSON report carrying one percentage per named file."""
    report = tmp_path / "coverage.json"
    files = {name: {"summary": {"percent_covered": pct}} for name, pct in measured.items()}
    report.write_text(json.dumps({"files": files}), encoding="utf-8")
    return report


# --- behavior 1: a report that says nothing is a refusal, never a pass -------


def test_a_report_that_was_never_written_is_refused_by_name(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    absent = tmp_path / "absent.json"
    code = GATE.check(absent, FLOOR, {})
    assert (code, capsys.readouterr().out) == (1, NO_REPORT.format(report=absent))


def test_a_report_measuring_no_file_says_nothing_was_checked(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = report_of(tmp_path, {})
    code = GATE.check(report, FLOOR, {})
    assert (code, capsys.readouterr().out) == (1, MEASURED_NOTHING.format(report=report))


def test_a_report_with_no_files_key_says_nothing_was_checked(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = tmp_path / "coverage.json"
    report.write_text(json.dumps({"meta": {}}), encoding="utf-8")
    code = GATE.check(report, FLOOR, {})
    assert (code, capsys.readouterr().out) == (1, MEASURED_NOTHING.format(report=report))


# --- behavior 2: the floor is per file, and the boundary value passes --------


def test_a_file_exactly_at_the_floor_clears_it(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = GATE.check(report_of(tmp_path, {"edge.py": 90.0}), FLOOR, {})
    assert (code, capsys.readouterr().out) == (0, ALL_CLEAR.format(count=1, floor=FLOOR))


def test_a_file_just_under_the_floor_is_named_with_its_percentage(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = GATE.check(report_of(tmp_path, {"edge.py": 89.9}), FLOOR, {})
    expected = EDGE_UNDER + SUMMARY.format(problems=1, floor=FLOOR)
    assert (code, capsys.readouterr().out) == (1, expected)


def test_the_files_under_the_floor_are_printed_worst_first(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    report = report_of(tmp_path, {"warm.py": 80.0, "cold.py": 10.0, "hot.py": 95.0})
    code = GATE.check(report, FLOOR, {})
    expected = COLD_UNDER + WARM_UNDER + SUMMARY.format(problems=2, floor=FLOOR)
    assert (code, capsys.readouterr().out) == (1, expected)


def test_each_percentage_comes_from_that_file_s_own_summary(tmp_path: Path) -> None:
    report = tmp_path / "coverage.json"
    files = {
        "one.py": {"summary": {"percent_covered": 42.5, "num_statements": 8}, "missing_lines": [3]},
        "two.py": {"summary": {"percent_covered": 100.0, "num_statements": 2}, "missing_lines": []},
    }
    report.write_text(json.dumps({"meta": {"branch_coverage": True}, "files": files}), encoding="utf-8")
    assert GATE.percentages(report) == {"one.py": 42.5, "two.py": 100.0}


# --- behavior 3: an exemption excuses one file, and must name a measured one --


def test_an_exempt_file_under_the_floor_leaves_the_tree_clear(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = report_of(tmp_path, {"one.py": 10.0})
    code = GATE.check(report, FLOOR, {"one.py": "no behavior to assert"})
    assert (code, capsys.readouterr().out) == (0, ALL_CLEAR.format(count=1, floor=FLOOR))


def test_the_stale_exemption_is_named_and_the_live_one_is_not(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exempt = {"one.py": "no behavior to assert", "gone.py": "no behavior to assert"}
    code = GATE.check(report_of(tmp_path, {"one.py": 50.0}), FLOOR, exempt)
    expected = GONE_STALE + SUMMARY.format(problems=1, floor=FLOOR)
    assert (code, capsys.readouterr().out) == (1, expected)


def test_a_file_under_the_floor_and_a_stale_exemption_are_both_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = GATE.check(report_of(tmp_path, {"cold.py": 10.0}), FLOOR, {"gone.py": "held"})
    expected = COLD_UNDER + GONE_STALE + SUMMARY.format(problems=2, floor=FLOOR)
    assert (code, capsys.readouterr().out) == (1, expected)


# --- behavior 4: the CLI takes the report and the floor, or falls back -------


def test_the_cli_judges_the_report_and_floor_it_is_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    report = report_of(tmp_path, {"one.py": 50.0})
    monkeypatch.setattr(sys, "argv", ["check_coverage_floor.py", str(report), "40"])
    monkeypatch.setattr(GATE, "EXEMPT", {})
    code = GATE.main()
    assert (code, capsys.readouterr().out) == (0, ALL_CLEAR.format(count=1, floor=40))


def test_the_cli_falls_back_to_this_repository_s_report_and_floor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["check_coverage_floor.py"])
    monkeypatch.setattr(GATE, "REPORT", report_of(tmp_path, {"one.py": 89.0}))
    monkeypatch.setattr(GATE, "EXEMPT", {})
    code = GATE.main()
    expected = ONE_UNDER + SUMMARY.format(problems=1, floor=FLOOR)
    assert (code, capsys.readouterr().out) == (1, expected)


def test_the_default_exemption_table_is_the_module_s_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(GATE, "EXEMPT", {"one.py": "no behavior to assert"})
    code = GATE.check(report_of(tmp_path, {"one.py": 1.0}), FLOOR)
    assert (code, capsys.readouterr().out) == (0, ALL_CLEAR.format(count=1, floor=FLOOR))
