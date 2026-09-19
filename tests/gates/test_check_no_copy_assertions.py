"""The copy gate over the suite: a test asserts prose only when the tests wrote that prose.

``check_file`` returns one ``(category, location)`` finding per prose literal in
an assertion position that nothing in the suite seeded. A case here writes a
whole small suite under ``tmp_path`` — the file under test, and where the rule
needs it a ``tests/support`` module or fixture — and reads back the categories.

The shared pool is cached per ``tests`` root, and every case gets its own
``tmp_path``, so each pool is built once from the files that case wrote.
"""

from pathlib import Path
from textwrap import dedent

import check_no_copy_assertions as GATE
import pytest

UNSEEDED_PROSE = """
def test_wording() -> None:
    assert "alpha beta" in body()
"""

SEEDED_IN_THE_SAME_FILE = """
SEEDED = "alpha beta"

def test_wording() -> None:
    assert "alpha beta" in body(SEEDED)
"""

SEEDED_IN_A_SUPPORT_MODULE = """
def test_wording() -> None:
    assert "gamma delta" in body()
"""

A_SUPPORT_MODULE = """
REPLY = "gamma delta"
"""

A_SUPPORT_MODULE_WITH_AN_F_STRING = """
def reply(name: str) -> str:
    return f"waited on {name} seconds"
"""

INSIDE_A_FIXTURE_FILE = """
def test_wording() -> None:
    assert "epsilon zeta" in body()
"""

A_FIXTURE_FILE = "the page says epsilon zeta and stops\n"

COMPOSED_OF_SEEDED_PIECES = """
FIRST = "alpha beta"
SECOND = "gamma delta"

def test_wording() -> None:
    assert "alpha beta, gamma delta" in body(FIRST, SECOND)
"""

MATCHING_AN_F_STRING_SKELETON = """
def fake_reply(name: str) -> str:
    return f"waited on {name} seconds"

def test_wording() -> None:
    assert fake_reply("x") == "waited on 30 seconds"
"""

AN_F_STRING_WITH_NO_PROSE = """
def fake_reply(name: str) -> str:
    return f"{name}:9"

def test_wording() -> None:
    assert fake_reply("x") == "alpha beta"
"""

HANDED_TO_A_PLAIN_FUNCTION = """
def test_counting() -> None:
    assert words("alpha beta") == 2
"""

HANDED_TO_A_PLAIN_FUNCTION_BY_KEYWORD = """
def test_counting() -> None:
    assert words(text="alpha beta") == 2
"""

SEARCHED_FOR_ON_THE_VALUE = """
def test_searching() -> None:
    assert body.count("alpha beta") == 1
"""

AN_XML_FRAME = """
def test_frame() -> None:
    assert body == "<tag alpha beta>"
"""

A_KEY_VALUE_PAIR = """
def test_pair() -> None:
    assert body == "alpha=beta gamma"
"""

A_JSON_BODY = """
def test_body() -> None:
    assert body == '{"alpha": "beta gamma"}'
"""

A_SINGLE_WORD = """
def test_word() -> None:
    assert body == "alpha"
"""

A_RAISES_MATCH = """
import pytest

def test_refusal() -> None:
    with pytest.raises(ValueError, match="alpha beta"):
        fail()
"""

A_RAISES_WITH_NO_MATCH = """
import pytest

def test_refusal() -> None:
    with pytest.raises(ValueError):
        fail()
"""


def written(tmp_path: Path, source: str, name: str = "tests/test_sample.py") -> Path:
    """The suite file a case hands the gate, under a ``tests`` root of its own."""
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(source), encoding="utf-8")
    return path


def seed(tmp_path: Path, name: str, body: str) -> None:
    """Write one more file into the suite, for the pool to pick up."""
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(body), encoding="utf-8")


def categories(tmp_path: Path, source: str, name: str = "tests/test_sample.py") -> list[str]:
    """The category of every finding the gate returns for a source."""
    return [category for category, _ in GATE.check_file(written(tmp_path, source, name))]


# --- behavior 1: prose the tests never wrote is copy --------------------------


def test_prose_asserted_and_never_seeded_is_reported(tmp_path: Path) -> None:
    assert categories(tmp_path, UNSEEDED_PROSE) == ["assert-literal"]


def test_a_match_pattern_is_reported_under_its_own_category(tmp_path: Path) -> None:
    assert categories(tmp_path, A_RAISES_MATCH) == ["raises-match"]


def test_a_raises_context_with_no_match_asserts_no_prose(tmp_path: Path) -> None:
    assert categories(tmp_path, A_RAISES_WITH_NO_MATCH) == []


# --- behavior 2: what the tests wrote, in any of the places they write it ------


def test_prose_the_same_file_states_outside_an_assertion_is_seeded(tmp_path: Path) -> None:
    assert categories(tmp_path, SEEDED_IN_THE_SAME_FILE) == []


def test_prose_a_support_module_states_is_seeded(tmp_path: Path) -> None:
    seed(tmp_path, "tests/support/fake.py", A_SUPPORT_MODULE)
    assert categories(tmp_path, SEEDED_IN_A_SUPPORT_MODULE) == []


def test_prose_lying_inside_a_fixture_file_is_seeded(tmp_path: Path) -> None:
    seed(tmp_path, "tests/support/fixtures/page.txt", A_FIXTURE_FILE)
    assert categories(tmp_path, INSIDE_A_FIXTURE_FILE) == []


def test_prose_composed_of_seeded_pieces_is_seeded(tmp_path: Path) -> None:
    assert categories(tmp_path, COMPOSED_OF_SEEDED_PIECES) == []


def test_prose_matching_an_f_string_a_fake_writes_is_seeded(tmp_path: Path) -> None:
    assert categories(tmp_path, MATCHING_AN_F_STRING_SKELETON) == []


def test_an_f_string_a_support_module_writes_seeds_the_pool_too(tmp_path: Path) -> None:
    seed(tmp_path, "tests/support/fake.py", A_SUPPORT_MODULE_WITH_AN_F_STRING)
    assert categories(tmp_path, MATCHING_AN_F_STRING_SKELETON) == []


def test_an_f_string_holding_no_prose_seeds_nothing(tmp_path: Path) -> None:
    assert categories(tmp_path, AN_F_STRING_WITH_NO_PROSE) == ["assert-literal"]


# --- behavior 3: an input to the assertion is not a search for wording --------


@pytest.mark.parametrize("source", [HANDED_TO_A_PLAIN_FUNCTION, HANDED_TO_A_PLAIN_FUNCTION_BY_KEYWORD])
def test_prose_handed_to_a_plain_function_is_input_rather_than_copy(tmp_path: Path, source: str) -> None:
    assert categories(tmp_path, source) == []


def test_prose_handed_to_a_method_on_the_value_is_still_a_search_for_wording(tmp_path: Path) -> None:
    assert categories(tmp_path, SEARCHED_FOR_ON_THE_VALUE) == ["assert-literal"]


# --- behavior 4: a wire shape is not prose, and neither is one word -----------


@pytest.mark.parametrize("source", [AN_XML_FRAME, A_KEY_VALUE_PAIR, A_JSON_BODY, A_SINGLE_WORD])
def test_a_literal_that_is_not_prose_is_left_alone(tmp_path: Path, source: str) -> None:
    assert categories(tmp_path, source) == []


# --- behavior 5: a file outside any tests root has no shared pool -------------


def test_a_file_in_no_tests_root_draws_on_its_own_strings_alone(tmp_path: Path) -> None:
    assert categories(tmp_path, UNSEEDED_PROSE, "test_sample.py") == ["assert-literal"]


# --- behavior 6: the CLI fails on a finding, and --report only sizes ----------


@pytest.mark.parametrize(("flags", "code"), [([], 1), (["--report"], 0)])
def test_a_finding_fails_the_run_unless_the_run_is_only_sizing(tmp_path: Path, flags: list[str], code: int) -> None:
    path = written(tmp_path, UNSEEDED_PROSE)
    assert GATE.main([*flags, str(path)]) == code


def test_a_suite_seeding_everything_it_asserts_passes_the_cli(tmp_path: Path) -> None:
    path = written(tmp_path, SEEDED_IN_THE_SAME_FILE)
    assert GATE.main([str(path)]) == 0
