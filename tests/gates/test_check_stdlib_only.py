"""The stdlib gate: a package file imports the standard library and the package, nothing else.

Every import in the file is read off the AST, so the cases here vary the import
form rather than its position: plain ``import``, ``from ... import``, a dotted
submodule judged by its root, two names on one line, an import in a function
body, and a relative import, which names nothing outside the package and is
left alone.

A refusal is matched whole -- the path the test wrote, the line the import sits
on, the module name and the sentence around them -- against text seeded here,
so a verdict that moves is a test that fails.
"""

import sys
from pathlib import Path

import check_stdlib_only as GATE
import pytest

STDLIB_IMPORT = "import json\nimport sys\n"

STDLIB_FROM = "from pathlib import Path\n"

SUBMODULE_OF_THE_STDLIB = "import urllib.request\n"

SELF_IMPORT = "from triviajudge import core\n"

SELF_IMPORT_PLAIN = "import triviajudge\n"

RELATIVE_IMPORT = "from . import core\n"

THIRD_PARTY_IMPORT = "import pytest\n"

THIRD_PARTY_FROM = "from pytest import fixture\n"

THIRD_PARTY_SUBMODULE = "import pytest.mark.structures\n"

TWO_FOREIGN_NAMES_ON_ONE_LINE = "import pytest, yaml\n"

IMPORT_IN_A_FUNCTION = "def load() -> None:\n    import pytest\n\n    del pytest\n"

#: The refusal the gate prints for one foreign import.
REFUSAL = "{path}:{line}: imports '{name}', which is neither the standard library nor triviajudge"

#: What the gate prints after the refusals, for one problem.
ONE_PROBLEM_REMEDY = (
    "\n1 problem(s). The package is the standard library alone, which is what\n"
    "keeps `dependencies` in pyproject.toml empty. A third-party import belongs in the dev extra.\n"
)

#: What the gate prints when one file is clean.
ONE_CLEAN_FILE = (
    "[ok] 1 package file(s) import the standard library and triviajudge only\n"
)


def written(tmp_path: Path, source: str) -> Path:
    """The source written to a file the gate can read."""
    path = tmp_path / "module.py"
    path.write_text(source, encoding="utf-8")
    return path


def refusal(path: Path, line: int, name: str) -> str:
    """The one refusal line the gate prints for ``name`` imported at ``line`` of ``path``."""
    return REFUSAL.format(path=path, line=line, name=name)


# --- behavior 1: the standard library, the package and a relative import pass ---


@pytest.mark.parametrize(
    "source",
    [
        STDLIB_IMPORT,
        STDLIB_FROM,
        SUBMODULE_OF_THE_STDLIB,
        SELF_IMPORT,
        SELF_IMPORT_PLAIN,
        RELATIVE_IMPORT,
    ],
)
def test_an_import_of_the_standard_library_or_the_package_itself_is_no_fault(
    tmp_path: Path, source: str
) -> None:
    assert GATE.foreign(written(tmp_path, source)) == []


# --- behavior 2: anything else is named, wherever the import sits ------------


def test_a_plain_third_party_import_is_refused_by_name_and_line(tmp_path: Path) -> None:
    path = written(tmp_path, THIRD_PARTY_IMPORT)
    assert GATE.foreign(path) == [refusal(path, 1, "pytest")]


def test_a_third_party_from_import_is_refused_by_the_module_it_reads_from(
    tmp_path: Path,
) -> None:
    path = written(tmp_path, THIRD_PARTY_FROM)
    assert GATE.foreign(path) == [refusal(path, 1, "pytest")]


def test_a_dotted_third_party_import_is_refused_under_its_root_name(
    tmp_path: Path,
) -> None:
    path = written(tmp_path, THIRD_PARTY_SUBMODULE)
    assert GATE.foreign(path) == [refusal(path, 1, "pytest")]


def test_two_foreign_names_on_one_line_are_both_refused_on_that_line(
    tmp_path: Path,
) -> None:
    path = written(tmp_path, TWO_FOREIGN_NAMES_ON_ONE_LINE)
    assert GATE.foreign(path) == [refusal(path, 1, "pytest"), refusal(path, 1, "yaml")]


def test_an_import_inside_a_function_is_refused_on_the_line_it_sits_on(
    tmp_path: Path,
) -> None:
    path = written(tmp_path, IMPORT_IN_A_FUNCTION)
    assert GATE.foreign(path) == [refusal(path, 2, "pytest")]


# --- behavior 3: the printed verdict over every file handed over --------------


def test_a_package_of_stdlib_imports_prints_the_clean_count_and_exits_clean(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = GATE.check([written(tmp_path, STDLIB_IMPORT)])
    assert (code, capsys.readouterr().out) == (0, ONE_CLEAN_FILE)


def test_one_third_party_import_prints_the_refusal_and_the_remedy(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = written(tmp_path, THIRD_PARTY_IMPORT)
    code = GATE.check([path])
    assert (code, capsys.readouterr().out) == (
        1,
        refusal(path, 1, "pytest") + "\n" + ONE_PROBLEM_REMEDY,
    )


# --- behavior 4: argv names the files, and its absence names the package -----


def test_main_refuses_the_file_argv_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = written(tmp_path, THIRD_PARTY_FROM)
    monkeypatch.setattr(sys, "argv", ["check_stdlib_only.py", str(path)])
    code = GATE.main()
    assert (code, capsys.readouterr().out) == (
        1,
        refusal(path, 1, "pytest") + "\n" + ONE_PROBLEM_REMEDY,
    )


def test_main_with_no_argv_refuses_a_package_file_it_found_itself(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / GATE.PACKAGE).mkdir()
    path = tmp_path / GATE.PACKAGE / "mod.py"
    path.write_text(THIRD_PARTY_IMPORT, encoding="utf-8")
    monkeypatch.setattr(GATE, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["check_stdlib_only.py"])
    code = GATE.main()
    assert (code, capsys.readouterr().out) == (
        1,
        refusal(path, 1, "pytest") + "\n" + ONE_PROBLEM_REMEDY,
    )
