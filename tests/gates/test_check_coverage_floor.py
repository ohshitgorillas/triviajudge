"""The per-file coverage floor: what is under it, what is excused, and what the excuse must name.

The gate reads coverage.py's JSON report and refuses any file under the floor.
Three behaviors carry it. A report that is missing or measured nothing fails
rather than passing, because a tree that was never measured must not read as a
tree that measured clean. A file under the floor fails unless the exemption
table names it. An exemption naming no file in the report fails too, so an
excuse cannot outlive the file it excused.

Both checks run in one pass: a run that has a file under the floor and a stale
exemption reports both.
"""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING

import check_coverage_floor as GATE
import pytest

if TYPE_CHECKING:
    from pathlib import Path


def report_of(tmp_path: Path, measured: dict[str, float]) -> Path:
    """A coverage JSON report carrying one percentage per named file."""
    report = tmp_path / "coverage.json"
    files = {name: {"summary": {"percent_covered": pct}} for name, pct in measured.items()}
    report.write_text(json.dumps({"files": files}), encoding="utf-8")
    return report


# --- behavior 1: a report that says nothing is a refusal, never a pass -------


def test_a_report_that_was_never_written_is_refused(tmp_path: Path) -> None:
    assert GATE.check(tmp_path / "absent.json", 90, {}) == 1


def test_a_report_measuring_no_file_is_refused(tmp_path: Path) -> None:
    assert GATE.check(report_of(tmp_path, {}), 90, {}) == 1


def test_a_report_with_no_files_key_measures_nothing(tmp_path: Path) -> None:
    report = tmp_path / "coverage.json"
    report.write_text(json.dumps({"meta": {}}), encoding="utf-8")
    assert GATE.check(report, 90, {}) == 1


# --- behavior 2: the floor is per file, and the boundary value passes --------


@pytest.mark.parametrize(("percent", "code"), [(100.0, 0), (90.0, 0), (89.9, 1), (0.0, 1)])
def test_a_file_passes_exactly_when_it_reaches_the_floor(tmp_path: Path, percent: float, code: int) -> None:
    assert GATE.check(report_of(tmp_path, {"one.py": percent}), 90, {}) == code


def test_the_failing_file_is_named(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    GATE.check(report_of(tmp_path, {"cold.py": 12.0}), 90, {})
    assert "cold.py" in capsys.readouterr().out


def test_the_files_under_the_floor_are_reported_worst_first() -> None:
    measured = {"warm.py": 80.0, "cold.py": 10.0, "hot.py": 95.0}
    assert GATE.below(measured, 90, {}) == ["cold.py", "warm.py"]


def test_the_percentages_are_read_off_the_report(tmp_path: Path) -> None:
    assert GATE.percentages(report_of(tmp_path, {"one.py": 42.5})) == {"one.py": 42.5}


# --- behavior 3: an exemption excuses one file, and must name a measured one --


def test_an_exempt_file_may_sit_under_the_floor(tmp_path: Path) -> None:
    report = report_of(tmp_path, {"one.py": 10.0})
    assert GATE.check(report, 90, {"one.py": "no behavior to assert"}) == 0


def test_an_exemption_naming_no_measured_file_is_refused(tmp_path: Path) -> None:
    report = report_of(tmp_path, {"one.py": 95.0})
    assert GATE.check(report, 90, {"gone.py": "no behavior to assert"}) == 1


def test_the_stale_exemption_is_named(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    GATE.check(report_of(tmp_path, {"one.py": 95.0}), 90, {"gone.py": "no behavior to assert"})
    assert "gone.py" in capsys.readouterr().out


def test_only_the_keys_naming_no_measured_file_are_stale() -> None:
    exempt = {"one.py": "held", "gone.py": "held"}
    assert GATE.stale({"one.py": 95.0}, exempt) == ["gone.py"]


def test_a_file_under_the_floor_and_a_stale_exemption_are_both_counted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    GATE.check(report_of(tmp_path, {"cold.py": 10.0}), 90, {"gone.py": "held"})
    assert "2 problem(s)" in capsys.readouterr().out


# --- behavior 4: the CLI takes the report and the floor, or falls back -------


def test_the_cli_judges_the_report_and_floor_it_is_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    report = report_of(tmp_path, {"one.py": 50.0})
    monkeypatch.setattr(sys, "argv", ["check_coverage_floor.py", str(report), "40"])
    monkeypatch.setattr(GATE, "EXEMPT", {})
    GATE.main()
    assert "[ok] all 1 files" in capsys.readouterr().out


def test_the_cli_falls_back_to_this_repository_s_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["check_coverage_floor.py"])
    monkeypatch.setattr(GATE, "REPORT", report_of(tmp_path, {"one.py": 99.0}))
    monkeypatch.setattr(GATE, "EXEMPT", {})
    assert GATE.main() == 0


def test_the_default_exemption_table_is_the_module_s_own(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(GATE, "EXEMPT", {"one.py": "no behavior to assert"})
    assert GATE.check(report_of(tmp_path, {"one.py": 1.0}), 90) == 0
