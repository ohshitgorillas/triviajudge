"""The barrel gate: the re-export module, the pass-through method, and both exemption tables.

Every case writes the module under test into ``tmp_path`` at the path whose first
segment decides which rules reach it, and hands the gate explicit exemption
mappings, so the repository's own tables are never what is under test. A case
asserts the finding itself — the path, the key and the sentence the gate prints —
rather than how many findings there were.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import check_no_barrels as GATE
import pytest

from gates.conftest import written

if TYPE_CHECKING:
    from pathlib import Path

IMPORTS_ALONE = """
import os
from pathlib import Path
"""

CONSTANT = """
import os

NAME = 1
"""

ANNOTATED_CONSTANT = """
import os

NAME: int = 1
"""

MANIFEST_ONLY = """
import os

__all__ = ["os"]
"""

ANNOTATED_MANIFEST = """
import os

__all__: list[str] = ["os"]
"""

DEFINES_A_FUNCTION = """
import os

def f():
    return os
"""

NO_IMPORTS = """
NAME = 1
"""

FORWARDER = """
class Holder:
    def f(self, x):
        return self.other.f(x)
"""

DOCSTRING_FORWARDER = '''
class Holder:
    def f(self, x):
        """Hand the call on."""
        return self.other.f(x)
'''

ASYNC_FORWARDER = """
class Holder:
    async def f(self, x):
        return await self.other.f(x)
"""

MODULE_FORWARDER = """
def f(a, b):
    return holder.f(a, b)
"""

KEYWORD_CALL = """
class Holder:
    def f(self, x):
        return self.other.f(x, scope=x)
"""

STARRED_CALL = """
class Holder:
    def f(self, x):
        return self.other.f(*x)
"""

SUBSCRIPT_ROOT = """
class Holder:
    def f(self, x):
        return self.other[0].f(x)
"""

PLAIN_CALL = """
class Holder:
    def f(self, x):
        return helper(x)
"""

EXTRA_STATEMENT = """
class Holder:
    def f(self, x):
        x = x + 1
        return self.other.f(x)
"""

BARE_RETURN = """
class Holder:
    def f(self, x):
        return
"""

REORDERED_ARGS = """
class Holder:
    def f(self, x, y):
        return self.other.f(y, x)
"""

REASON = "the collaborator has no other route in"

#: The sentences the gate prints, one per category, with the site left open.
REEXPORT = "{}: imports and defines nothing — a re-export module is not a split"
FORWARDS = "{}: returns a call on its own arguments — move the callers, not the method"
MODULE_NO_FILE = "MODULE_EXEMPT[{!r}]: names no file"
MODULE_DEFINES = (
    "MODULE_EXEMPT[{!r}]: the module defines something, so it needs no exemption"
)
FORWARDER_NO_FILE = "FORWARDER_EXEMPT[{!r}]: names no file"
FORWARDER_NO_MATCH = "FORWARDER_EXEMPT[{!r}]: matches no forwarder"
SUMMARY = "\n{} problem(s). A split that changed no caller did not happen.\n"

#: The sites the cases write, and the keys they exempt.
BARREL = "triviajudge/barrel.py"
MOD = "triviajudge/mod.py"
MOD_F = "triviajudge/mod.py::f"
GONE = "triviajudge/gone.py"
GONE_F = "triviajudge/gone.py::f"
PLAIN_F = "triviajudge/plain.py::f"
MOD_MISSING = "triviajudge/mod.py::missing"

#: What ``check`` prints end to end: every finding, then the count.
ONE_PROBLEM_REPORT = REEXPORT.format(BARREL) + "\n" + SUMMARY.format(1)
TWO_PROBLEM_REPORT = (
    REEXPORT.format(BARREL)
    + "\n"
    + FORWARDER_NO_FILE.format(GONE_F)
    + "\n"
    + SUMMARY.format(2)
)


# --- behavior 1: a file of imports alone is a re-export, unless it is __init__ ---


@pytest.mark.parametrize(
    ("name", "source", "problems"),
    [
        (BARREL, IMPORTS_ALONE, [REEXPORT.format(BARREL)]),
        ("triviajudge/__init__.py", IMPORTS_ALONE, []),
        (
            "triviajudge/manifest.py",
            MANIFEST_ONLY,
            [REEXPORT.format("triviajudge/manifest.py")],
        ),
        (
            "triviajudge/annotated_manifest.py",
            ANNOTATED_MANIFEST,
            [REEXPORT.format("triviajudge/annotated_manifest.py")],
        ),
        ("triviajudge/constants.py", CONSTANT, []),
        ("triviajudge/annotated.py", ANNOTATED_CONSTANT, []),
        ("triviajudge/defines.py", DEFINES_A_FUNCTION, []),
        ("triviajudge/standalone.py", NO_IMPORTS, []),
    ],
)
def test_a_module_passes_only_while_it_defines_something_of_its_own(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    source: str,
    problems: list[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    assert GATE.faults(written(name, source), {}, {}) == problems


# --- behavior 2: a function that returns a call on its own arguments forwards ---


@pytest.mark.parametrize(
    ("source", "problems"),
    [
        (FORWARDER, [FORWARDS.format(MOD_F)]),
        (DOCSTRING_FORWARDER, [FORWARDS.format(MOD_F)]),
        (ASYNC_FORWARDER, [FORWARDS.format(MOD_F)]),
        (MODULE_FORWARDER, [FORWARDS.format(MOD_F)]),
        (KEYWORD_CALL, []),
        (STARRED_CALL, []),
        (SUBSCRIPT_ROOT, []),
        (PLAIN_CALL, []),
        (EXTRA_STATEMENT, []),
        (BARE_RETURN, []),
        (REORDERED_ARGS, []),
    ],
)
def test_a_pass_through_fails_and_anything_that_does_more_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str, problems: list[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert GATE.faults(written(MOD, source), {}, {}) == problems


@pytest.mark.parametrize(
    ("name", "problems"),
    [
        (MOD, [FORWARDS.format(MOD_F)]),
        ("scripts/gates/mod.py", [FORWARDS.format("scripts/gates/mod.py::f")]),
        ("elsewhere/mod.py", []),
    ],
)
def test_the_forwarder_rule_reaches_the_trees_it_names_and_no_others(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, problems: list[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert GATE.faults(written(name, FORWARDER), {}, {}) == problems


# --- behavior 3: an exemption silences its own site and nothing else ----------


@pytest.mark.parametrize(
    ("name", "source", "exempt", "module_exempt"),
    [
        (BARREL, IMPORTS_ALONE, {}, {BARREL: REASON}),
        (MOD, FORWARDER, {MOD_F: REASON}, {}),
    ],
)
def test_an_exempt_site_reports_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    name: str,
    source: str,
    exempt: dict[str, str],
    module_exempt: dict[str, str],
) -> None:
    monkeypatch.chdir(tmp_path)
    assert GATE.faults(written(name, source), exempt, module_exempt) == []


# --- behavior 4: an exemption excusing nothing is itself a failure ------------


@pytest.mark.parametrize(
    ("existing", "source", "module_exempt", "problems"),
    [
        (BARREL, IMPORTS_ALONE, {BARREL: REASON}, []),
        (None, IMPORTS_ALONE, {GONE: REASON}, [MODULE_NO_FILE.format(GONE)]),
        (
            "triviajudge/constants.py",
            CONSTANT,
            {"triviajudge/constants.py": REASON},
            [MODULE_DEFINES.format("triviajudge/constants.py")],
        ),
    ],
)
def test_a_module_exemption_stands_only_while_its_module_re_exports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    existing: str | None,
    source: str,
    module_exempt: dict[str, str],
    problems: list[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    if existing is not None:
        written(existing, source)
    assert GATE.stale_modules(module_exempt) == problems


@pytest.mark.parametrize(
    ("existing", "source", "exempt", "problems"),
    [
        (MOD, FORWARDER, {MOD_F: REASON}, []),
        (None, FORWARDER, {GONE_F: REASON}, [FORWARDER_NO_FILE.format(GONE_F)]),
        (
            MOD,
            FORWARDER,
            {MOD_MISSING: REASON},
            [FORWARDER_NO_MATCH.format(MOD_MISSING)],
        ),
        (
            "triviajudge/plain.py",
            PLAIN_CALL,
            {PLAIN_F: REASON},
            [FORWARDER_NO_MATCH.format(PLAIN_F)],
        ),
    ],
)
def test_a_forwarder_exemption_stands_only_while_it_matches_a_forwarder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    existing: str | None,
    source: str,
    exempt: dict[str, str],
    problems: list[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    if existing is not None:
        written(existing, source)
    assert GATE.stale_forwarders(exempt) == problems


# --- behavior 5: check prints what it found, and argv names the files ---------


def test_check_prints_every_finding_then_the_count_and_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    code = GATE.check([written(BARREL, IMPORTS_ALONE)], {GONE_F: REASON}, {})
    assert (code, capsys.readouterr().out) == (1, TWO_PROBLEM_REPORT)


def test_check_prints_nothing_when_every_file_is_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    code = GATE.check([written("triviajudge/constants.py", CONSTANT)], {}, {})
    assert (code, capsys.readouterr().out) == (0, "")


@pytest.mark.parametrize(
    ("source", "code", "out"),
    [(CONSTANT, 0, ""), (IMPORTS_ALONE, 1, ONE_PROBLEM_REPORT)],
)
def test_the_command_line_checks_the_files_it_names(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *,
    source: str,
    code: int,
    out: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(GATE, "MODULE_EXEMPT", {})
    monkeypatch.setattr(GATE, "FORWARDER_EXEMPT", {})
    monkeypatch.setattr(sys, "argv", ["check_no_barrels.py", written(BARREL, source)])
    assert (GATE.main(), capsys.readouterr().out) == (code, out)
