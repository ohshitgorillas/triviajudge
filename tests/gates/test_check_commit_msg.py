"""The commit-message gate: the change and its reason, never the road there.

Each labelled class in ``PATTERNS`` gets a message that trips it, and the case
asserts the line the finding names — the line the fixture wrote the narration
on — never the wording after it. The rest is what the gate does not read —
git's ``#`` comments, the trailing block of ``Key: value`` trailers, and a line
carrying the pragma with a reason — and a pragma with no reason, which is a
finding of its own and the only one on its line.
"""

import io
import re
import sys
from pathlib import Path

import check_commit_msg as GATE
import pytest


def line_of(finding: str) -> int:
    """The line number a finding names: the first integer in it."""
    found = re.search(r"\d+", finding)
    return int(found.group()) if found else -1


def lines_of(findings: list[str]) -> list[int]:
    """The line each finding names, in the order the gate listed them."""
    return [line_of(finding) for finding in findings]


CLEAN = "fix(core): bound the git call\n\nAn unbounded call wedges the commit with its output captured.\n"

DATED = "fix(core): bound the git call\n\nThe call was bounded on 2026-07-04.\n"

ITERATION = "fix(core): bound the git call\n\nThe first attempt raised instead of returning.\n"

DISCOVERY = "fix(core): bound the git call\n\nIt turned out the call never answers.\n"

PROCESS = "fix(core): bound the git call\n\nThe reviewer flagged the unbounded call.\n"

TALLY = "fix(core): bound the git call\n\nThis is the fourth such call in the history of the module.\n"

#: Narration in the subject as well as the body, to pin which line each finding names.
TWO_LINES = "fix(core): drop the earlier draft\n\nThe reviewer flagged the unbounded call.\n"

EXEMPTED = "fix(core): bound the git call\n\nThe first attempt is named here. history-ok: the bug needs its tense\n"

BARE = "fix(core): bound the git call\n\nThe first attempt is named here. history-ok:\n"

COMMENTED = "fix(core): bound the git call\n\n# It turned out the call never answers.\n"

TRAILERED = "fix(core): bound the git call\n\nSee: it turned out the call never answers\n"

TRAILERED_PAST_BLANKS = "fix(core): bound the git call\n\nSee: it turned out the call never answers\n\n\n"

#: A comment, a body line, a trailer and trailing blank lines in one message.
MIXED = (
    "fix(core): bound the git call\n\n# please enter the commit message\nThe call is bounded now.\nSee: a link\n\n\n"
)

#: What ``scanned_lines`` keeps of ``MIXED``: the comment, the trailer and the blanks are gone.
MIXED_SCANNED = [(1, "fix(core): bound the git call"), (2, ""), (3, "The call is bounded now.")]


# --- behavior 1: each labelled class of narration is named on its own line ---


@pytest.mark.parametrize(
    "message",
    [DATED, ITERATION, DISCOVERY, PROCESS, TALLY],
    ids=["dated", "iteration", "discovery", "process", "tally"],
)
def test_narration_is_named_with_its_class_line_and_matched_words(message: str) -> None:
    assert lines_of(GATE.check_message(message)) == [3]


def test_a_finding_per_narrating_line_in_the_order_the_lines_run() -> None:
    assert lines_of(GATE.check_message(TWO_LINES)) == [1, 3]


# --- behavior 2: a message that states the change and the reason passes ------


def test_a_message_that_states_the_change_and_the_reason_draws_nothing() -> None:
    assert GATE.check_message(CLEAN) == []


# --- behavior 3: the pragma takes a reason, and nothing less -----------------


def test_a_line_whose_pragma_carries_a_reason_is_left_alone() -> None:
    assert GATE.check_message(EXEMPTED) == []


def test_a_reasonless_pragma_is_the_one_finding_on_a_narrating_line() -> None:
    assert lines_of(GATE.check_message(BARE)) == [3]


# --- behavior 4: what the gate reads, and what it leaves alone ---------------


def test_narration_in_a_git_comment_line_is_not_read() -> None:
    assert GATE.check_message(COMMENTED) == []


def test_narration_inside_a_trailing_trailer_is_not_read() -> None:
    assert GATE.check_message(TRAILERED) == []


def test_a_trailer_is_still_a_trailer_behind_trailing_blank_lines() -> None:
    assert GATE.check_message(TRAILERED_PAST_BLANKS) == []


def test_the_scanned_lines_are_numbered_over_what_survives_the_drops() -> None:
    assert GATE.scanned_lines(MIXED) == MIXED_SCANNED


# --- behavior 5: the message comes from a file, or from stdin under `-` ------


def test_main_prints_the_finding_for_the_file_argv_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "COMMIT_EDITMSG"
    path.write_text(DISCOVERY, encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["check_commit_msg.py", str(path)])
    assert (GATE.main(), line_of(capsys.readouterr().out.splitlines()[0])) == (1, 3)


def test_main_reads_stdin_under_a_dash_and_says_nothing_of_a_clean_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["check_commit_msg.py", "-"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(CLEAN))
    assert (GATE.main(), capsys.readouterr().out) == (0, "")
