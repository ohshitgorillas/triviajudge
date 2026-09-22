"""The citation gate: a citation names a heading that still exists, and never a position.

Every case writes its own little documentation set under ``tmp_path`` and indexes
it with ``doc_set``, so the headings a citation resolves against are the ones the
case wrote. The documents are named ``GUIDE.md`` and ``NOTES.md`` rather than
this repository's own filenames, which keeps a citation written here a fixture
rather than a citation of the tree the gate also reads.

A failing case asserts where the finding points: the citing file and the line
the case wrote the citation on, read off the ``<path>:<line>:`` address every
finding opens with, and the count of headings an ambiguous prefix matched, read
off the digits after it. The wording after the address is the gate's own and is
never asserted. A file under ``tmp_path`` is outside the repository, so the
gate addresses it by its absolute path.
"""

import re
from pathlib import Path
from textwrap import dedent

import check_doc_refs as GATE
import pytest

GUIDE = """
# setup and teardown

## the judged repository configures the gates

## the judged repository names its own file scope

### a `backtick` *heading* with case Folded
"""

NOTES = """
# how the sweep reads a tree
"""

A_PLAN_UNDER_DOCS = """
# the plan for the next cut
"""

#: every heading of ``GUIDE.md``, normalised, in document order
GUIDE_HEADINGS = [
    "setup and teardown",
    "the judged repository configures the gates",
    "the judged repository names its own file scope",
    "a backtick heading with case folded",
]

RESOLVING = '# (GUIDE.md "setup and teardown")\n'
RESOLVING_BY_PREFIX = '# (GUIDE.md "the judged repository configures")\n'
RESOLVING_THROUGH_DECORATION = '# (GUIDE.md "A `Backtick` Heading With Case Folded")\n'
RESOLVING_IN_A_SUBDIRECTORY = '# (plan.md "the plan for the next cut")\n'
RESOLVING_IN_A_SECOND_DOCUMENT = '# (NOTES.md "how the sweep reads a tree")\n'
AMBIGUOUS_PREFIX = '# (GUIDE.md "the judged repository")\n'
NO_SUCH_HEADING = '# (GUIDE.md "nothing of the sort")\n'
A_ROUND_CITATION = "# (GUIDE.md round 3)\n"
A_STEP_CITATION = "# (GUIDE.md step 12)\n"
A_ROUND_CITATION_WITH_WORDS_BETWEEN = "# (GUIDE.md sweep pass round 3)\n"
AN_UNKNOWN_DOCUMENT = '# (ELSEWHERE.md "a heading nobody indexes")\n'
A_STRING_LITERAL_NAMING_A_DOCUMENT = '(OUT / "GUIDE.md").write_text(body)\n'
EXEMPT_ON_THE_LINE = (
    '# (GUIDE.md "nothing of the sort")  # doc-ref-exempt: the fixture spells it out\n'
)
EXEMPT_ON_THE_LINE_ABOVE = (
    '# doc-ref-exempt: the fixture spells it out\n# (GUIDE.md "nothing of the sort")\n'
)
TWO_BROKEN_CITATIONS = (
    '# (GUIDE.md "nothing of the sort")\n# (GUIDE.md "or this either")\n'
)
#: a citation the gate would report, in bytes no text decoder accepts
UNDECODABLE_WITH_A_BROKEN_CITATION = b'\xff\xfe# (GUIDE.md "nothing of the sort")\n'

NO_SUCH_HEADING_FINDING = '{path}:1: GUIDE.md "nothing of the sort" — no such heading'
#: what ``main`` prints under the findings it listed
ONE_BROKEN_CITATION_TAIL = "\n\n1 broken doc citation(s)\n"
EMPTY_INDEX_REFUSAL = "check_doc_refs: no markdown found\n"
THE_GATE_SAYS_NOTHING = ""


@pytest.fixture
def docs(tmp_path: Path) -> dict[str, list[str]]:
    """The index over a documentation set the case writes itself."""
    (tmp_path / "GUIDE.md").write_text(dedent(GUIDE), encoding="utf-8")
    (tmp_path / "NOTES.md").write_text(dedent(NOTES), encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "plan.md").write_text(
        dedent(A_PLAN_UNDER_DOCS), encoding="utf-8"
    )
    return GATE.doc_set(tmp_path)


def citing(tmp_path: Path, body: str) -> Path:
    """Write ``body`` to the file whose citations a case is about, and name it."""
    path = tmp_path / "citing.py"
    path.write_text(body, encoding="utf-8")
    return path


def located(findings: list[str], path: Path) -> list[int]:
    """The line of ``path`` each finding is reported against, in the order the gate listed them.

    A finding addresses the citing file as ``<path>:<line>:``; anything after
    that is the gate's own wording and stays unread. A finding that does not
    open with ``path`` raises, since no line can be read off it.
    """
    lines = []
    for finding in findings:
        if not finding.startswith(f"{path}:"):
            raise ValueError(f"finding is not against {path}: {finding!r}")
        lines.append(int(finding.removeprefix(f"{path}:").split(":", 1)[0]))
    return lines


def counted(findings: list[str], path: Path) -> list[list[int]]:
    """Every integer each finding carries after its ``<path>:<line>:`` address, per finding."""
    counts = []
    for finding in findings:
        if not finding.startswith(f"{path}:"):
            raise ValueError(f"finding is not against {path}: {finding!r}")
        tail = finding.removeprefix(f"{path}:").split(":", 1)[1]
        counts.append([int(digits) for digits in re.findall(r"\d+", tail)])
    return counts


# --- behavior 1: a citation that names a heading resolves ---------------------


@pytest.mark.parametrize(
    "body",
    [
        RESOLVING,
        RESOLVING_BY_PREFIX,
        RESOLVING_THROUGH_DECORATION,
        RESOLVING_IN_A_SUBDIRECTORY,
        RESOLVING_IN_A_SECOND_DOCUMENT,
    ],
)
def test_a_citation_naming_a_heading_that_exists_resolves(
    tmp_path: Path, docs: dict[str, list[str]], body: str
) -> None:
    assert GATE.check(citing(tmp_path, body), docs) == []


def test_the_index_answers_to_the_stem_and_to_the_filename(
    docs: dict[str, list[str]],
) -> None:
    assert (docs["GUIDE"], docs["GUIDE.md"]) == (GUIDE_HEADINGS, GUIDE_HEADINGS)


# --- behavior 2: a citation that resolves to nothing, or to two things, fails --


def test_a_citation_matching_no_heading_names_the_heading_it_wanted(
    tmp_path: Path, docs: dict[str, list[str]]
) -> None:
    resolving = GATE.check(citing(tmp_path, RESOLVING), docs)
    path = citing(tmp_path, NO_SUCH_HEADING)
    assert (resolving, located(GATE.check(path, docs), path)) == ([], [1])


def test_a_prefix_matching_two_headings_says_how_many_it_matched(
    tmp_path: Path, docs: dict[str, list[str]]
) -> None:
    resolving = GATE.check(citing(tmp_path, RESOLVING_BY_PREFIX), docs)
    path = citing(tmp_path, AMBIGUOUS_PREFIX)
    ambiguous = GATE.check(path, docs)
    assert (resolving, located(ambiguous, path), counted(ambiguous, path)) == (
        [],
        [1],
        [[2]],
    )


def test_every_broken_citation_is_reported_against_its_own_line(
    tmp_path: Path, docs: dict[str, list[str]]
) -> None:
    path = citing(tmp_path, NO_SUCH_HEADING)
    one = located(GATE.check(path, docs), path)
    path = citing(tmp_path, TWO_BROKEN_CITATIONS)
    assert (one, located(GATE.check(path, docs), path)) == ([1], [1, 2])


# --- behavior 3: a positional citation is refused while it still resolves ------


@pytest.mark.parametrize(
    "body",
    [A_ROUND_CITATION, A_STEP_CITATION, A_ROUND_CITATION_WITH_WORDS_BETWEEN],
    ids=["round", "step", "round with words between"],
)
def test_a_citation_of_a_position_rather_than_a_heading_is_refused(
    tmp_path: Path, docs: dict[str, list[str]], body: str
) -> None:
    resolving = GATE.check(citing(tmp_path, RESOLVING), docs)
    path = citing(tmp_path, body)
    assert (resolving, located(GATE.check(path, docs), path)) == ([], [1])


# --- behavior 4: what the gate leaves alone -----------------------------------


@pytest.mark.parametrize(
    "body", [AN_UNKNOWN_DOCUMENT, A_STRING_LITERAL_NAMING_A_DOCUMENT]
)
def test_a_line_the_gate_has_no_business_with_is_left_alone(
    tmp_path: Path, docs: dict[str, list[str]], body: str
) -> None:
    assert GATE.check(citing(tmp_path, body), docs) == []


def test_a_broken_citation_in_a_file_that_is_not_text_is_skipped(
    tmp_path: Path, docs: dict[str, list[str]]
) -> None:
    binary = tmp_path / "held.py"
    binary.write_bytes(UNDECODABLE_WITH_A_BROKEN_CITATION)
    assert GATE.check(binary, docs) == []


# --- behavior 5: the pragma takes a reason, on the line or the one above -------


@pytest.mark.parametrize("body", [EXEMPT_ON_THE_LINE, EXEMPT_ON_THE_LINE_ABOVE])
def test_a_line_carrying_the_pragma_is_not_judged(
    tmp_path: Path, docs: dict[str, list[str]], body: str
) -> None:
    assert GATE.check(citing(tmp_path, body), docs) == []


# --- behavior 6: the CLI prints the finding, and refuses an empty index --------


def test_the_run_prints_the_broken_citation_and_its_count(
    tmp_path: Path,
    docs: dict[str, list[str]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = citing(tmp_path, NO_SUCH_HEADING)
    monkeypatch.setattr(GATE, "doc_set", lambda: docs)
    status = GATE.main([str(path)])
    assert (status, capsys.readouterr().err) == (
        1,
        NO_SUCH_HEADING_FINDING.format(path=path) + ONE_BROKEN_CITATION_TAIL,
    )


def test_a_resolving_citation_passes_the_run_without_a_word(
    tmp_path: Path,
    docs: dict[str, list[str]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = citing(tmp_path, RESOLVING)
    monkeypatch.setattr(GATE, "doc_set", lambda: docs)
    status = GATE.main([str(path)])
    assert (status, capsys.readouterr().err) == (0, THE_GATE_SAYS_NOTHING)


def test_an_index_holding_no_documents_is_a_refusal(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(GATE, "doc_set", dict)
    status = GATE.main([])
    assert (status, capsys.readouterr().err) == (1, EMPTY_INDEX_REFUSAL)


def test_a_path_that_is_no_file_is_not_read(
    tmp_path: Path,
    docs: dict[str, list[str]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(GATE, "doc_set", lambda: docs)
    status = GATE.main([str(tmp_path / "docs")])
    assert (status, capsys.readouterr().err) == (0, THE_GATE_SAYS_NOTHING)


def test_a_repo_relative_path_is_how_a_problem_is_addressed() -> None:
    inside = GATE.ROOT / "scripts" / "gates" / "repo" / "check_doc_refs.py"
    assert GATE.relabel(inside) == "scripts/gates/repo/check_doc_refs.py"
