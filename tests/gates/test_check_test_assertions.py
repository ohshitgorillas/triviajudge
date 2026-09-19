"""The shape gate over the suite: one assertion per test, of a shape a test may take.

``check_file`` returns one ``(category, location, count)`` finding per defect,
and the category is what a test here reads: the printed sentence is the gate's
wording, the category is its verdict.

Every case writes a suite file under ``tmp_path`` and hands the gate that path,
so a source under test is a string here and a module to the gate. The
``private`` scan skips a path with a ``support`` component, which is why one case
writes its file there instead.
"""

from pathlib import Path
from textwrap import dedent

import check_test_assertions as GATE
import pytest

ONE_ASSERTION = """
def test_one() -> None:
    assert 1 == 1
"""

NO_ASSERTION = """
def test_none() -> None:
    pass
"""

TWO_ASSERTIONS = """
def test_two() -> None:
    assert 1 == 1
    assert 2 == 2
"""

A_CONJUNCTION = """
def test_both() -> None:
    assert 1 == 1 and 2 == 2
"""

A_NEGATED_CONJUNCTION = """
def test_neither() -> None:
    assert not (1 == 2 and 2 == 3)
"""

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

AN_ASSERT_IN_A_WHILE = """
def test_until() -> None:
    while True:
        assert 1
        break
"""

A_SWEEP_OVER_A_GENERATOR = """
def test_all_of_them() -> None:
    assert all(n for n in (1, 2))
"""

A_SWEEP_UNDER_A_NOT = """
def test_none_of_them() -> None:
    assert not any(n for n in (1, 2))
"""

AN_ASSERT_IN_A_HELPER = """
def helper() -> None:
    assert 1 == 1
"""

AN_ASSERT_IN_A_FIXTURE = """
def fixture_body() -> None:
    assert 2 == 2
"""

NOT_NONE = """
def test_present() -> None:
    assert answer() is not None
"""

LENGTH_OVER_ZERO = """
def test_filled() -> None:
    assert len(answer()) > 0
"""

BARE_LENGTH = """
def test_any_at_all() -> None:
    assert len(answer())
"""

A_DUNDER_REACH = """
def test_protocol() -> None:
    assert value.__class__ == int
"""

A_PRIVATE_REACH = """
def test_inside() -> None:
    assert value._hidden == 1
"""

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

A_SKIPPED_TEST_BY_BARE_MARK = """
from pytest import mark

@mark.xfail
def test_expected_red() -> None:
    assert 1 == 1
"""

A_CONDITIONALLY_SKIPPED_TEST = """
import pytest

@pytest.mark.skipif(True, reason="held")
def test_maybe() -> None:
    assert 1 == 1
"""

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


def written(tmp_path: Path, source: str, name: str = "test_sample.py") -> Path:
    """The suite file a case hands the gate."""
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(source), encoding="utf-8")
    return path


def categories(tmp_path: Path, source: str, name: str = "test_sample.py") -> list[str]:
    """The category of every finding the gate returns for a source."""
    return [category for category, _, _ in GATE.check_file(written(tmp_path, source, name))]


def counted(tmp_path: Path, source: str) -> list[tuple[str, int]]:
    """Every finding as (category, assertion count)."""
    return [(category, count) for category, _, count in GATE.check_file(written(tmp_path, source))]


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
def test_a_test_holding_one_assertion_of_a_legal_shape_is_no_finding(tmp_path: Path, source: str) -> None:
    assert categories(tmp_path, source) == []


def test_a_private_attribute_on_cls_is_the_test_reaching_its_own_state(tmp_path: Path) -> None:
    assert categories(tmp_path, A_PRIVATE_REACH_ON_CLS) == []


# --- behavior 2: an assertion count other than one is reported with the count --


@pytest.mark.parametrize(
    ("source", "count"),
    [
        (NO_ASSERTION, 0),
        (TWO_ASSERTIONS, 2),
        (A_CONJUNCTION, 2),
        (A_NEGATED_CONJUNCTION, 2),
    ],
)
def test_a_test_not_holding_exactly_one_assertion_carries_its_count(tmp_path: Path, source: str, count: int) -> None:
    assert counted(tmp_path, source) == [("count", count)]


# --- behavior 3: a sweep inside one assertion is a case sweep, not one case ---


@pytest.mark.parametrize(
    "source",
    [AN_ASSERT_IN_A_LOOP, AN_ASSERT_IN_A_WHILE, A_SWEEP_OVER_A_GENERATOR, A_SWEEP_UNDER_A_NOT],
)
def test_an_assertion_swept_over_cases_is_reported_as_a_loop(tmp_path: Path, source: str) -> None:
    assert categories(tmp_path, source) == ["loop"]


# --- behavior 4: an assert outside a test is a helper deciding, not reporting --


@pytest.mark.parametrize("source", [AN_ASSERT_IN_A_HELPER, AN_ASSERT_IN_A_FIXTURE])
def test_an_assert_in_a_function_that_is_not_a_test_is_reported_as_outside(tmp_path: Path, source: str) -> None:
    assert categories(tmp_path, source) == ["outside"]


# --- behavior 5: presence pinned where a value was owed ----------------------


@pytest.mark.parametrize("source", [NOT_NONE, LENGTH_OVER_ZERO, BARE_LENGTH])
def test_an_assertion_pinning_mere_presence_is_reported_as_existence(tmp_path: Path, source: str) -> None:
    assert categories(tmp_path, source) == ["existence"]


# --- behavior 6: a skip is a decision, so it is reported ---------------------


@pytest.mark.parametrize(
    "source",
    [A_SKIPPED_TEST, A_SKIPPED_TEST_BY_BARE_MARK, A_CONDITIONALLY_SKIPPED_TEST],
)
def test_a_skip_marker_is_reported_whatever_its_spelling(tmp_path: Path, source: str) -> None:
    assert categories(tmp_path, source) == ["skip"]


# --- behavior 7: a private reach is the test knowing too much -----------------


def test_a_single_underscore_attribute_on_anything_but_self_is_reported(tmp_path: Path) -> None:
    assert categories(tmp_path, A_PRIVATE_REACH) == ["private"]


def test_a_fake_under_support_may_reach_into_its_own_state(tmp_path: Path) -> None:
    assert categories(tmp_path, A_PRIVATE_REACH, "support/fake_holder.py") == []


# --- behavior 8: an exemption covers a skip or an existence, and nothing else --


def test_an_exempt_key_silences_the_skip_it_names(tmp_path: Path) -> None:
    path = written(tmp_path, A_SKIPPED_TEST)
    assert GATE.check_file(path, {f"{path}::test_held": "the owner said so"}) == []


def test_an_exempt_key_silences_the_existence_assertion_it_names(tmp_path: Path) -> None:
    path = written(tmp_path, AN_EXISTENCE_ASSERT_AND_A_SKIP)
    assert GATE.check_file(path, {f"{path}::test_held": "the owner said so"}) == []


def test_a_count_finding_outlives_the_exemption_on_its_test(tmp_path: Path) -> None:
    path = written(tmp_path, A_SKIPPED_TEST_WITH_NO_ASSERTION)
    exempt = {f"{path}::test_held": "the owner said so"}
    assert [category for category, _, _ in GATE.check_file(path, exempt)] == ["count"]


def test_the_module_table_is_what_an_unasked_check_reads(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = written(tmp_path, A_SKIPPED_TEST)
    monkeypatch.setitem(GATE.EXEMPT, f"{path}::test_held", "the owner said so")
    assert GATE.check_file(path) == []


# --- behavior 9: findings come back in the order the file reads --------------


def test_findings_arrive_in_line_order(tmp_path: Path) -> None:
    assert categories(tmp_path, A_HELPER_ABOVE_A_COUNTLESS_TEST) == ["outside", "count"]


# --- behavior 10: the CLI fails on a finding, and --report only sizes ---------


@pytest.mark.parametrize(("flags", "code"), [([], 1), (["--report"], 0)])
def test_a_finding_fails_the_run_unless_the_run_is_only_sizing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, flags: list[str], code: int
) -> None:
    path = written(tmp_path, TWO_ASSERTIONS)
    monkeypatch.setattr("sys.argv", ["check_test_assertions.py", *flags, str(path)])
    assert GATE.main() == code


def test_a_clean_file_passes_the_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = written(tmp_path, ONE_ASSERTION)
    monkeypatch.setattr("sys.argv", ["check_test_assertions.py", str(path)])
    assert GATE.main() == 0


def test_a_finding_that_carries_no_count_still_fails_the_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = written(tmp_path, AN_ASSERT_IN_A_LOOP)
    monkeypatch.setattr("sys.argv", ["check_test_assertions.py", str(path)])
    assert GATE.main() == 1
