"""The suppression gate: a code names the check, and the reason names the argument.

Both suppressions are read out of comment tokens, so the sources below are data to
the gate rather than suppressions of their own. Ruff holds each to naming codes;
this gate holds each to stating why the check is wrong at that line.

A case whose point is that a line passes pairs that line with a silent suppression
on the next one, so the verdict has to name the second line and only it.
"""

from pathlib import Path

import check_noqa_reasons as GATE
import pytest

SILENT_NOQA = "value = call()  # noqa: S603\n"

STATED_THEN_SILENT = "first = call()  # noqa: S603 — argv is this module's own literals\nsecond = call()  # noqa: S607\n"

TWO_CODES = "value = call()  # noqa: S603, S607\n"

COLON_INSTEAD = "value = call()  # noqa: S603: argv is our own\n"

SILENT_IGNORE = "value = call()  # type: ignore[arg-type]\n"

STATED_IGNORE_THEN_SILENT = (
    "first = call()  # type: ignore[arg-type]  # — the keys are checked above\n"
    "second = call()  # type: ignore[arg-type]\n"
)

STRING_THEN_SILENT = 'TEXT = "# noqa: S603"\nvalue = call()  # noqa: S607\n'

PLAIN_THEN_SILENT = (
    "value = call()  # the value the caller asked for\nother = call()  # noqa: S603\n"
)

#: What the gate says after naming the suppression it refuses.
SILENT_TAIL = "states no reason — add ' — <why the check is wrong here>'"

#: How a finding names each suppression: the checker, then the codes it silences.
NOQA_S603 = "noqa S603"
NOQA_S607 = "noqa S607"
NOQA_BOTH = "noqa S603, S607"
IGNORE_ARG = "type: ignore arg-type"

#: The count line ``check`` prints under a single finding.
SUMMARY_ONE = (
    "1 silent suppression(s). A code names the check; the reason names the argument."
)


def module(tmp_path: Path, source: str) -> Path:
    """Put one module in a throwaway tree and answer with its path."""
    path = tmp_path / "subject.py"
    path.write_text(source, encoding="utf-8")
    return path


def finding(path: Path, line: int, named: str) -> str:
    """The one line the gate prints for the silent suppression at ``line``."""
    return f"{path}:{line}: {named} {SILENT_TAIL}"


# --- behavior 1: a ruff suppression states a reason --------------------------


def test_a_silent_noqa_is_named_by_line_and_code(tmp_path: Path) -> None:
    path = module(tmp_path, SILENT_NOQA)
    assert GATE.faults(path) == [finding(path, 1, NOQA_S603)]


def test_a_stated_reason_clears_its_line_and_leaves_the_next_one_named(
    tmp_path: Path,
) -> None:
    path = module(tmp_path, STATED_THEN_SILENT)
    assert GATE.faults(path) == [finding(path, 2, NOQA_S607)]


def test_a_suppression_naming_two_codes_is_one_finding_naming_both(
    tmp_path: Path,
) -> None:
    path = module(tmp_path, TWO_CODES)
    assert GATE.faults(path) == [finding(path, 1, NOQA_BOTH)]


def test_a_colon_after_the_codes_is_not_a_stated_reason(tmp_path: Path) -> None:
    path = module(tmp_path, COLON_INSTEAD)
    assert GATE.faults(path) == [finding(path, 1, NOQA_S603)]


# --- behavior 2: a mypy suppression states a reason --------------------------


def test_a_silent_type_ignore_is_named_by_line_and_code(tmp_path: Path) -> None:
    path = module(tmp_path, SILENT_IGNORE)
    assert GATE.faults(path) == [finding(path, 1, IGNORE_ARG)]


def test_a_stated_type_ignore_clears_its_line_and_leaves_the_next_one_named(
    tmp_path: Path,
) -> None:
    path = module(tmp_path, STATED_IGNORE_THEN_SILENT)
    assert GATE.faults(path) == [finding(path, 2, IGNORE_ARG)]


# --- behavior 3: only comments are read -------------------------------------


def test_a_suppression_spelled_inside_a_string_is_data(tmp_path: Path) -> None:
    path = module(tmp_path, STRING_THEN_SILENT)
    assert GATE.faults(path) == [finding(path, 2, NOQA_S607)]


def test_a_comment_suppressing_nothing_is_left_alone(tmp_path: Path) -> None:
    path = module(tmp_path, PLAIN_THEN_SILENT)
    assert GATE.faults(path) == [finding(path, 2, NOQA_S603)]


# --- behavior 4: the verdict a caller reads ----------------------------------


def test_check_prints_the_finding_with_its_count_and_refuses(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = module(tmp_path, SILENT_NOQA)
    status = GATE.check([path])
    assert (status, capsys.readouterr().out) == (
        1,
        f"{finding(path, 1, NOQA_S603)}\n\n{SUMMARY_ONE}\n",
    )


def test_main_checks_the_file_named_on_argv(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    path = module(tmp_path, SILENT_IGNORE)
    monkeypatch.setattr("sys.argv", ["check_noqa_reasons.py", str(path)])
    status = GATE.main()
    assert (status, capsys.readouterr().out) == (
        1,
        f"{finding(path, 1, IGNORE_ARG)}\n\n{SUMMARY_ONE}\n",
    )


STATED_NOQA = "value = call()  # noqa: S603 — argv is this module's own literals\n"

STATED_IGNORE = (
    "value = call()  # type: ignore[arg-type]  # — the keys are checked above\n"
)

#: What ``check`` prints when every suppression it read states a reason.
TWO_CLEAN_FILES = "[ok] 2 file(s) state a reason at every suppression\n"


def test_check_counts_the_files_it_read_when_every_suppression_states_a_reason(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    first = module(tmp_path, STATED_NOQA)
    second = tmp_path / "other.py"
    second.write_text(STATED_IGNORE, encoding="utf-8")
    assert (GATE.check([first, second]), capsys.readouterr().out) == (
        0,
        TWO_CLEAN_FILES,
    )
