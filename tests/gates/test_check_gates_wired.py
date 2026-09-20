"""Behavior of the gate that holds every gate script to both wirings that run it.

Each case builds a tree of its own: a ``scripts/gates`` directory of named
scripts, a Makefile and a pre-commit config. Makefile wiring is mandatory;
pre-commit wiring is mandatory or carries a reason in the exemption table, and a
reason naming no script is itself a fault.

A case is judged on the exit code together with the finding lines the gate
prints, seeded below as constants: which script is unwired, which of the two
configs it is missing from, which exemption names no script, which config holds
no live invocation of the duplication gate, and which duplication path the tree
tracks nothing under.
"""

import json
import subprocess
from itertools import takewhile
from pathlib import Path

import check_gates_wired as GATE
import pytest

ONE = "check_one.py"
TWO = "check_two.py"
GHOST = "check_gone.py"

REASON = "too slow for the commit path"

NOWHERE = "nowhere"

#: A directory of the throwaway tree, holding files git is made to track.
SOMEWHERE = "scripts/gates"

#: The duplication gate's invocation, which no filename sweep can find.
JSCPD = "npx jscpd"

#: The Makefile recipe line invoking it, live, commented out, and absent.
INVOKES = f"duplication:\n\t{JSCPD}\n"
INVOKES_COMMENTED = f"duplication:\n\t# {JSCPD}\n"
SILENT = ""

#: The pre-commit hook invoking it, and the config that carries no such hook.
HOOK = f"  - id: jscpd\n    entry: {JSCPD}\n"
NO_HOOK = ""

#: Seconds a git call in a throwaway tree may take.
GIT_TIMEOUT = 30

#: The verdict a clean sweep prints, naming how many gate scripts it swept.
OK = "[ok] all {count} gate scripts are wired into the Makefile and pre-commit"

#: That verdict over a tree of two gate scripts, wired in both configs.
WIRED = OK.format(count=2)

NO_MAKEFILE_TARGET = f"scripts/gates/{TWO}: no Makefile target invokes it"
NOT_IN_PRECOMMIT = f"scripts/gates/{TWO}: not in .pre-commit-config.yaml and not exempt"
STALE_EXEMPTION = f"PRECOMMIT_EXEMPT['{GHOST}']: names no gate script"
UNTRACKED_PATH = f".jscpd.json: path '{NOWHERE}' names no directory the tree tracks"
MAKEFILE_WITHOUT_JSCPD = f"Makefile: no live line invokes `{JSCPD}`"
PRECOMMIT_WITHOUT_JSCPD = f".pre-commit-config.yaml: no live line invokes `{JSCPD}`"


def recipe(*names: str, duplication: str = INVOKES) -> str:
    """A Makefile target invoking each named script on a line of its own."""
    return duplication + "lint:\n" + "".join(f"\t.venv/bin/python scripts/gates/{name}\n" for name in names)


def hooks(*names: str, duplication: str = HOOK) -> str:
    """A pre-commit config with one local hook per named script."""
    return f"repos:\n{duplication}" + "".join(
        f"  - id: {name}\n    entry: python scripts/gates/{name}\n" for name in names
    )


def committed(root: Path) -> Path:
    """Put the written tree under git, so the files in it are files git tracks."""
    git = ["/usr/bin/env", "git"]
    subprocess.run([*git, "init", "-q"], cwd=root, check=True, capture_output=True, timeout=GIT_TIMEOUT)
    subprocess.run([*git, "add", "-A"], cwd=root, check=True, capture_output=True, timeout=GIT_TIMEOUT)
    return root


def commented(name: str) -> str:
    """A line naming a script that wires nothing, because it is a comment."""
    return f"  # python scripts/gates/{name}\n"


def tree(root: Path, gates: list[str], makefile: str, precommit: str) -> Path:
    """Write the gate scripts and the two configs that are supposed to run them."""
    directory = root / "scripts" / "gates"
    directory.mkdir(parents=True, exist_ok=True)
    for name in gates:
        (directory / name).write_text("", encoding="utf-8")
    (root / "Makefile").write_text(makefile, encoding="utf-8")
    (root / ".pre-commit-config.yaml").write_text(precommit, encoding="utf-8")
    (root / GATE.CONFIG).write_text(json.dumps({GATE.PATHS: []}), encoding="utf-8")
    return root


def verdict(root: Path, exempt: dict[str, str], capsys: pytest.CaptureFixture[str]) -> tuple[int, list[str]]:
    """The exit code and the lines the gate printed before its closing summary."""
    code = GATE.check(root, exempt)
    printed = capsys.readouterr().out.splitlines()
    return code, list(takewhile(bool, printed))


# --- behavior 1: a gate runs in the Makefile and in pre-commit, or says why not ---


def test_a_gate_in_both_wirings_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tree(tmp_path, [ONE, TWO], recipe(ONE, TWO), hooks(ONE, TWO))
    assert verdict(root, {}, capsys) == (0, [WIRED])


def test_a_gate_no_makefile_target_invokes_is_named(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tree(tmp_path, [ONE, TWO], recipe(ONE), hooks(ONE, TWO))
    assert verdict(root, {}, capsys) == (1, [NO_MAKEFILE_TARGET])


def test_a_gate_missing_from_precommit_is_named(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tree(tmp_path, [ONE, TWO], recipe(ONE, TWO), hooks(ONE))
    assert verdict(root, {}, capsys) == (1, [NOT_IN_PRECOMMIT])


def test_a_gate_commented_out_of_the_makefile_is_named(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tree(tmp_path, [ONE, TWO], recipe(ONE) + commented(TWO), hooks(ONE, TWO))
    assert verdict(root, {}, capsys) == (1, [NO_MAKEFILE_TARGET])


def test_a_gate_commented_out_of_precommit_is_named(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tree(tmp_path, [ONE, TWO], recipe(ONE, TWO), hooks(ONE) + commented(TWO))
    assert verdict(root, {}, capsys) == (1, [NOT_IN_PRECOMMIT])


def test_an_exempt_gate_may_stay_off_the_commit_path(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tree(tmp_path, [ONE, TWO], recipe(ONE, TWO), hooks(ONE))
    assert verdict(root, {TWO: REASON}, capsys) == (0, [WIRED])


def test_an_exemption_excuses_nothing_in_the_makefile(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tree(tmp_path, [ONE, TWO], recipe(ONE), hooks(ONE))
    assert verdict(root, {TWO: REASON}, capsys) == (1, [NO_MAKEFILE_TARGET])


def test_an_exemption_naming_no_gate_script_is_named(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tree(tmp_path, [ONE, TWO], recipe(ONE, TWO), hooks(ONE, TWO))
    assert verdict(root, {GHOST: REASON}, capsys) == (1, [STALE_EXEMPTION])


# --- behavior 2: the gates are the scripts in the directory, sorted -----------


def test_the_gates_are_every_script_in_the_directory(tmp_path: Path) -> None:
    root = tree(tmp_path, [TWO, ONE], recipe(ONE, TWO), hooks(ONE, TWO))
    assert GATE.gate_scripts(root / "scripts" / "gates") == [ONE, TWO]


# --- behavior 3: the duplication gate runs in both configs too ----------------


def test_a_makefile_that_never_invokes_the_duplication_gate_is_named(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tree(tmp_path, [ONE, TWO], recipe(ONE, TWO, duplication=SILENT), hooks(ONE, TWO))
    assert verdict(root, {}, capsys) == (1, [MAKEFILE_WITHOUT_JSCPD])


def test_a_precommit_config_that_never_invokes_the_duplication_gate_is_named(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tree(tmp_path, [ONE, TWO], recipe(ONE, TWO), hooks(ONE, TWO, duplication=NO_HOOK))
    assert verdict(root, {}, capsys) == (1, [PRECOMMIT_WITHOUT_JSCPD])


def test_a_commented_out_duplication_invocation_wires_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tree(tmp_path, [ONE, TWO], recipe(ONE, TWO, duplication=INVOKES_COMMENTED), hooks(ONE, TWO))
    assert verdict(root, {}, capsys) == (1, [MAKEFILE_WITHOUT_JSCPD])


# --- behavior 4: the duplication gate reads directories the tree tracks -------


def test_a_duplication_path_the_tree_tracks_nothing_under_is_named(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tree(tmp_path, [ONE, TWO], recipe(ONE, TWO), hooks(ONE, TWO))
    (root / GATE.CONFIG).write_text(json.dumps({GATE.PATHS: [NOWHERE]}), encoding="utf-8")
    assert verdict(root, {}, capsys) == (1, [UNTRACKED_PATH])


def test_a_duplication_path_the_tree_tracks_a_file_under_is_clean(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tree(tmp_path, [ONE, TWO], recipe(ONE, TWO), hooks(ONE, TWO))
    (root / GATE.CONFIG).write_text(json.dumps({GATE.PATHS: [SOMEWHERE]}), encoding="utf-8")
    assert verdict(committed(root), {}, capsys) == (0, [WIRED])


# --- behavior 5: this repository wires every gate it ships --------------------


def test_this_repository_wires_every_gate_of_its_own(capsys: pytest.CaptureFixture[str]) -> None:
    shipped = GATE.gate_scripts(GATE.ROOT / "scripts" / "gates")
    code = GATE.main()
    assert (code, capsys.readouterr().out.splitlines()) == (0, [OK.format(count=len(shipped))])
