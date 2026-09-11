"""The engine both gates run on: diff reading, the clean-line cache, the root, the verdict.

``triviajudge.core`` is the half of the old markdown gate that has nothing to
do with markdown. Four seams are exercised here.

``added_lines(diff)`` turns a zero-context unified diff into the lines it adds,
carrying the path and the new-file line number. Its numbering is the part that
breaks silently: a hunk header resets it, a removed line does not advance it,
and an unchanged line does.

``digest``, ``clean_cache`` and ``remember_clean`` are the cache. A digest is
taken over the line's stripped text alone, so a line the judge passed stays
passed after it moves. A cache that is absent, unreadable or holding something
other than a list reads as empty rather than raising, because a gate that
cannot read its cache should judge, not fail.

``Gate`` carries an optional cache, and ``judged`` writes one only under
``--stop`` and only when the field is set, which is what lets a gate that does
not judge at ``Stop`` carry none at all.

``root()`` answers with the work tree the current directory sits in, and raises
``NotARepository`` outside one rather than inferring a tree.
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

from triviajudge import core

EMPTY_DIFF = ""

ONE_ADDED_LINE = (
    "diff --git a/doc.md b/doc.md\n"
    "--- a/doc.md\n"
    "+++ b/doc.md\n"
    "@@ -0,0 +1 @@\n"
    "+the resampler runs at the rate the panel asks for\n"
)

TWO_FILES_TWO_HUNKS = (
    "diff --git a/one.md b/one.md\n"
    "--- a/one.md\n"
    "+++ b/one.md\n"
    "@@ -0,0 +4 @@\n"
    "+first added line\n"
    "+second added line\n"
    "diff --git a/two.md b/two.md\n"
    "--- a/two.md\n"
    "+++ b/two.md\n"
    "@@ -0,0 +9 @@\n"
    "+third added line\n"
)

A_REMOVAL_BESIDE_AN_ADDITION = (
    "diff --git a/doc.md b/doc.md\n"
    "--- a/doc.md\n"
    "+++ b/doc.md\n"
    "@@ -3,2 +3,1 @@\n"
    "-the line that went away\n"
    "+the line that stands now\n"
)


def ids_of(diff: str) -> list[str]:
    """The ``path:line`` of every line the diff adds."""
    return [line.id for line in core.added_lines(diff)]


# --- behavior 1: a diff becomes the lines it adds, addressed by new-file number ---


@pytest.mark.parametrize(
    ("diff", "ids"),
    [
        (EMPTY_DIFF, []),
        (ONE_ADDED_LINE, ["doc.md:1"]),
        (TWO_FILES_TWO_HUNKS, ["one.md:4", "one.md:5", "two.md:9"]),
        (A_REMOVAL_BESIDE_AN_ADDITION, ["doc.md:3"]),
    ],
)
def test_the_added_lines_of_a_diff_carry_their_new_file_numbers(diff: str, ids: list[str]) -> None:
    assert ids_of(diff) == ids


# --- behavior 2: a digest follows the text, not the place ---------------------


def test_the_same_text_at_two_addresses_has_one_digest() -> None:
    here = core.Line("one.md", 4, "  the rate the panel asks for  ")
    moved = core.Line("other.md", 91, "the rate the panel asks for")
    assert core.digest(here) == core.digest(moved)


def test_different_text_has_a_different_digest() -> None:
    assert core.digest(core.Line("a.md", 1, "one")) != core.digest(core.Line("a.md", 1, "two"))


# --- behavior 3: an unreadable cache reads as empty, never as an error --------


@pytest.mark.parametrize(
    ("content", "seen"),
    [
        (None, []),
        ("not json at all", []),
        ('{"digests": []}', []),
        ('["abc", "def"]', ["abc", "def"]),
    ],
)
def test_the_clean_cache_reads_as_empty_unless_it_holds_a_list(
    tmp_path: Path, content: str | None, seen: list[str]
) -> None:
    cache = tmp_path / "clean.json"
    if content is not None:
        cache.write_text(content, encoding="utf-8")
    assert core.clean_cache(cache) == seen


# --- behavior 4: what the judge passed is remembered, what it flagged is not --


def test_only_the_lines_the_judge_passed_reach_the_cache(tmp_path: Path) -> None:
    cache = tmp_path / "nested" / "clean.json"
    passed = core.Line("doc.md", 1, "the rate the panel asks for")
    flagged = core.Line("doc.md", 2, "approved 2026-07-04")
    core.remember_clean([passed, flagged], [{"id": "doc.md:2", "reason": "dated event"}], cache)
    assert json.loads(cache.read_text(encoding="utf-8")) == [core.digest(passed)]


def test_the_cache_keeps_only_the_newest_entries(tmp_path: Path) -> None:
    cache = tmp_path / "clean.json"
    cache.write_text(json.dumps([f"old-{n}" for n in range(core.CACHE_CAP)]) + "\n", encoding="utf-8")
    core.remember_clean([core.Line("doc.md", 1, "a line the judge passed")], [], cache)
    assert len(json.loads(cache.read_text(encoding="utf-8"))) == core.CACHE_CAP


# --- behavior 5: a gate carries a cache only if it has one -------------------


def test_a_gate_declares_no_cache_by_default() -> None:
    gate = core.Gate("prompt", lambda _args: ([], []), "[ok] nothing added", judge_at_stop=False)
    assert gate.cache is None


# --- behavior 6: the root is the tree the cwd sits in, or a refusal ----------


def test_the_root_is_the_work_tree_the_directory_sits_in(tmp_path: Path) -> None:
    git = os.environ.get("GIT", "git")
    subprocess.run([git, "init", "-q", str(tmp_path / "repo")], check=True, capture_output=True)
    inside = tmp_path / "repo" / "deep" / "deeper"
    inside.mkdir(parents=True)
    core.root.cache_clear()
    cwd = Path.cwd()
    try:
        os.chdir(inside)
        assert core.root().resolve() == (tmp_path / "repo").resolve()
    finally:
        os.chdir(cwd)
        core.root.cache_clear()


def test_a_directory_in_no_work_tree_is_refused_rather_than_inferred(tmp_path: Path) -> None:
    outside = tmp_path / "bare"
    outside.mkdir()
    core.root.cache_clear()
    cwd = Path.cwd()
    try:
        os.chdir(outside)
        with pytest.raises(core.NotARepository):
            core.root()
    finally:
        os.chdir(cwd)
        core.root.cache_clear()
