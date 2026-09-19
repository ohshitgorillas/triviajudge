"""The barrel gate: the re-export module, the pass-through method, and both exemption tables.

Every case writes the module under test into ``tmp_path`` at the path whose first
segment decides which rules reach it, and hands ``check`` explicit exemption
mappings, so the repository's own tables are never what is under test.
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


# --- behavior 1: a file of imports alone is a re-export, unless it is __init__ ---


@pytest.mark.parametrize(
    ("name", "source", "code"),
    [
        ("triviajudge/barrel.py", IMPORTS_ALONE, 1),
        ("triviajudge/__init__.py", IMPORTS_ALONE, 0),
        ("triviajudge/manifest.py", MANIFEST_ONLY, 1),
        ("triviajudge/annotated_manifest.py", ANNOTATED_MANIFEST, 1),
        ("triviajudge/constants.py", CONSTANT, 0),
        ("triviajudge/annotated.py", ANNOTATED_CONSTANT, 0),
        ("triviajudge/defines.py", DEFINES_A_FUNCTION, 0),
        ("triviajudge/standalone.py", NO_IMPORTS, 0),
    ],
)
def test_a_module_passes_only_while_it_defines_something_of_its_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, source: str, code: int
) -> None:
    monkeypatch.chdir(tmp_path)
    assert GATE.check([written(name, source)], {}, {}) == code


# --- behavior 2: a function that returns a call on its own arguments forwards ---


@pytest.mark.parametrize(
    ("source", "code"),
    [
        (FORWARDER, 1),
        (DOCSTRING_FORWARDER, 1),
        (ASYNC_FORWARDER, 1),
        (MODULE_FORWARDER, 1),
        (KEYWORD_CALL, 0),
        (STARRED_CALL, 0),
        (SUBSCRIPT_ROOT, 0),
        (PLAIN_CALL, 0),
        (EXTRA_STATEMENT, 0),
        (BARE_RETURN, 0),
        (REORDERED_ARGS, 0),
    ],
)
def test_a_pass_through_fails_and_anything_that_does_more_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str, code: int
) -> None:
    monkeypatch.chdir(tmp_path)
    assert GATE.check([written("triviajudge/mod.py", source)], {}, {}) == code


@pytest.mark.parametrize(
    ("name", "code"),
    [("triviajudge/mod.py", 1), ("scripts/gates/mod.py", 1), ("elsewhere/mod.py", 0)],
)
def test_the_forwarder_rule_reaches_the_trees_it_names_and_no_others(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, code: int
) -> None:
    monkeypatch.chdir(tmp_path)
    assert GATE.check([written(name, FORWARDER)], {}, {}) == code


# --- behavior 3: an exemption silences its own site and nothing else ----------


@pytest.mark.parametrize(
    ("name", "source", "exempt", "module_exempt", "code"),
    [
        ("triviajudge/barrel.py", IMPORTS_ALONE, {}, {"triviajudge/barrel.py": REASON}, 0),
        ("triviajudge/mod.py", FORWARDER, {"triviajudge/mod.py::f": REASON}, {}, 0),
    ],
)
def test_an_exempt_site_passes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    name: str,
    source: str,
    exempt: dict[str, str],
    module_exempt: dict[str, str],
    code: int,
) -> None:
    monkeypatch.chdir(tmp_path)
    assert GATE.check([written(name, source)], exempt, module_exempt) == code


# --- behavior 4: an exemption excusing nothing is itself a failure ------------


@pytest.mark.parametrize(
    ("existing", "source", "module_exempt", "code"),
    [
        ("triviajudge/barrel.py", IMPORTS_ALONE, {"triviajudge/barrel.py": REASON}, 0),
        (None, IMPORTS_ALONE, {"triviajudge/gone.py": REASON}, 1),
        ("triviajudge/constants.py", CONSTANT, {"triviajudge/constants.py": REASON}, 1),
    ],
)
def test_a_module_exemption_stands_only_while_its_module_re_exports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    existing: str | None,
    source: str,
    module_exempt: dict[str, str],
    code: int,
) -> None:
    monkeypatch.chdir(tmp_path)
    if existing is not None:
        written(existing, source)
    assert GATE.check([], {}, module_exempt) == code


@pytest.mark.parametrize(
    ("existing", "source", "exempt", "code"),
    [
        ("triviajudge/mod.py", FORWARDER, {"triviajudge/mod.py::f": REASON}, 0),
        (None, FORWARDER, {"triviajudge/gone.py::f": REASON}, 1),
        ("triviajudge/mod.py", FORWARDER, {"triviajudge/mod.py::missing": REASON}, 1),
        ("triviajudge/plain.py", PLAIN_CALL, {"triviajudge/plain.py::f": REASON}, 1),
    ],
)
def test_a_forwarder_exemption_stands_only_while_it_matches_a_forwarder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    existing: str | None,
    source: str,
    exempt: dict[str, str],
    code: int,
) -> None:
    monkeypatch.chdir(tmp_path)
    if existing is not None:
        written(existing, source)
    assert GATE.check([], exempt, {}) == code


@pytest.mark.parametrize("key", ["triviajudge/gone.py", "triviajudge/gone.py::f"])
def test_an_unenforceable_exemption_is_named_by_its_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], key: str
) -> None:
    monkeypatch.chdir(tmp_path)
    GATE.check([], {key: REASON}, {key: REASON})
    assert key in capsys.readouterr().out


# --- behavior 5: argv names the files, and the module's own tables govern -----


@pytest.mark.parametrize(("source", "code"), [(CONSTANT, 0), (IMPORTS_ALONE, 1)])
def test_the_command_line_checks_the_files_it_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str, code: int
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(GATE, "MODULE_EXEMPT", {})
    monkeypatch.setattr(GATE, "FORWARDER_EXEMPT", {})
    monkeypatch.setattr(sys, "argv", ["check_no_barrels.py", written("triviajudge/named.py", source)])
    assert GATE.main() == code
