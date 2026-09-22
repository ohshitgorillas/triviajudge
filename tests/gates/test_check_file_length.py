"""The length gate: the hard cap, the ratchet above the watch line, and the allowance audit.

Every case writes its own files under ``tmp_path`` and hands ``check`` an
explicit allowance mapping, so the repository's own table is never what is under
test. The gate measures relative paths off the current directory and reads the
first path segment to tell a test file from a source file, so each case runs
with the current directory moved into ``tmp_path``.

Lengths and limits are written as literals, and every refusal the gate can print
is seeded below as the exact line expected. A case asserts the verdict pair —
the exit code and everything printed — so a finding that names the wrong file,
measures the wrong length or quotes the wrong limit fails the case.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

import check_file_length as GATE

if TYPE_CHECKING:
    import pytest

SUMMARY = "A watched file only ever gets shorter."

CAP_OVER_SOURCE = "pkg/over_the_cap.py: 501 lines (max 500) — split it"
CAP_OVER_TESTS = "tests/test_over_the_cap.py: 801 lines (max 800) — split it"

RATCHET_NO_ENTRY = "pkg/watched.py: 437 lines, over the 400-line watch line — add an ALLOWANCE entry of 437"
RATCHET_OVER_ENTRY = "pkg/watched.py: 450 lines, over its allowance of 421 — split it, the allowance does not rise"
RATCHET_UNDER_ENTRY = (
    "pkg/watched.py: 412 lines, under its allowance of 455 — lower the entry to 412"
)

STALE_NO_FILE = "ALLOWANCE['pkg/gone.py']: names no file"
STALE_TEST_PATH = "ALLOWANCE['tests/test_watched.py']: names a test path, which the ratchet does not govern"
STALE_UNDER_WATCH_LINE = (
    "ALLOWANCE['pkg/shrunk.py']: file is back under the 400-line watch line — drop it"
)

ARGV_CAP = "pkg/named.py: 501 lines (max 500) — split it"
ARGV_NO_ENTRY = "pkg/named.py: 501 lines, over the 400-line watch line — add an ALLOWANCE entry of 501"

PASSED = (0, "")


def written(name: str, lines: int) -> str:
    """Write a file of ``lines`` lines at ``name``, relative to the current directory."""
    path = Path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(f"# {number}\n" for number in range(lines)), encoding="utf-8"
    )
    return name


def printed(capsys: pytest.CaptureFixture[str]) -> str:
    """Everything the gate printed."""
    return capsys.readouterr().out


def refusal(*findings: str) -> str:
    """The full text the gate prints for ``findings``: each one, then the count and the rule."""
    return (
        "".join(f"{finding}\n" for finding in findings)
        + f"\n{len(findings)} problem(s). {SUMMARY}\n"
    )


# --- behavior 1: the cap refuses a file outright, at its own limit per tree ---


def test_a_source_file_at_the_cap_passes_without_a_word(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    code = GATE.check([written("pkg/at_the_cap.py", 500)], {"pkg/at_the_cap.py": 500})
    assert (code, printed(capsys)) == PASSED


def test_a_source_file_over_the_cap_is_named_with_its_length_and_the_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    code = GATE.check(
        [written("pkg/over_the_cap.py", 501)], {"pkg/over_the_cap.py": 501}
    )
    assert (code, printed(capsys)) == (1, refusal(CAP_OVER_SOURCE))


def test_a_test_file_past_the_source_cap_is_held_to_the_wider_test_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    code = GATE.check([written("tests/test_wide.py", 800)], {})
    assert (code, printed(capsys)) == PASSED


def test_a_test_file_over_the_test_cap_is_named_with_its_length_and_the_test_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    code = GATE.check([written("tests/test_over_the_cap.py", 801)], {})
    assert (code, printed(capsys)) == (1, refusal(CAP_OVER_TESTS))


# --- behavior 2: above the watch line a source file carries an entry, and only shrinks ---


def test_a_source_file_at_the_watch_line_needs_no_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    code = GATE.check([written("pkg/watched.py", 400)], {})
    assert (code, printed(capsys)) == PASSED


def test_a_watched_file_with_no_entry_is_told_the_length_to_write_down(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    code = GATE.check([written("pkg/watched.py", 437)], {})
    assert (code, printed(capsys)) == (1, refusal(RATCHET_NO_ENTRY))


def test_a_watched_file_at_the_length_its_entry_permits_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    code = GATE.check([written("pkg/watched.py", 450)], {"pkg/watched.py": 450})
    assert (code, printed(capsys)) == PASSED


def test_a_watched_file_over_its_entry_is_measured_against_the_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    code = GATE.check([written("pkg/watched.py", 450)], {"pkg/watched.py": 421})
    assert (code, printed(capsys)) == (1, refusal(RATCHET_OVER_ENTRY))


def test_a_watched_file_under_its_entry_is_told_the_length_to_lower_it_to(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    code = GATE.check([written("pkg/watched.py", 412)], {"pkg/watched.py": 455})
    assert (code, printed(capsys)) == (1, refusal(RATCHET_UNDER_ENTRY))


def test_the_ratchet_does_not_reach_a_test_file_over_the_watch_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    code = GATE.check([written("tests/test_long.py", 460)], {})
    assert (code, printed(capsys)) == PASSED


# --- behavior 3: the table is audited off the filesystem, not off the paths handed over ---


def test_an_entry_the_ratchet_can_enforce_stands_with_no_path_handed_over(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    written("pkg/watched.py", 430)
    code = GATE.check([], {"pkg/watched.py": 430})
    assert (code, printed(capsys)) == PASSED


def test_an_entry_naming_no_file_is_refused_by_its_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    code = GATE.check([], {"pkg/gone.py": 430})
    assert (code, printed(capsys)) == (1, refusal(STALE_NO_FILE))


def test_an_entry_naming_a_test_path_is_refused_as_ungoverned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    written("tests/test_watched.py", 430)
    code = GATE.check([], {"tests/test_watched.py": 430})
    assert (code, printed(capsys)) == (1, refusal(STALE_TEST_PATH))


def test_an_entry_whose_file_fell_under_the_watch_line_is_refused_as_droppable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    written("pkg/shrunk.py", 120)
    code = GATE.check([], {"pkg/shrunk.py": 430})
    assert (code, printed(capsys)) == (1, refusal(STALE_UNDER_WATCH_LINE))


# --- behavior 4: argv names the files, and the module's own table governs -----


def test_the_command_line_passes_a_file_no_rule_touches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(GATE, "ALLOWANCE", {})
    monkeypatch.setattr(
        sys, "argv", ["check_file_length.py", written("pkg/named.py", 10)]
    )
    assert (GATE.main(), printed(capsys)) == PASSED


def test_the_command_line_reports_every_rule_the_file_it_names_breaks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(GATE, "ALLOWANCE", {})
    monkeypatch.setattr(
        sys, "argv", ["check_file_length.py", written("pkg/named.py", 501)]
    )
    assert (GATE.main(), printed(capsys)) == (1, refusal(ARGV_CAP, ARGV_NO_ENTRY))
