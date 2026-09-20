"""The corpus gate: every record parses, and no text is filed under both verdicts.

A record is a citation, a tab and text. The pair comparison is over the text
alone, so the same sentence cited from two files is one claim about that sentence.
"""

from pathlib import Path

import check_corpus as GATE

A_RECORD = "docs/a.md:41\tThe corpus holds one verdict per text.\n"

ANOTHER_RECORD = "docs/b.md:7\tA record is a citation, a tab and text.\n"

SAME_TEXT_ELSEWHERE = "docs/c.md:9\tThe corpus holds one verdict per text.\n"

NO_TAB = "docs/a.md:41 The corpus holds one verdict per text.\n"

NO_LINE_NUMBER = "docs/a.md:middle\tThe corpus holds one verdict per text.\n"

NO_TEXT = "docs/a.md:41\t\n"

A_BLANK_LINE = "docs/a.md:41\tA record.\n\n"


def corpus(tmp_path: Path, trivia: str, clean: str) -> Path:
    """Put one labelled pair in a throwaway corpus directory, the changelog pair empty."""
    (tmp_path / "trivia.txt").write_text(trivia, encoding="utf-8")
    (tmp_path / "clean.txt").write_text(clean, encoding="utf-8")
    (tmp_path / "changelog-trivia.txt").write_text("", encoding="utf-8")
    (tmp_path / "changelog-clean.txt").write_text("", encoding="utf-8")
    return tmp_path


# --- behavior 1: every line parses as a record ------------------------------


def test_a_pair_that_parses_and_agrees_passes(tmp_path: Path) -> None:
    assert GATE.check(corpus(tmp_path, A_RECORD, ANOTHER_RECORD)) == 0


def test_a_line_carrying_no_tab_is_no_record(tmp_path: Path) -> None:
    assert GATE.check(corpus(tmp_path, NO_TAB, ANOTHER_RECORD)) == 1


def test_a_citation_naming_no_line_number_is_no_record(tmp_path: Path) -> None:
    assert GATE.check(corpus(tmp_path, NO_LINE_NUMBER, ANOTHER_RECORD)) == 1


def test_a_record_carrying_no_text_is_no_record(tmp_path: Path) -> None:
    assert GATE.check(corpus(tmp_path, NO_TEXT, ANOTHER_RECORD)) == 1


def test_a_blank_line_is_no_record(tmp_path: Path) -> None:
    assert GATE.check(corpus(tmp_path, A_BLANK_LINE, ANOTHER_RECORD)) == 1


# --- behavior 2: no text is filed under both labels -------------------------


def test_one_text_cited_from_two_files_is_a_contradiction(tmp_path: Path) -> None:
    assert GATE.check(corpus(tmp_path, A_RECORD, SAME_TEXT_ELSEWHERE)) == 1


def test_two_texts_that_differ_are_two_claims(tmp_path: Path) -> None:
    assert GATE.contradictions(corpus(tmp_path, A_RECORD, ANOTHER_RECORD), "trivia.txt", "clean.txt") == []


def test_this_repository_s_corpus_parses_and_holds_one_verdict_per_text() -> None:
    assert GATE.check(GATE.ROOT / GATE.CORPUS) == 0
