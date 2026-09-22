"""The shape gate over the suite: one assertion per test, of a shape a test may take.

``check_file`` returns one ``(category, location, count)`` finding per defect, and
every case here asserts the whole tuple: the category is the gate's verdict, the
location is the line it reached that verdict on, and the count is what a ``count``
finding owes. The written path is folded to ``FILE`` so an expected finding is a
constant; the CLI cases read the printed sentence through ``capsys``.

Every case writes a suite file under ``tmp_path`` and hands the gate that path,
so a source under test is a string here and a module to the gate. The
``private`` scan skips a path with a ``support`` component, which is why one case
writes its file there instead.
"""

from pathlib import Path
from textwrap import dedent

import check_test_assertions as GATE
import pytest

#: What the written path reads as in an expected finding or sentence.
FILE = "FILE"

Expectation = list[tuple[str, str, int]]

ONE_ASSERTION = """
def test_one() -> None:
    assert 1 == 1
"""

NO_ASSERTION = """
def test_none() -> None:
    pass
"""
NO_ASSERTION_FINDINGS: Expectation = [("count", "FILE:2 test_none", 0)]

TWO_ASSERTIONS = """
def test_two() -> None:
    assert 1 == 1
    assert 2 == 2
"""
TWO_ASSERTIONS_FINDINGS: Expectation = [("count", "FILE:2 test_two", 2)]
TWO_ASSERTIONS_SENTENCE = "FILE:2 test_two: 2 assertions (want 1)\n"

A_CONJUNCTION = """
def test_both() -> None:
    assert 1 == 1 and 2 == 2
"""
A_CONJUNCTION_FINDINGS: Expectation = [("count", "FILE:2 test_both", 2)]

A_NEGATED_CONJUNCTION = """
def test_neither() -> None:
    assert not (1 == 2 and 2 == 3)
"""
A_NEGATED_CONJUNCTION_FINDINGS: Expectation = [("count", "FILE:2 test_neither", 2)]

A_RAISES_CONTEXT = """
import pytest

def test_raising() -> None:
    with pytest.raises(ValueError):
        int("x")
"""

A_PLAIN_CONTEXT = """
def test_held() -> None:
    with held() as body:
        assert body
"""

A_RAISES_BESIDE_A_PLAIN_CONTEXT = """
import pytest

def test_refusal() -> None:
    with held(), pytest.raises(ValueError):
        fail()
"""

AN_ASSERT_IN_A_LOOP = """
def test_each() -> None:
    for n in (1, 2):
        assert n
"""
AN_ASSERT_IN_A_LOOP_FINDINGS: Expectation = [("loop", "FILE:2 test_each", 0)]
AN_ASSERT_IN_A_LOOP_SENTENCE = "FILE:2 test_each: loop\n"

AN_ASSERT_IN_A_WHILE = """
def test_until() -> None:
    while True:
        assert 1
        break
"""
AN_ASSERT_IN_A_WHILE_FINDINGS: Expectation = [("loop", "FILE:2 test_until", 0)]

A_SWEEP_OVER_A_GENERATOR = """
def test_all_of_them() -> None:
    assert all(n for n in (1, 2))
"""
A_SWEEP_OVER_A_GENERATOR_FINDINGS: Expectation = [
    ("loop", "FILE:2 test_all_of_them", 0)
]

A_SWEEP_UNDER_A_NOT = """
def test_none_of_them() -> None:
    assert not any(n for n in (1, 2))
"""
A_SWEEP_UNDER_A_NOT_FINDINGS: Expectation = [("loop", "FILE:2 test_none_of_them", 0)]

AN_ASSERT_IN_A_HELPER = """
def helper() -> None:
    assert 1 == 1
"""
AN_ASSERT_IN_A_HELPER_FINDINGS: Expectation = [("outside", "FILE:3 helper", 0)]

AN_ASSERT_IN_A_FIXTURE = """
def fixture_body() -> None:
    assert 2 == 2
"""
AN_ASSERT_IN_A_FIXTURE_FINDINGS: Expectation = [("outside", "FILE:3 fixture_body", 0)]

NOT_NONE = """
def test_present() -> None:
    assert answer() is not None
"""
NOT_NONE_FINDINGS: Expectation = [("existence", "FILE:2 test_present", 0)]

LENGTH_OVER_ZERO = """
def test_filled() -> None:
    assert len(answer()) > 0
"""
LENGTH_OVER_ZERO_FINDINGS: Expectation = [("existence", "FILE:2 test_filled", 0)]

BARE_LENGTH = """
def test_any_at_all() -> None:
    assert len(answer())
"""
BARE_LENGTH_FINDINGS: Expectation = [("existence", "FILE:2 test_any_at_all", 0)]

A_DUNDER_REACH = """
def test_protocol() -> None:
    assert value.__class__ == int
"""

A_PRIVATE_REACH = """
def test_inside() -> None:
    assert value._hidden == 1
"""
A_PRIVATE_REACH_FINDINGS: Expectation = [("private", "FILE:3 test_inside", 0)]

A_PRIVATE_REACH_ON_SELF = """
class TestHolder:
    def test_inside(self) -> None:
        assert self._hidden == 1
"""

A_PRIVATE_REACH_ON_CLS = """
class TestHolder:
    def test_inside(cls) -> None:
        assert cls._hidden == 1
"""

A_NESTED_DEF = """
def test_outer() -> None:
    def inner() -> None:
        assert 1 == 2
    assert 1 == 1
"""

A_SKIPPED_TEST = """
import pytest

@pytest.mark.skip(reason="held")
def test_held() -> None:
    assert 1 == 1
"""
A_SKIPPED_TEST_FINDINGS: Expectation = [("skip", "FILE:5 test_held", 0)]

A_SKIPPED_TEST_BY_BARE_MARK = """
from pytest import mark

@mark.xfail
def test_expected_red() -> None:
    assert 1 == 1
"""
A_SKIPPED_TEST_BY_BARE_MARK_FINDINGS: Expectation = [
    ("skip", "FILE:5 test_expected_red", 0)
]

A_CONDITIONALLY_SKIPPED_TEST = """
import pytest

@pytest.mark.skipif(True, reason="held")
def test_maybe() -> None:
    assert 1 == 1
"""
A_CONDITIONALLY_SKIPPED_TEST_FINDINGS: Expectation = [("skip", "FILE:5 test_maybe", 0)]

A_PARAMETRIZED_TEST = """
import pytest

@pytest.mark.parametrize("n", [1, 2])
def test_swept(n: int) -> None:
    assert n
"""

A_SKIPPED_TEST_WITH_NO_ASSERTION = """
import pytest

@pytest.mark.skip(reason="held")
def test_held() -> None:
    pass
"""
A_SKIPPED_TEST_WITH_NO_ASSERTION_FINDINGS: Expectation = [
    ("count", "FILE:5 test_held", 0)
]

AN_EXISTENCE_ASSERT_AND_A_SKIP = """
import pytest

@pytest.mark.skip(reason="held")
def test_held() -> None:
    assert answer() is not None
"""

A_HELPER_ABOVE_A_COUNTLESS_TEST = """
def helper() -> None:
    assert 1 == 1

def test_later() -> None:
    pass
"""
A_HELPER_ABOVE_A_COUNTLESS_TEST_FINDINGS: Expectation = [
    ("outside", "FILE:3 helper", 0),
    ("count", "FILE:5 test_later", 0),
]


def written(tmp_path: Path, source: str, name: str = "test_sample.py") -> Path:
    """The suite file a case hands the gate."""
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(source), encoding="utf-8")
    return path


def folded(findings: list[GATE.Finding], path: Path) -> Expectation:
    """Every finding with the written path folded to ``FILE``."""
    return [
        (category, where.replace(str(path), FILE), count)
        for category, where, count in findings
    ]


def verdict(tmp_path: Path, source: str, name: str = "test_sample.py") -> Expectation:
    """Every finding the gate returns for a source, path folded."""
    path = written(tmp_path, source, name)
    return folded(GATE.check_file(path), path)


# --- behavior 1: one assertion of a plain shape is what a test may hold -------


@pytest.mark.parametrize(
    "source",
    [
        ONE_ASSERTION,
        A_RAISES_CONTEXT,
        A_RAISES_BESIDE_A_PLAIN_CONTEXT,
        A_PLAIN_CONTEXT,
        A_NESTED_DEF,
        A_DUNDER_REACH,
        A_PARAMETRIZED_TEST,
        A_PRIVATE_REACH_ON_SELF,
    ],
)
def test_a_test_holding_one_assertion_of_a_legal_shape_is_no_finding(
    tmp_path: Path, source: str
) -> None:
    assert verdict(tmp_path, source) == []


def test_a_private_attribute_on_cls_is_the_test_reaching_its_own_state(
    tmp_path: Path,
) -> None:
    assert verdict(tmp_path, A_PRIVATE_REACH_ON_CLS) == []


# --- behavior 2: an assertion count other than one is reported with the count --


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (NO_ASSERTION, NO_ASSERTION_FINDINGS),
        (TWO_ASSERTIONS, TWO_ASSERTIONS_FINDINGS),
        (A_CONJUNCTION, A_CONJUNCTION_FINDINGS),
        (A_NEGATED_CONJUNCTION, A_NEGATED_CONJUNCTION_FINDINGS),
    ],
)
def test_a_test_not_holding_exactly_one_assertion_is_named_with_its_count(
    tmp_path: Path, source: str, expected: Expectation
) -> None:
    assert verdict(tmp_path, source) == expected


# --- behavior 3: a sweep inside one assertion is a case sweep, not one case ---


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (AN_ASSERT_IN_A_LOOP, AN_ASSERT_IN_A_LOOP_FINDINGS),
        (AN_ASSERT_IN_A_WHILE, AN_ASSERT_IN_A_WHILE_FINDINGS),
        (A_SWEEP_OVER_A_GENERATOR, A_SWEEP_OVER_A_GENERATOR_FINDINGS),
        (A_SWEEP_UNDER_A_NOT, A_SWEEP_UNDER_A_NOT_FINDINGS),
    ],
)
def test_an_assertion_swept_over_cases_is_named_as_a_loop(
    tmp_path: Path, source: str, expected: Expectation
) -> None:
    assert verdict(tmp_path, source) == expected


# --- behavior 4: an assert outside a test is a helper deciding, not reporting --


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (AN_ASSERT_IN_A_HELPER, AN_ASSERT_IN_A_HELPER_FINDINGS),
        (AN_ASSERT_IN_A_FIXTURE, AN_ASSERT_IN_A_FIXTURE_FINDINGS),
    ],
)
def test_an_assert_in_a_function_that_is_not_a_test_is_named_as_outside(
    tmp_path: Path, source: str, expected: Expectation
) -> None:
    assert verdict(tmp_path, source) == expected


# --- behavior 5: presence pinned where a value was owed ----------------------


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (NOT_NONE, NOT_NONE_FINDINGS),
        (LENGTH_OVER_ZERO, LENGTH_OVER_ZERO_FINDINGS),
        (BARE_LENGTH, BARE_LENGTH_FINDINGS),
    ],
)
def test_an_assertion_pinning_mere_presence_is_named_as_existence(
    tmp_path: Path, source: str, expected: Expectation
) -> None:
    assert verdict(tmp_path, source) == expected


# --- behavior 6: a skip is a decision, so it is reported ---------------------


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (A_SKIPPED_TEST, A_SKIPPED_TEST_FINDINGS),
        (A_SKIPPED_TEST_BY_BARE_MARK, A_SKIPPED_TEST_BY_BARE_MARK_FINDINGS),
        (A_CONDITIONALLY_SKIPPED_TEST, A_CONDITIONALLY_SKIPPED_TEST_FINDINGS),
    ],
)
def test_a_skip_marker_is_named_whatever_its_spelling(
    tmp_path: Path, source: str, expected: Expectation
) -> None:
    assert verdict(tmp_path, source) == expected


# --- behavior 7: a private reach is the test knowing too much -----------------


def test_a_single_underscore_attribute_on_anything_but_self_is_named_at_its_line(
    tmp_path: Path,
) -> None:
    assert verdict(tmp_path, A_PRIVATE_REACH) == A_PRIVATE_REACH_FINDINGS


def test_a_fake_under_support_may_reach_into_its_own_state(tmp_path: Path) -> None:
    assert verdict(tmp_path, A_PRIVATE_REACH, "support/fake_holder.py") == []


# --- behavior 8: an exemption covers a skip or an existence, and nothing else --


def test_an_exempt_key_silences_the_skip_it_names(tmp_path: Path) -> None:
    path = written(tmp_path, A_SKIPPED_TEST)
    assert GATE.check_file(path, {f"{path}::test_held": "the owner said so"}) == []


def test_an_exempt_key_silences_the_existence_assertion_it_names(
    tmp_path: Path,
) -> None:
    path = written(tmp_path, AN_EXISTENCE_ASSERT_AND_A_SKIP)
    assert GATE.check_file(path, {f"{path}::test_held": "the owner said so"}) == []


def test_a_count_finding_outlives_the_exemption_on_its_test(tmp_path: Path) -> None:
    path = written(tmp_path, A_SKIPPED_TEST_WITH_NO_ASSERTION)
    exempt = {f"{path}::test_held": "the owner said so"}
    assert (
        folded(GATE.check_file(path, exempt), path)
        == A_SKIPPED_TEST_WITH_NO_ASSERTION_FINDINGS
    )


def test_the_module_table_is_what_an_unasked_check_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = written(tmp_path, A_SKIPPED_TEST)
    monkeypatch.setitem(GATE.EXEMPT, f"{path}::test_held", "the owner said so")
    assert GATE.check_file(path) == []


# --- behavior 9: findings come back in the order the file reads --------------


def test_findings_arrive_in_line_order(tmp_path: Path) -> None:
    assert (
        verdict(tmp_path, A_HELPER_ABOVE_A_COUNTLESS_TEST)
        == A_HELPER_ABOVE_A_COUNTLESS_TEST_FINDINGS
    )


# --- behavior 10: the CLI prints the finding, and fails unless it is sizing ----


def test_a_finding_fails_the_run_and_prints_its_sentence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = written(tmp_path, TWO_ASSERTIONS)
    monkeypatch.setattr("sys.argv", ["check_test_assertions.py", str(path)])
    code = GATE.main()
    assert (code, capsys.readouterr().out.replace(str(path), FILE)) == (
        1,
        TWO_ASSERTIONS_SENTENCE,
    )


def test_a_sizing_run_prints_the_same_sentence_and_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = written(tmp_path, TWO_ASSERTIONS)
    monkeypatch.setattr("sys.argv", ["check_test_assertions.py", "--report", str(path)])
    code = GATE.main()
    assert (code, capsys.readouterr().out.replace(str(path), FILE)) == (
        0,
        TWO_ASSERTIONS_SENTENCE,
    )


def test_a_clean_file_passes_the_cli_saying_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = written(tmp_path, ONE_ASSERTION)
    monkeypatch.setattr("sys.argv", ["check_test_assertions.py", str(path)])
    code = GATE.main()
    assert (code, capsys.readouterr().out) == (0, "")


def test_a_finding_that_carries_no_count_prints_its_category_and_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = written(tmp_path, AN_ASSERT_IN_A_LOOP)
    monkeypatch.setattr("sys.argv", ["check_test_assertions.py", str(path)])
    code = GATE.main()
    assert (code, capsys.readouterr().out.replace(str(path), FILE)) == (
        1,
        AN_ASSERT_IN_A_LOOP_SENTENCE,
    )
