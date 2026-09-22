"""The nesting gate: what counts as a level, what a function is called, and the exemption audit.

Each depth case is a module source the test writes itself, measured through
``depths``, whose whole answer — name, def line and depth — is what the case
pins. Each refusal case writes that source to a file under ``tmp_path`` and
drives ``check`` with an explicit exemption mapping, so the repository's own
table is never what is under test, and reads the printed finding back through
``capsys`` against the text seeded below.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import check_nesting as GATE
import pytest

from gates.conftest import written

if TYPE_CHECKING:
    from pathlib import Path

FLAT = """
def f():
    pass
"""

ONE_BLOCK = """
def f():
    if a:
        pass
"""

FOUR_DEEP = """
def f():
    if a:
        for b in c:
            while d:
                with e:
                    pass
"""

FIVE_DEEP = """
def f():
    if a:
        for b in c:
            while d:
                with e:
                    if g:
                        pass
"""

ELIF_CHAIN = """
def f():
    if a:
        pass
    elif b:
        pass
    elif c:
        pass
    else:
        pass
"""

ELSE_HOLDING_AN_IF = """
def f():
    if a:
        pass
    else:
        if b:
            pass
"""

HANDLER_BODY = """
def f():
    try:
        pass
    except ValueError:
        if a:
            pass
"""

FINALLY_BODY = """
def f():
    try:
        pass
    finally:
        if a:
            pass
"""

EXCEPT_STAR = """
def f():
    try:
        pass
    except* ValueError:
        pass
"""

MATCH_CASE = """
def f():
    match a:
        case 1:
            if b:
                pass
"""

ASYNC_BLOCKS = """
async def f():
    async with a:
        async for b in c:
            pass
"""

NESTED_DEF = """
def outer():
    if a:
        def inner():
            if b:
                if c:
                    if d:
                        if e:
                            pass
"""

METHOD = """
class Holder:
    def method(self):
        if a:
            pass
"""

NESTED_CLASS = """
class Outer:
    class Inner:
        def method(self):
            pass
"""

#: Where a refusal case writes its module, and the reason an exemption carries.
DEEP = "pkg/deep.py"
SHALLOW = "pkg/shallow.py"
GONE = "pkg/gone.py"
NAMED = "pkg/named.py"
REASON = "the arms are one decision"

#: The exact text the gate prints, seeded here so a changed verdict fails.
DEEP_FINDING = "pkg/deep.py:2: f() nests 5 deep (max 4)"
NAMED_FINDING = "pkg/named.py:2: f() nests 5 deep (max 4)"
NO_FILE = "EXEMPT['pkg/gone.py::f']: names no file"
NO_FUNCTION = (
    "EXEMPT['pkg/deep.py::missing']: names no function in pkg/deep.py — drop it"
)
WITHIN_LIMIT = (
    "EXEMPT['pkg/shallow.py::f']: nests 1 deep, within the limit of 4 — drop it"
)
SUMMARY = (
    "1 problem(s). Flatten the function, or add an EXEMPT entry saying why it stands."
)


def refusal(finding: str) -> tuple[int, str]:
    """The exit code and the whole output a single-finding run prints."""
    return 1, f"{finding}\n\n{SUMMARY}\n"


# --- behavior 1: a level is a block, and two shapes deliberately are not ------


@pytest.mark.parametrize(
    ("source", "found"),
    [
        (FLAT, [("f", 2, 0)]),
        (ONE_BLOCK, [("f", 2, 1)]),
        (FOUR_DEEP, [("f", 2, 4)]),
        (FIVE_DEEP, [("f", 2, 5)]),
        (ELIF_CHAIN, [("f", 2, 1)]),
        (ELSE_HOLDING_AN_IF, [("f", 2, 2)]),
        (HANDLER_BODY, [("f", 2, 2)]),
        (FINALLY_BODY, [("f", 2, 2)]),
        (EXCEPT_STAR, [("f", 2, 1)]),
        (MATCH_CASE, [("f", 2, 2)]),
        (ASYNC_BLOCKS, [("f", 2, 2)]),
    ],
)
def test_the_measured_depth_is_the_number_of_blocks_a_line_sits_inside(
    source: str, found: list[tuple[str, int, int]]
) -> None:
    assert GATE.depths(source) == found


# --- behavior 2: a function is named where the reader finds it ----------------


@pytest.mark.parametrize(
    ("source", "found"),
    [
        (NESTED_DEF, [("outer", 2, 1), ("outer.inner", 4, 4)]),
        (METHOD, [("Holder.method", 3, 1)]),
        (NESTED_CLASS, [("Outer.Inner.method", 4, 0)]),
    ],
)
def test_a_function_is_reported_under_its_dotted_name_and_measured_on_its_own(
    source: str, found: list[tuple[str, int, int]]
) -> None:
    assert GATE.depths(source) == found


# --- behavior 3: past the limit a site fails unless an exemption says why -----


def test_a_function_at_the_limit_passes_without_a_word(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    code = GATE.check([written(DEEP, FOUR_DEEP)], {})
    assert (code, capsys.readouterr().out) == (0, "")


def test_a_deep_function_is_refused_by_file_line_name_and_depth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    code = GATE.check([written(DEEP, FIVE_DEEP)], {})
    assert (code, capsys.readouterr().out) == refusal(DEEP_FINDING)


def test_an_exemption_on_the_site_itself_silences_the_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    code = GATE.check([written(DEEP, FIVE_DEEP)], {f"{DEEP}::f": REASON})
    assert (code, capsys.readouterr().out) == (0, "")


# --- behavior 4: an exemption is audited off the filesystem -------------------


def test_an_exemption_still_excusing_a_deep_site_is_silent_though_argv_is_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    written(DEEP, FIVE_DEEP)
    code = GATE.check([], {f"{DEEP}::f": REASON})
    assert (code, capsys.readouterr().out) == (0, "")


def test_an_exemption_naming_no_file_is_refused_by_its_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    code = GATE.check([], {f"{GONE}::f": REASON})
    assert (code, capsys.readouterr().out) == refusal(NO_FILE)


def test_an_exemption_naming_no_function_in_its_file_is_refused_by_its_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    written(DEEP, FIVE_DEEP)
    code = GATE.check([], {f"{DEEP}::missing": REASON})
    assert (code, capsys.readouterr().out) == refusal(NO_FUNCTION)


def test_an_exemption_on_a_site_within_the_limit_is_refused_with_its_depth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    written(SHALLOW, ONE_BLOCK)
    code = GATE.check([], {f"{SHALLOW}::f": REASON})
    assert (code, capsys.readouterr().out) == refusal(WITHIN_LIMIT)


# --- behavior 5: argv names the files, and the module's own table governs -----


def test_the_command_line_checks_the_files_it_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(GATE, "EXEMPT", {})
    monkeypatch.setattr(sys, "argv", ["check_nesting.py", written(NAMED, FIVE_DEEP)])
    code = GATE.main()
    assert (code, capsys.readouterr().out) == refusal(NAMED_FINDING)
