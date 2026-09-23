"""The markdown screen: the deterministic refusals the markdown judge never sees.

``md_screen.screen`` takes ``Line`` records and answers the lines it keeps for
the judge beside the complaints it raised itself. A complaint opens with the
``path:line`` of the line it refuses, so that prefix is what is pinned here;
the wording after it is copy.

Each family is screened on one refused text that is not its source phrase and
one passed text sharing its words, so a screen matching any family word fails.

Every phrase fed to the screen lives in a string literal, never in a comment or
docstring of this file.
"""

import importlib
from typing import cast

import pytest

from triviajudge.core import Line

ORIGIN = "doc.md:1"


def screened(text: str) -> tuple[list[Line], list[str]]:
    """``md_screen.screen`` over one line of ``doc.md``, imported at call time.

    The import sits here rather than at module level so a missing module fails
    each test on its own and leaves the collection of other files intact.
    """
    screen = importlib.import_module("triviajudge.md_screen").screen
    return cast("tuple[list[Line], list[str]]", screen([Line("doc.md", 1, text)]))


def complained_about(text: str) -> list[str]:
    """The ``path:line`` each complaint opens with, for one line of ``doc.md``."""
    _kept, complaints = screened(text)
    return [complaint[: len(ORIGIN)] for complaint in complaints]


def kept_numbers(text: str) -> list[int]:
    """The line numbers the screen keeps for the judge, for one line of ``doc.md``."""
    kept, _complaints = screened(text)
    return [line.number for line in kept]


REFUSED = [ORIGIN]
PASSED: list[str] = []

# --- behavior 1: each family refuses its own shape and passes its neighbors ---


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("The schema was reviewed on 2026-03-14 by the owner", REFUSED),
        ("| schema | reviewed | 2026-03-14 |", PASSED),
        ("The bypassed check reads 2026-03-14 rows", PASSED),
        ("The cache is re-checked on every run", PASSED),
        ("In round 2 the judge dropped the tabs", REFUSED),
        ("Every round reads the staged model", PASSED),
        ("The round-3 fix moved the cache", REFUSED),
        ("The round-trip test reads the cache", PASSED),
        ("Phase 2 moved the parser into core", REFUSED),
        ("Each phase reads the parser output", PASSED),
        ("The step-4 hand-back carried the new gate", REFUSED),
        ("The hand-back step carries the new gate", PASSED),
        ("Opal hand-back pass, both hosts green", REFUSED),
        ("The hand-back names the tests that must pass", PASSED),
        ("Keep ~~the old flag~~ out of the parser", REFUSED),
        ("The ~/.cache directory holds the staged model", PASSED),
        ("RESOLVED: the parser reads tabs", REFUSED),
        ("Conflicts are resolved: the newest entry wins", PASSED),
        ("Still open: the tab width in tables", REFUSED),
        ("The file is still open: the gate reads it twice", PASSED),
        ("Formerly named the lane gate", REFUSED),
        ("The previously staged model is documented here", PASSED),
        ("The claim made here earlier was wrong", REFUSED),
        ("Each claim made here is checked earlier by the gate", PASSED),
        ("The then-current parser read tabs", REFUSED),
        ("The current parser reads tabs, then spaces", PASSED),
        ("Tab handling works the same way", REFUSED),
        ("The same reader works on tabs and spaces", PASSED),
        ("Output is the same as before", REFUSED),
        ("The same header comes before each table", PASSED),
        ("The prompt is unchanged from the last release", REFUSED),
        ("An unchanged line is read from the cache", PASSED),
        ("The run completed with no flags", REFUSED),
        ("A completed run writes the cache", PASSED),
        ("All 9 hosts checked", REFUSED),
        ("All 9 hosts read the staged model", PASSED),
        ("The gate ran twice on the same file", REFUSED),
        ("The gate runs twice as fast on tabs", PASSED),
        ("The parser used to read tabs", REFUSED),
        ("Used to read tabs before the gate", REFUSED),
        ("The owner got used to the tabs", REFUSED),
        ("The flag can be used to skip the cache", PASSED),
        ("The flag is used to skip the cache", PASSED),
        ("This line is not trivia", REFUSED),
        ("The judge flags trivia, not rules", PASSED),
        ("Keep this line for the judge", REFUSED),
        ("Keep the line under this heading", PASSED),
        ("Written in present tense by design", REFUSED),
        ("The present tense is the design rule", PASSED),
    ],
    ids=[
        "dated event refused",
        "dated table row passed",
        "date as a noun passed",
        "re-checked passed",
        "round with a number refused",
        "round with no number passed",
        "hyphenated round refused",
        "round-trip passed",
        "phase with a number refused",
        "phase with no number passed",
        "numbered step hand-back refused",
        "hand-back step passed",
        "hand-back pass refused",
        "hand-back must pass passed",
        "strikethrough refused",
        "tilde path passed",
        "resolved opening refused",
        "resolved mid-line passed",
        "still open opening refused",
        "still open mid-line passed",
        "formerly named refused",
        "previously staged passed",
        "made here earlier refused",
        "made here checked earlier passed",
        "then-current refused",
        "current then passed",
        "works the same refused",
        "same reader works passed",
        "same as before refused",
        "same before passed",
        "unchanged from refused",
        "unchanged read from passed",
        "run completed refused",
        "completed run passed",
        "all hosts checked refused",
        "all hosts read passed",
        "ran twice refused",
        "runs twice passed",
        "used to mid-line refused",
        "used to opening refused",
        "got used to refused",
        "can be used to passed",
        "is used to passed",
        "not trivia refused",
        "trivia not rules passed",
        "keep this line refused",
        "keep the line passed",
        "present tense by design refused",
        "present tense design rule passed",
    ],
)
def test_each_family_refuses_its_shape_and_passes_a_line_sharing_its_words(
    text: str, expected: list[str]
) -> None:
    assert complained_about(text) == expected


# --- behavior 2: the history pragma exempts only with a reason after it -------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("The schema was reviewed on 2026-03-14 history-ok:", REFUSED),
        ("The schema was reviewed on 2026-03-14 history-ok: provenance row", PASSED),
    ],
    ids=["bare pragma refused", "pragma with a reason passed"],
)
def test_the_history_pragma_exempts_a_line_only_when_it_carries_a_reason(
    text: str, expected: list[str]
) -> None:
    assert complained_about(text) == expected


# --- behavior 3: quoted, indented and inline-code text is not screened --------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("> The parser used to read tabs", [1]),
        ("    The parser used to read tabs", [1]),
        ("\tThe parser used to read tabs", [1]),
        ("The `parser used to` flag reads tabs", [1]),
        ("The parser used to read tabs", []),
        ("   The parser used to read tabs", []),
    ],
    ids=[
        "blockquote kept",
        "four spaces kept",
        "tab kept",
        "inline code kept",
        "bare refused",
        "three spaces refused",
    ],
)
def test_a_phrase_inside_a_quote_an_indented_block_or_inline_code_reaches_the_judge(
    text: str, expected: list[int]
) -> None:
    assert kept_numbers(text) == expected
