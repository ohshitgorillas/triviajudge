"""The suppression gate: a code names the check, and the reason names the argument.

Both suppressions are read out of comment tokens, so the sources below are data to
the gate rather than suppressions of their own. Ruff holds each to naming codes;
this gate holds each to stating why the check is wrong at that line.
"""

from pathlib import Path

import check_noqa_reasons as GATE

SILENT_NOQA = "value = call()  # noqa: S603\n"

STATED_NOQA = "value = call()  # noqa: S603 — argv is this module's own literals\n"

TWO_CODES = "value = call()  # noqa: S603, S607\n"

COLON_INSTEAD = "value = call()  # noqa: S603: argv is our own\n"

SILENT_IGNORE = "value = call()  # type: ignore[arg-type]\n"

STATED_IGNORE = "value = call()  # type: ignore[arg-type]  # — the keys are checked above\n"

INSIDE_A_STRING = 'TEXT = "# noqa: S603"\n'

NOTHING_SUPPRESSED = "value = call()  # the value the caller asked for\n"


def module(tmp_path: Path, source: str) -> Path:
    """Put one module in a throwaway tree and answer with its path."""
    path = tmp_path / "subject.py"
    path.write_text(source, encoding="utf-8")
    return path


# --- behavior 1: a ruff suppression states a reason --------------------------


def test_a_noqa_saying_nothing_is_a_finding(tmp_path: Path) -> None:
    assert len(GATE.faults(module(tmp_path, SILENT_NOQA))) == 1


def test_a_noqa_stating_a_reason_passes(tmp_path: Path) -> None:
    assert GATE.faults(module(tmp_path, STATED_NOQA)) == []


def test_a_suppression_naming_two_codes_is_one_finding(tmp_path: Path) -> None:
    assert len(GATE.faults(module(tmp_path, TWO_CODES))) == 1


def test_a_colon_after_the_codes_reads_as_more_codes(tmp_path: Path) -> None:
    assert len(GATE.faults(module(tmp_path, COLON_INSTEAD))) == 1


# --- behavior 2: a mypy suppression states a reason --------------------------


def test_a_type_ignore_saying_nothing_is_a_finding(tmp_path: Path) -> None:
    assert len(GATE.faults(module(tmp_path, SILENT_IGNORE))) == 1


def test_a_type_ignore_stating_a_reason_passes(tmp_path: Path) -> None:
    assert GATE.faults(module(tmp_path, STATED_IGNORE)) == []


# --- behavior 3: only comments are read -------------------------------------


def test_a_suppression_spelled_inside_a_string_is_data(tmp_path: Path) -> None:
    assert GATE.faults(module(tmp_path, INSIDE_A_STRING)) == []


def test_a_comment_suppressing_nothing_is_left_alone(tmp_path: Path) -> None:
    assert GATE.faults(module(tmp_path, NOTHING_SUPPRESSED)) == []


def test_a_file_carrying_a_silent_suppression_fails_the_gate(tmp_path: Path) -> None:
    assert GATE.check([module(tmp_path, SILENT_NOQA)]) == 1
