"""The corpus gate: every record parses, and no text is filed under both verdicts.

A record is a citation, a tab and text. The pair comparison is over the text
alone, so the same sentence cited from two files is one claim about that sentence.

Every case writes its own throwaway corpus under ``tmp_path`` and asserts the
verdict the gate reaches over it: which file and line failed to parse, or which
line of the trivia file repeats a text the clean file also files. The expected
sentences are seeded here as constants, with ``{path}`` and ``{directory}``
standing for the throwaway corpus a case writes, since the gate addresses a
directory outside the repository by its absolute path.
"""

import sys
from pathlib import Path

import check_corpus as GATE
import pytest

A_RECORD = "docs/a.md:41\tThe corpus holds one verdict per text.\n"

ANOTHER_RECORD = "docs/b.md:7\tA record is a citation, a tab and text.\n"

SAME_TEXT_ELSEWHERE = "docs/c.md:9\tThe corpus holds one verdict per text.\n"

NO_TAB = "docs/a.md:41 The corpus holds one verdict per text.\n"

NO_LINE_NUMBER = "docs/a.md:middle\tThe corpus holds one verdict per text.\n"

NO_TEXT = "docs/a.md:41\t\n"

A_RECORD_THEN_A_BLANK_LINE = "docs/a.md:41\tA record.\n\n"

#: what ``unparsed`` says of the line it could not read
NO_RECORD_FINDING = "{path}:{number}: no record — a line reads `path:line<TAB>text`"

#: what ``contradictions`` says of a text the trivia file and the clean file both file
CONTRADICTION_FINDING = "{path}:1: also clean.txt:1 — one text, two verdicts"

#: what ``check`` prints over a corpus that holds
OK_LINE = "[ok] {directory} parses whole, and every text holds one verdict\n"

#: what ``check`` prints under the one problem it listed
ONE_PROBLEM_TAIL = (
    "\n1 problem(s) in {directory}. A dropped record shrinks the corpus in silence,\n"
    "and a text under both labels scores the judge wrong whichever verdict it gives.\n"
)


def corpus(tmp_path: Path, trivia: str, clean: str) -> Path:
    """Put one labelled pair in a throwaway corpus directory, the changelog pair empty."""
    (tmp_path / "trivia.txt").write_text(trivia, encoding="utf-8")
    (tmp_path / "clean.txt").write_text(clean, encoding="utf-8")
    (tmp_path / "changelog-trivia.txt").write_text("", encoding="utf-8")
    (tmp_path / "changelog-clean.txt").write_text("", encoding="utf-8")
    return tmp_path


# --- behavior 1: every line parses as a record ------------------------------


@pytest.mark.parametrize(
    ("body", "number"),
    [
        (NO_TAB, 1),
        (NO_LINE_NUMBER, 1),
        (NO_TEXT, 1),
        (A_RECORD_THEN_A_BLANK_LINE, 2),
    ],
)
def test_a_line_that_is_no_record_is_reported_against_its_own_line(
    tmp_path: Path, body: str, number: int
) -> None:
    path = corpus(tmp_path, body, ANOTHER_RECORD) / "trivia.txt"
    assert GATE.unparsed(path) == [NO_RECORD_FINDING.format(path=path, number=number)]


def test_a_file_whose_every_line_is_a_record_is_reported_against_nothing(
    tmp_path: Path,
) -> None:
    assert (
        GATE.unparsed(corpus(tmp_path, A_RECORD, ANOTHER_RECORD) / "trivia.txt") == []
    )


# --- behavior 2: no text is filed under both labels -------------------------


def test_one_text_cited_from_two_files_names_both_sides(tmp_path: Path) -> None:
    directory = corpus(tmp_path, A_RECORD, SAME_TEXT_ELSEWHERE)
    assert GATE.contradictions(directory, "trivia.txt", "clean.txt") == [
        CONTRADICTION_FINDING.format(path=directory / "trivia.txt")
    ]


def test_two_texts_that_differ_are_two_claims(tmp_path: Path) -> None:
    assert (
        GATE.contradictions(
            corpus(tmp_path, A_RECORD, ANOTHER_RECORD), "trivia.txt", "clean.txt"
        )
        == []
    )


# --- behavior 3: the check prints its verdict, and refuses on a problem ------


def test_the_check_prints_the_unreadable_line_and_refuses(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = corpus(tmp_path, NO_TAB, ANOTHER_RECORD)
    status = GATE.check(directory)
    assert (status, capsys.readouterr().out) == (
        1,
        NO_RECORD_FINDING.format(path=directory / "trivia.txt", number=1)
        + "\n"
        + ONE_PROBLEM_TAIL.format(directory=directory),
    )


def test_the_check_prints_the_contradiction_and_refuses(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = corpus(tmp_path, A_RECORD, SAME_TEXT_ELSEWHERE)
    status = GATE.check(directory)
    assert (status, capsys.readouterr().out) == (
        1,
        CONTRADICTION_FINDING.format(path=directory / "trivia.txt")
        + "\n"
        + ONE_PROBLEM_TAIL.format(directory=directory),
    )


def test_a_pair_that_parses_and_agrees_passes_with_a_word_for_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = corpus(tmp_path, A_RECORD, ANOTHER_RECORD)
    status = GATE.check(directory)
    assert (status, capsys.readouterr().out) == (0, OK_LINE.format(directory=directory))


# --- behavior 4: the run reads the directory on argv, else this corpus -------


def test_the_run_checks_the_directory_named_on_argv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = corpus(tmp_path, A_RECORD, SAME_TEXT_ELSEWHERE)
    monkeypatch.setattr(sys, "argv", ["check_corpus.py", str(directory)])
    status = GATE.main()
    assert (status, capsys.readouterr().out) == (
        1,
        CONTRADICTION_FINDING.format(path=directory / "trivia.txt")
        + "\n"
        + ONE_PROBLEM_TAIL.format(directory=directory),
    )


def test_the_run_with_no_argument_holds_this_repository_s_corpus(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["check_corpus.py"])
    status = GATE.main()
    assert (status, capsys.readouterr().out) == (
        0,
        OK_LINE.format(directory=GATE.ROOT / GATE.CORPUS),
    )
