"""The citation gate: a citation names a heading that still exists, and never a position.

Every case writes its own little documentation set under ``tmp_path`` and indexes
it with ``doc_set``, so the headings a citation resolves against are the ones the
case wrote. The documents are named ``GUIDE.md`` and ``NOTES.md`` rather than
this repository's own filenames, which keeps a citation written here a fixture
rather than a citation of the tree the gate also reads.

A problem line is counted, not quoted: the count is the verdict, the sentence is
the gate's wording.
"""

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
EXEMPT_ON_THE_LINE = '# (GUIDE.md "nothing of the sort")  # doc-ref-exempt: the fixture spells it out\n'
EXEMPT_ON_THE_LINE_ABOVE = '# doc-ref-exempt: the fixture spells it out\n# (GUIDE.md "nothing of the sort")\n'
TWO_BROKEN_CITATIONS = '# (GUIDE.md "nothing of the sort")\n# (GUIDE.md "or this either")\n'


@pytest.fixture
def docs(tmp_path: Path) -> dict[str, list[str]]:
    """The index over a documentation set the case writes itself."""
    (tmp_path / "GUIDE.md").write_text(dedent(GUIDE), encoding="utf-8")
    (tmp_path / "NOTES.md").write_text(dedent(NOTES), encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "plan.md").write_text(dedent(A_PLAN_UNDER_DOCS), encoding="utf-8")
    return GATE.doc_set(tmp_path)


def problems(tmp_path: Path, body: str, docs: dict[str, list[str]]) -> list[str]:
    """Every citation problem the gate finds in a file carrying ``body``."""
    citing = tmp_path / "citing.py"
    citing.write_text(body, encoding="utf-8")
    return GATE.check(citing, docs)


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
    assert problems(tmp_path, body, docs) == []


def test_the_index_answers_to_the_stem_and_to_the_filename(docs: dict[str, list[str]]) -> None:
    assert docs["GUIDE"] == docs["GUIDE.md"]


# --- behavior 2: a citation that resolves to nothing, or to two things, fails --


@pytest.mark.parametrize("body", [AMBIGUOUS_PREFIX, NO_SUCH_HEADING])
def test_a_citation_resolving_to_other_than_one_heading_is_a_problem(
    tmp_path: Path, docs: dict[str, list[str]], body: str
) -> None:
    assert len(problems(tmp_path, body, docs)) == 1


def test_every_broken_citation_on_its_own_line_is_reported(tmp_path: Path, docs: dict[str, list[str]]) -> None:
    assert len(problems(tmp_path, TWO_BROKEN_CITATIONS, docs)) == 2


# --- behavior 3: a positional citation is refused while it still resolves ------


@pytest.mark.parametrize("body", [A_ROUND_CITATION, A_STEP_CITATION, A_ROUND_CITATION_WITH_WORDS_BETWEEN])
def test_a_citation_of_a_position_rather_than_a_heading_is_refused(
    tmp_path: Path, docs: dict[str, list[str]], body: str
) -> None:
    assert len(problems(tmp_path, body, docs)) == 1


# --- behavior 4: what the gate leaves alone -----------------------------------


@pytest.mark.parametrize("body", [AN_UNKNOWN_DOCUMENT, A_STRING_LITERAL_NAMING_A_DOCUMENT])
def test_a_line_the_gate_has_no_business_with_is_left_alone(
    tmp_path: Path, docs: dict[str, list[str]], body: str
) -> None:
    assert problems(tmp_path, body, docs) == []


def test_a_file_that_cannot_be_read_as_text_is_skipped(tmp_path: Path, docs: dict[str, list[str]]) -> None:
    binary = tmp_path / "held.py"
    binary.write_bytes(b"\xff\xfe\x00 (GUIDE.md")
    assert GATE.check(binary, docs) == []


# --- behavior 5: the pragma takes a reason, on the line or the one above -------


@pytest.mark.parametrize("body", [EXEMPT_ON_THE_LINE, EXEMPT_ON_THE_LINE_ABOVE])
def test_a_line_carrying_the_pragma_is_not_judged(tmp_path: Path, docs: dict[str, list[str]], body: str) -> None:
    assert problems(tmp_path, body, docs) == []


# --- behavior 6: the CLI fails on a broken citation and on an empty index ------


def test_a_broken_citation_fails_the_run(
    tmp_path: Path, docs: dict[str, list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    citing = tmp_path / "citing.py"
    citing.write_text(NO_SUCH_HEADING, encoding="utf-8")
    monkeypatch.setattr(GATE, "doc_set", lambda: docs)
    assert GATE.main([str(citing)]) == 1


def test_a_resolving_citation_passes_the_run(
    tmp_path: Path, docs: dict[str, list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    citing = tmp_path / "citing.py"
    citing.write_text(RESOLVING, encoding="utf-8")
    monkeypatch.setattr(GATE, "doc_set", lambda: docs)
    assert GATE.main([str(citing)]) == 0


def test_an_index_holding_no_documents_is_a_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(GATE, "doc_set", dict)
    assert GATE.main([]) == 1


def test_a_path_that_is_no_file_is_not_read(
    tmp_path: Path, docs: dict[str, list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(GATE, "doc_set", lambda: docs)
    assert GATE.main([str(tmp_path / "docs")]) == 0


def test_a_repo_relative_path_is_how_a_problem_is_addressed() -> None:
    inside = GATE.ROOT / "scripts" / "gates" / "check_doc_refs.py"
    assert GATE.relabel(inside) == "scripts/gates/check_doc_refs.py"
