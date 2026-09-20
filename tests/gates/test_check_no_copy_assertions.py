"""The copy gate over the suite: a test asserts prose only when the tests wrote that prose.

``check_file`` returns one ``(category, location)`` finding per prose literal in
an assertion position that nothing in the suite seeded. A case here writes a
whole small suite under ``tmp_path`` — the file under test, and where the rule
needs it a ``tests/support`` module or fixture — and reads back every finding as
``<line> <category>: <literal>``, against the exact text seeded above.

A source whose point is that some literal is *not* copy carries a control
assertion on prose nothing seeded, so the expected findings name the control
line alone: a gate that stopped reporting anything fails the case too.

The shared pool is cached per ``tests`` root, and every case gets its own
``tmp_path``, so each pool is built once from the files that case wrote.
"""

from pathlib import Path
from textwrap import dedent

import check_no_copy_assertions as GATE
import pytest

#: The control finding, for a source whose control sits on line 6.
CONTROL_ON_LINE_6 = "6 assert-literal: 'omega psi'"

UNSEEDED_PROSE = """
def test_wording() -> None:
    assert "alpha beta" in body()
"""
UNSEEDED_PROSE_FINDING = "3 assert-literal: 'alpha beta'"

SEEDED_IN_THE_SAME_FILE = """
SEEDED = "alpha beta"

def test_wording() -> None:
    assert "alpha beta" in body(SEEDED)

def test_control() -> None:
    assert "omega psi" in body()
"""
SEEDED_IN_THE_SAME_FILE_FINDING = "8 assert-literal: 'omega psi'"

ASSERTS_ONLY_SEEDED_PROSE = """
SEEDED = "alpha beta"

def test_wording() -> None:
    assert "alpha beta" in body(SEEDED)
"""

SEEDED_IN_A_SUPPORT_MODULE = """
def test_wording() -> None:
    assert "gamma delta" in body()

def test_control() -> None:
    assert "omega psi" in body()
"""
SUPPORT_PROSE_FINDING = "3 assert-literal: 'gamma delta'"

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

def test_control() -> None:
    assert "omega psi" in body()
"""

A_FIXTURE_FILE = "the page says epsilon zeta and stops\n"

COMPOSED_OF_SEEDED_PIECES = """
FIRST = "alpha beta"
SECOND = "gamma delta"

def test_wording() -> None:
    assert "alpha beta, gamma delta" in body(FIRST, SECOND)

def test_control() -> None:
    assert "omega psi" in body()
"""
COMPOSED_OF_SEEDED_PIECES_FINDING = "9 assert-literal: 'omega psi'"

MATCHING_AN_F_STRING_SKELETON = """
def fake_reply(name: str) -> str:
    return f"waited on {name} seconds"

def test_wording() -> None:
    assert fake_reply("x") == "waited on 30 seconds"

def test_control() -> None:
    assert "omega psi" in body()
"""
MATCHING_AN_F_STRING_SKELETON_FINDING = "9 assert-literal: 'omega psi'"

MATCHING_A_SUPPORT_F_STRING = """
def test_wording() -> None:
    assert reply("x") == "waited on 30 seconds"

def test_control() -> None:
    assert "omega psi" in body()
"""

AN_F_STRING_WITH_NO_PROSE = """
def fake_reply(name: str) -> str:
    return f"{name}:9"

def test_wording() -> None:
    assert fake_reply("x") == "alpha beta"
"""
AN_F_STRING_WITH_NO_PROSE_FINDING = "6 assert-literal: 'alpha beta'"

HANDED_TO_A_PLAIN_FUNCTION = """
def test_counting() -> None:
    assert words("alpha beta") == 2

def test_control() -> None:
    assert "omega psi" in body()
"""

HANDED_TO_A_PLAIN_FUNCTION_BY_KEYWORD = """
def test_counting() -> None:
    assert words(text="alpha beta") == 2

def test_control() -> None:
    assert "omega psi" in body()
"""

SEARCHED_FOR_ON_THE_VALUE = """
def test_searching() -> None:
    assert body.count("alpha beta") == 1
"""
SEARCHED_FOR_ON_THE_VALUE_FINDING = "3 assert-literal: 'alpha beta'"

AN_XML_FRAME = """
def test_frame() -> None:
    assert body == "<tag alpha beta>"

def test_control() -> None:
    assert "omega psi" in body()
"""

A_KEY_VALUE_PAIR = """
def test_pair() -> None:
    assert body == "alpha=beta gamma"

def test_control() -> None:
    assert "omega psi" in body()
"""

A_JSON_BODY = """
def test_body() -> None:
    assert body == '{"alpha": "beta gamma"}'

def test_control() -> None:
    assert "omega psi" in body()
"""

A_SINGLE_WORD = """
def test_word() -> None:
    assert body == "alpha"

def test_control() -> None:
    assert "omega psi" in body()
"""

A_RAISES_MATCH = """
import pytest

def test_refusal() -> None:
    with pytest.raises(ValueError, match="alpha beta"):
        fail()
"""
A_RAISES_MATCH_FINDING = "5 raises-match: 'alpha beta'"

A_RAISES_WITH_NO_MATCH = """
import pytest

def test_refusal() -> None:
    with pytest.raises(ValueError):
        fail()

def test_control() -> None:
    assert "omega psi" in body()
"""
A_RAISES_WITH_NO_MATCH_FINDING = "9 assert-literal: 'omega psi'"

#: What ``--report`` adds under the findings for one ``assert-literal`` site.
REPORT_TAIL = "assert-literal: 1 site(s)\ncopy assertions: 1 total (report only)\n"


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


def reported(tmp_path: Path, source: str, name: str = "tests/test_sample.py") -> list[str]:
    """Every finding for a source, as ``<line> <category>: <literal>``."""
    path = written(tmp_path, source, name)
    return [location.removeprefix(f"{path}:") for _, location in GATE.check_file(path)]


# --- behavior 1: prose the tests never wrote is copy --------------------------


def test_prose_asserted_and_never_seeded_is_reported(tmp_path: Path) -> None:
    assert reported(tmp_path, UNSEEDED_PROSE) == [UNSEEDED_PROSE_FINDING]


def test_a_match_pattern_is_reported_under_its_own_category(tmp_path: Path) -> None:
    assert reported(tmp_path, A_RAISES_MATCH) == [A_RAISES_MATCH_FINDING]


def test_a_raises_context_with_no_match_asserts_no_prose(tmp_path: Path) -> None:
    assert reported(tmp_path, A_RAISES_WITH_NO_MATCH) == [A_RAISES_WITH_NO_MATCH_FINDING]


# --- behavior 2: what the tests wrote, in any of the places they write it ------


def test_prose_the_same_file_states_outside_an_assertion_is_seeded(tmp_path: Path) -> None:
    assert reported(tmp_path, SEEDED_IN_THE_SAME_FILE) == [SEEDED_IN_THE_SAME_FILE_FINDING]


def test_prose_a_support_module_states_is_seeded(tmp_path: Path) -> None:
    seed(tmp_path, "tests/support/fake.py", A_SUPPORT_MODULE)
    assert reported(tmp_path, SEEDED_IN_A_SUPPORT_MODULE) == [CONTROL_ON_LINE_6]


def test_prose_lying_inside_a_fixture_file_is_seeded(tmp_path: Path) -> None:
    seed(tmp_path, "tests/support/fixtures/page.txt", A_FIXTURE_FILE)
    assert reported(tmp_path, INSIDE_A_FIXTURE_FILE) == [CONTROL_ON_LINE_6]


def test_prose_composed_of_seeded_pieces_is_seeded(tmp_path: Path) -> None:
    assert reported(tmp_path, COMPOSED_OF_SEEDED_PIECES) == [COMPOSED_OF_SEEDED_PIECES_FINDING]


def test_prose_matching_an_f_string_a_fake_writes_is_seeded(tmp_path: Path) -> None:
    assert reported(tmp_path, MATCHING_AN_F_STRING_SKELETON) == [MATCHING_AN_F_STRING_SKELETON_FINDING]


def test_an_f_string_a_support_module_writes_seeds_the_pool_too(tmp_path: Path) -> None:
    seed(tmp_path, "tests/support/fake.py", A_SUPPORT_MODULE_WITH_AN_F_STRING)
    assert reported(tmp_path, MATCHING_A_SUPPORT_F_STRING) == [CONTROL_ON_LINE_6]


def test_an_f_string_holding_no_prose_seeds_nothing(tmp_path: Path) -> None:
    assert reported(tmp_path, AN_F_STRING_WITH_NO_PROSE) == [AN_F_STRING_WITH_NO_PROSE_FINDING]


# --- behavior 3: an input to the assertion is not a search for wording --------


def test_prose_handed_to_a_plain_function_is_input_rather_than_copy(tmp_path: Path) -> None:
    assert reported(tmp_path, HANDED_TO_A_PLAIN_FUNCTION) == [CONTROL_ON_LINE_6]


def test_prose_handed_to_a_plain_function_by_keyword_is_input_too(tmp_path: Path) -> None:
    assert reported(tmp_path, HANDED_TO_A_PLAIN_FUNCTION_BY_KEYWORD) == [CONTROL_ON_LINE_6]


def test_prose_handed_to_a_method_on_the_value_is_still_a_search_for_wording(tmp_path: Path) -> None:
    assert reported(tmp_path, SEARCHED_FOR_ON_THE_VALUE) == [SEARCHED_FOR_ON_THE_VALUE_FINDING]


# --- behavior 4: a wire shape is not prose, and neither is one word -----------


def test_an_xml_frame_is_left_alone(tmp_path: Path) -> None:
    assert reported(tmp_path, AN_XML_FRAME) == [CONTROL_ON_LINE_6]


def test_a_key_value_pair_is_left_alone(tmp_path: Path) -> None:
    assert reported(tmp_path, A_KEY_VALUE_PAIR) == [CONTROL_ON_LINE_6]


def test_a_json_body_is_left_alone(tmp_path: Path) -> None:
    assert reported(tmp_path, A_JSON_BODY) == [CONTROL_ON_LINE_6]


def test_a_single_word_is_left_alone(tmp_path: Path) -> None:
    assert reported(tmp_path, A_SINGLE_WORD) == [CONTROL_ON_LINE_6]


# --- behavior 5: a file outside any tests root has no shared pool -------------


def test_a_file_in_no_tests_root_draws_on_its_own_strings_alone(tmp_path: Path) -> None:
    seed(tmp_path, "tests/support/fake.py", A_SUPPORT_MODULE)
    assert reported(tmp_path, SEEDED_IN_A_SUPPORT_MODULE, "test_sample.py") == [
        SUPPORT_PROSE_FINDING,
        CONTROL_ON_LINE_6,
    ]


# --- behavior 6: the CLI fails on a finding, and --report only sizes ----------


def test_the_cli_prints_the_finding_it_refuses(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = written(tmp_path, UNSEEDED_PROSE)
    code = GATE.main([str(path)])
    assert (code, capsys.readouterr().out) == (1, f"{path}:{UNSEEDED_PROSE_FINDING}\n")


def test_report_mode_prints_the_finding_with_a_count_and_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = written(tmp_path, UNSEEDED_PROSE)
    code = GATE.main(["--report", str(path)])
    assert (code, capsys.readouterr().out) == (0, f"{path}:{UNSEEDED_PROSE_FINDING}\n{REPORT_TAIL}")


def test_a_suite_seeding_everything_it_asserts_passes_the_cli_in_silence(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = GATE.main([str(written(tmp_path, ASSERTS_ONLY_SEEDED_PROSE))])
    assert (code, capsys.readouterr().out) == (0, "")
