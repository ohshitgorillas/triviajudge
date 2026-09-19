"""The stdlib gate: a package file imports the standard library and the package, nothing else.

Every import in the file is read off the AST, so the cases here vary the import
form rather than its position: plain ``import``, ``from ... import``, a dotted
submodule judged by its root, and a relative import, which names nothing
outside the package and is left alone.

A refusal is matched on the path the test wrote and the module name it put in
the import, never on the sentence the gate wraps around them.
"""

import ast
import sys
from pathlib import Path

import check_stdlib_only as GATE
import pytest

STDLIB_IMPORT = "import json\nimport sys\n"

TWO_NAMES_ON_ONE_LINE = "import json, sys\n"

STDLIB_FROM = "from pathlib import Path\n"

SUBMODULE_OF_THE_STDLIB = "import urllib.request\n"

SELF_IMPORT = "from triviajudge import core\n"

SELF_IMPORT_PLAIN = "import triviajudge\n"

RELATIVE_IMPORT = "from . import core\n"

THIRD_PARTY_IMPORT = "import pytest\n"

THIRD_PARTY_FROM = "from pytest import fixture\n"

THIRD_PARTY_SUBMODULE = "import pytest.mark.structures\n"

IMPORT_IN_A_FUNCTION = "def load() -> None:\n    import pytest\n\n    del pytest\n"


def written(tmp_path: Path, source: str) -> Path:
    """The source written to a file the gate can read."""
    path = tmp_path / "module.py"
    path.write_text(source, encoding="utf-8")
    return path


# --- behavior 1: the standard library, the package and a relative import pass ---


@pytest.mark.parametrize(
    "source",
    [STDLIB_IMPORT, STDLIB_FROM, SUBMODULE_OF_THE_STDLIB, SELF_IMPORT, SELF_IMPORT_PLAIN, RELATIVE_IMPORT],
)
def test_an_import_of_the_standard_library_or_the_package_itself_is_no_fault(tmp_path: Path, source: str) -> None:
    assert GATE.foreign(written(tmp_path, source)) == []


# --- behavior 2: anything else is named, wherever the import sits ------------


@pytest.mark.parametrize(
    "source",
    [THIRD_PARTY_IMPORT, THIRD_PARTY_FROM, THIRD_PARTY_SUBMODULE, IMPORT_IN_A_FUNCTION],
)
def test_an_import_from_outside_the_standard_library_is_a_fault(tmp_path: Path, source: str) -> None:
    assert len(GATE.foreign(written(tmp_path, source))) == 1


def test_the_fault_names_the_module_the_file_imported(tmp_path: Path) -> None:
    assert "'pytest'" in GATE.foreign(written(tmp_path, THIRD_PARTY_IMPORT))[0]


def test_two_stdlib_names_on_one_line_are_both_read() -> None:
    assert GATE.roots(ast.parse(TWO_NAMES_ON_ONE_LINE)) == [(1, "json"), (1, "sys")]


# --- behavior 3: the exit code is the verdict over every file handed over ----


def test_a_package_of_stdlib_imports_exits_clean(tmp_path: Path) -> None:
    assert GATE.check([written(tmp_path, STDLIB_IMPORT)]) == 0


def test_one_third_party_import_fails_the_run(tmp_path: Path) -> None:
    assert GATE.check([written(tmp_path, THIRD_PARTY_IMPORT)]) == 1


# --- behavior 4: argv names the files, and its absence names the package -----


def test_main_judges_the_file_argv_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = written(tmp_path, THIRD_PARTY_FROM)
    monkeypatch.setattr(sys, "argv", ["check_stdlib_only.py", str(path)])
    assert GATE.main() == 1


def test_main_with_no_argv_judges_the_whole_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / GATE.PACKAGE).mkdir()
    (tmp_path / GATE.PACKAGE / "mod.py").write_text(THIRD_PARTY_IMPORT, encoding="utf-8")
    monkeypatch.setattr(GATE, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["check_stdlib_only.py"])
    assert GATE.main() == 1
