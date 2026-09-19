"""The commit-message gate: the change and its reason, never the road there.

Each labelled class in ``PATTERNS`` gets a message that trips it, and the label
asserted is the one the gate's own table carries rather than a sentence copied
out of it. The rest is what the gate does not read: git's ``#`` comments, the
trailing block of ``Key: value`` trailers, and a line carrying the pragma with a
reason. A pragma with no reason is a complaint of its own.
"""

import io
import sys
from pathlib import Path

import check_commit_msg as GATE
import pytest

CLEAN = "fix(core): bound the git call\n\nAn unbounded call wedges the commit with its output captured.\n"

DATED = "fix(core): bound the git call\n\nThe call was bounded on 2026-07-04.\n"

ITERATION = "fix(core): bound the git call\n\nThe first attempt raised instead of returning.\n"

DISCOVERY = "fix(core): bound the git call\n\nIt turned out the call never answers.\n"

PROCESS = "fix(core): bound the git call\n\nThe reviewer flagged the unbounded call.\n"

TALLY = "fix(core): bound the git call\n\nThis is the fourth such call in the history of the module.\n"

#: One message per entry of the gate's table, in the table's order.
NARRATING = (DATED, ITERATION, DISCOVERY, PROCESS, TALLY)

EXEMPTED = "fix(core): bound the git call\n\nThe first attempt is named here. history-ok: the bug needs its tense\n"

BARE = "fix(core): bound the git call\n\nhistory-ok:\n"

COMMENTED = "fix(core): bound the git call\n\n# It turned out the call never answers.\n"

TRAILERED = "fix(core): bound the git call\n\nSee: it turned out the call never answers\n"

TRAILING_BLANKS = "fix(core): bound the git call\n\nThe call is bounded now.\n\n\n"


# --- behavior 1: a message that states the change and the reason passes ------


@pytest.mark.parametrize("message", [CLEAN, COMMENTED, TRAILERED, EXEMPTED])
def test_a_message_the_gate_has_nothing_to_say_about_is_clean(message: str) -> None:
    assert GATE.check_message(message) == []


# --- behavior 2: each labelled class of narration is refused by its own label ---


@pytest.mark.parametrize("index", range(len(GATE.PATTERNS)))
def test_every_class_of_narration_is_refused_under_its_label(index: int) -> None:
    assert GATE.PATTERNS[index][1] in GATE.check_message(NARRATING[index])[0]


def test_the_complaint_names_the_line_the_narration_sits_on() -> None:
    assert GATE.check_message(PROCESS)[0].startswith("line 3:")


# --- behavior 3: the pragma takes a reason, and nothing less -----------------


def test_a_pragma_with_no_reason_is_a_complaint_of_its_own() -> None:
    assert GATE.PRAGMA in GATE.check_message(BARE)[0]


def test_a_pragma_with_no_reason_is_the_only_complaint_on_its_line() -> None:
    assert len(GATE.check_message(BARE)) == 1


# --- behavior 4: what the gate reads, and what it leaves alone ---------------


@pytest.mark.parametrize(
    ("message", "lines"),
    [
        (CLEAN, 3),
        (COMMENTED, 1),
        (TRAILERED, 2),
        (TRAILING_BLANKS, 3),
    ],
)
def test_the_scanned_lines_drop_comments_trailers_and_the_trailing_blanks(message: str, lines: int) -> None:
    assert len(GATE.scanned_lines(message)) == lines


# --- behavior 5: the message comes from a file, or from stdin under `-` ------


def test_main_reads_the_message_file_argv_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "COMMIT_EDITMSG"
    path.write_text(DISCOVERY, encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["check_commit_msg.py", str(path)])
    assert GATE.main() == 1


def test_main_reads_stdin_under_a_dash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["check_commit_msg.py", "-"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(CLEAN))
    assert GATE.main() == 0
