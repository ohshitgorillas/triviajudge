"""The nesting gate: what counts as a level, what a function is called, and the exemption audit.

Each depth case is a module source the test writes itself, measured through
``depths``; each refusal case writes that source to a file under ``tmp_path`` and
drives ``check`` with an explicit exemption mapping, so the repository's own
table is never what is under test.
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


def measured(source: str) -> dict[str, int]:
    """Qualified function name -> the deepest nesting it reaches."""
    return {name: depth for name, _line, depth in GATE.depths(source)}


# --- behavior 1: a level is a block, and two shapes deliberately are not ------


@pytest.mark.parametrize(
    ("source", "depth"),
    [
        (FLAT, 0),
        (ONE_BLOCK, 1),
        (FOUR_DEEP, 4),
        (FIVE_DEEP, 5),
        (ELIF_CHAIN, 1),
        (ELSE_HOLDING_AN_IF, 2),
        (HANDLER_BODY, 2),
        (FINALLY_BODY, 2),
        (EXCEPT_STAR, 1),
        (MATCH_CASE, 2),
        (ASYNC_BLOCKS, 2),
    ],
)
def test_the_measured_depth_is_the_number_of_blocks_a_line_sits_inside(source: str, depth: int) -> None:
    assert measured(source)["f"] == depth


# --- behavior 2: a function is named where the reader finds it ----------------


@pytest.mark.parametrize(
    ("source", "found"),
    [
        (NESTED_DEF, {"outer": 1, "outer.inner": 4}),
        (METHOD, {"Holder.method": 1}),
        (NESTED_CLASS, {"Outer.Inner.method": 0}),
    ],
)
def test_a_function_is_reported_under_its_dotted_name_and_measured_on_its_own(
    source: str, found: dict[str, int]
) -> None:
    assert measured(source) == found


# --- behavior 3: past the limit a site fails unless an exemption says why -----


@pytest.mark.parametrize(
    ("source", "exempt", "code"),
    [
        (FOUR_DEEP, {}, 0),
        (FIVE_DEEP, {}, 1),
        (FIVE_DEEP, {"pkg/deep.py::f": "the arms are one decision"}, 0),
    ],
)
def test_a_deep_function_is_refused_unless_its_own_site_is_exempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str, exempt: dict[str, str], code: int
) -> None:
    monkeypatch.chdir(tmp_path)
    assert GATE.check([written("pkg/deep.py", source)], exempt) == code


def test_a_deep_function_is_named_by_the_file_it_sits_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    GATE.check([written("pkg/deep.py", FIVE_DEEP)], {})
    assert "pkg/deep.py" in capsys.readouterr().out


# --- behavior 4: an exemption is audited off the filesystem -------------------


@pytest.mark.parametrize(
    ("existing", "source", "key", "code"),
    [
        ("pkg/deep.py", FIVE_DEEP, "pkg/deep.py::f", 0),
        (None, FLAT, "pkg/gone.py::f", 1),
        ("pkg/deep.py", FIVE_DEEP, "pkg/deep.py::missing", 1),
        ("pkg/shallow.py", ONE_BLOCK, "pkg/shallow.py::f", 1),
    ],
)
def test_an_exemption_stands_only_while_it_excuses_a_site_past_the_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    existing: str | None,
    source: str,
    key: str,
    code: int,
) -> None:
    monkeypatch.chdir(tmp_path)
    if existing is not None:
        written(existing, source)
    assert GATE.check([], {key: "the reason the entry carries"}) == code


def test_an_unenforceable_exemption_is_named_by_its_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    GATE.check([], {"pkg/gone.py::f": "the reason the entry carries"})
    assert "pkg/gone.py::f" in capsys.readouterr().out


# --- behavior 5: argv names the files, and the module's own table governs -----


@pytest.mark.parametrize(("source", "code"), [(FOUR_DEEP, 0), (FIVE_DEEP, 1)])
def test_the_command_line_checks_the_files_it_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str, code: int
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(GATE, "EXEMPT", {})
    monkeypatch.setattr(sys, "argv", ["check_nesting.py", written("pkg/named.py", source)])
    assert GATE.main() == code
