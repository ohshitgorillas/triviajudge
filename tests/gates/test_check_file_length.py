"""The length gate: the hard cap, the ratchet above the watch line, and the allowance audit.

Every case writes its own files under ``tmp_path`` and hands ``check`` an
explicit allowance mapping, so the repository's own table is never what is under
test. The gate measures relative paths off the current directory and reads the
first path segment to tell a test file from a source file, so each case runs
with the current directory moved into ``tmp_path``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import check_file_length as GATE
import pytest


def written(name: str, lines: int) -> str:
    """Write a file of ``lines`` lines at ``name``, relative to the current directory."""
    path = Path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"# {number}\n" for number in range(lines)), encoding="utf-8")
    return name


def printed(capsys: pytest.CaptureFixture[str]) -> str:
    """Everything the gate printed."""
    return capsys.readouterr().out


# --- behavior 1: the cap refuses a file outright, at its own limit per tree ---


@pytest.mark.parametrize(
    ("name", "lines", "allowance", "code"),
    [
        ("pkg/small.py", 10, {}, 0),
        ("pkg/at_the_cap.py", GATE.MAX_LINES, {"pkg/at_the_cap.py": GATE.MAX_LINES}, 0),
        ("pkg/over_the_cap.py", GATE.MAX_LINES + 1, {"pkg/over_the_cap.py": GATE.MAX_LINES + 1}, 1),
        ("tests/test_wide.py", GATE.MAX_LINES + 1, {}, 0),
        ("tests/test_at_the_cap.py", GATE.MAX_LINES_TESTS, {}, 0),
        ("tests/test_over_the_cap.py", GATE.MAX_LINES_TESTS + 1, {}, 1),
    ],
)
def test_a_file_passes_until_it_is_longer_than_the_limit_for_its_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    name: str,
    lines: int,
    allowance: dict[str, int],
    code: int,
) -> None:
    monkeypatch.chdir(tmp_path)
    assert GATE.check([written(name, lines)], allowance) == code


# --- behavior 2: above the watch line a source file carries an entry, and only shrinks ---


@pytest.mark.parametrize(
    ("lines", "allowance", "code"),
    [
        (GATE.WATCH_LINE, {}, 0),
        (GATE.WATCH_LINE + 1, {}, 1),
        (450, {"pkg/watched.py": 450}, 0),
        (450, {"pkg/watched.py": 420}, 1),
        (410, {"pkg/watched.py": 450}, 1),
    ],
)
def test_the_ratchet_holds_a_watched_file_to_the_length_its_entry_permits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, lines: int, allowance: dict[str, int], code: int
) -> None:
    monkeypatch.chdir(tmp_path)
    assert GATE.check([written("pkg/watched.py", lines)], allowance) == code


def test_a_watched_file_with_no_entry_is_told_the_length_to_write_down(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    GATE.check([written("pkg/watched.py", 437)], {})
    assert "437" in printed(capsys)


def test_a_file_over_its_entry_is_measured_against_the_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    GATE.check([written("pkg/watched.py", 450)], {"pkg/watched.py": 421})
    assert "421" in printed(capsys)


def test_a_file_under_its_entry_is_told_the_length_to_lower_it_to(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    GATE.check([written("pkg/watched.py", 412)], {"pkg/watched.py": 455})
    assert "412" in printed(capsys)


def test_the_ratchet_does_not_reach_a_test_file_over_the_watch_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert GATE.check([written("tests/test_long.py", GATE.WATCH_LINE + 60)], {}) == 0


# --- behavior 3: the table is audited off the filesystem, not off the paths handed over ---


@pytest.mark.parametrize(
    ("existing", "lines", "key", "code"),
    [
        ("pkg/watched.py", 430, "pkg/watched.py", 0),
        (None, 0, "pkg/gone.py", 1),
        ("tests/test_watched.py", 430, "tests/test_watched.py", 1),
        ("pkg/shrunk.py", 120, "pkg/shrunk.py", 1),
    ],
)
def test_an_entry_stands_only_while_the_ratchet_can_enforce_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    existing: str | None,
    lines: int,
    key: str,
    code: int,
) -> None:
    monkeypatch.chdir(tmp_path)
    if existing is not None:
        written(existing, lines)
    assert GATE.check([], {key: 430}) == code


def test_an_unenforceable_entry_is_named_by_its_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    GATE.check([], {"pkg/gone.py": 430})
    assert "pkg/gone.py" in printed(capsys)


# --- behavior 4: argv names the files, and the module's own table governs -----


@pytest.mark.parametrize(("lines", "code"), [(10, 0), (GATE.MAX_LINES + 1, 1)])
def test_the_command_line_checks_the_files_it_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, lines: int, code: int
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(GATE, "ALLOWANCE", {})
    monkeypatch.setattr(sys, "argv", ["check_file_length.py", written("pkg/named.py", lines)])
    assert GATE.main() == code
