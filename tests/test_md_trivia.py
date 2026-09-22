"""The markdown gate: what counts as prose, and which lines each input mode hands the judge.

``prose_only`` is the screen that keeps a judge call cheap: a fenced block, a
heading, a table rule and a blank line carry no prose to rule on, and a file the
repository names in ``md_skip`` is not read at all. A fence toggles per file, so
two files fencing at once do not close each other's block.

``collect`` is the mode switch. ``--lines`` reads calibration records, ``--head``
reads what the last commit added, a file list reads what is staged, and a run
naming none of those has nothing to judge.

Every phrase a judge would rule on lives in a string literal, never in a comment
or docstring of this file.
"""

import argparse
from pathlib import Path

import pytest

from triviajudge import md_trivia
from triviajudge.core import Line, NotARepositoryError

FENCED = [
    Line("doc.md", 1, "the panel holds the staged rate"),
    Line("doc.md", 2, "```python"),
    Line("doc.md", 3, "value = 1"),
    Line("doc.md", 4, "```"),
    Line("doc.md", 5, "the lane returns the staged model"),
]

ONE_ADDED_LINE = "diff --git a/doc.md b/doc.md\n--- a/doc.md\n+++ b/doc.md\n@@ -0,0 +1 @@\n+the panel holds the staged rate\n"


def namespace(**overrides: object) -> argparse.Namespace:
    """The arguments a gate run carries, with every mode the flags leave alone switched off."""
    args: dict[str, object] = {"stop": False, "lines": None, "head": False, "files": []}
    return argparse.Namespace(**{**args, **overrides})


# --- behavior 1: only prose reaches the judge --------------------------------


def test_a_fenced_block_is_not_prose_and_the_text_after_it_is() -> None:
    assert [line.number for line in md_trivia.prose_only(FENCED)] == [1, 5]


@pytest.mark.parametrize(
    "line",
    [
        Line("doc.md", 1, ""),
        Line("doc.md", 1, "## a heading"),
        Line("doc.md", 1, "| --- | --- |"),
        Line("CHANGELOG.md", 1, "the panel holds the staged rate"),
    ],
)
def test_a_line_carrying_no_prose_is_not_judged(line: Line) -> None:
    assert md_trivia.prose_only([line]) == []


# --- behavior 2: each input mode reads the lines it names --------------------


def test_the_records_mode_judges_the_lines_the_file_addresses(tmp_path: Path) -> None:
    records = tmp_path / "lines.tsv"
    records.write_text("doc.md:12\tthe panel holds the staged rate\n", encoding="utf-8")
    lines, _complaints = md_trivia.collect(namespace(lines=str(records)))
    assert [line.id for line in lines] == ["doc.md:12"]


def test_the_head_mode_judges_what_the_last_commit_added(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("triviajudge.md_trivia.git_diff", lambda *_args: ONE_ADDED_LINE)
    lines, _complaints = md_trivia.collect(namespace(head=True))
    assert [line.id for line in lines] == ["doc.md:1"]


def test_the_commit_mode_judges_what_the_named_files_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("triviajudge.md_trivia.git_diff", lambda *_args: ONE_ADDED_LINE)
    lines, _complaints = md_trivia.collect(namespace(files=["doc.md"]))
    assert [line.id for line in lines] == ["doc.md:1"]


def test_a_run_naming_no_file_and_no_mode_judges_nothing() -> None:
    assert md_trivia.collect(namespace()) == ([], [])


# --- behavior 4: outside a work tree the gate refuses rather than passes -----


def test_a_directory_in_no_work_tree_is_refused(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def outside() -> None:
        raise NotARepositoryError("no git work tree")

    monkeypatch.setattr("triviajudge.md_trivia.settings", outside)
    monkeypatch.setattr("sys.argv", ["triviajudge-md"])
    assert (md_trivia.main(), "no git work tree" in capsys.readouterr().err) == (
        1,
        True,
    )
