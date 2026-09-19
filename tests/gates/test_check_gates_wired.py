"""Behavior of the gate that holds every gate script to both wirings that run it.

Each case builds a tree of its own: a ``scripts/gates`` directory of named
scripts, a Makefile and a pre-commit config. Makefile wiring is mandatory;
pre-commit wiring is mandatory or carries a reason in the exemption table, and a
reason naming no script is itself a fault.

A refusal is matched on the exit code, and the counted faults on the script names
the case wrote into the two configs.
"""

from pathlib import Path

import check_gates_wired as GATE
import pytest

ONE = "check_one.py"
TWO = "check_two.py"
GHOST = "check_gone.py"

REASON = "too slow for the commit path"


def recipe(*names: str) -> str:
    """A Makefile target invoking each named script on a line of its own."""
    return "lint:\n" + "".join(f"\t.venv/bin/python scripts/gates/{name}\n" for name in names)


def hooks(*names: str) -> str:
    """A pre-commit config with one local hook per named script."""
    return "repos:\n" + "".join(f"  - id: {name}\n    entry: python scripts/gates/{name}\n" for name in names)


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
    return root


# --- behavior 1: a gate runs in the Makefile and in pre-commit, or says why not ---


@pytest.mark.parametrize(
    ("makefile", "precommit", "exempt", "code"),
    [
        (recipe(ONE, TWO), hooks(ONE, TWO), {}, 0),
        (recipe(ONE), hooks(ONE, TWO), {}, 1),
        (recipe(ONE, TWO), hooks(ONE), {}, 1),
        (recipe(ONE) + commented(TWO), hooks(ONE, TWO), {}, 1),
        (recipe(ONE, TWO), hooks(ONE) + commented(TWO), {}, 1),
        (recipe(ONE, TWO), hooks(ONE), {TWO: REASON}, 0),
        (recipe(ONE), hooks(ONE), {TWO: REASON}, 1),
        (recipe(ONE, TWO), hooks(ONE, TWO), {GHOST: REASON}, 1),
    ],
)
def test_a_gate_passes_only_when_both_wirings_run_it(
    tmp_path: Path, makefile: str, precommit: str, exempt: dict[str, str], code: int
) -> None:
    root = tree(tmp_path, [ONE, TWO], makefile, precommit)
    assert GATE.check(root, exempt) == code


# --- behavior 2: the gates are the scripts in the directory, sorted -----------


def test_the_gates_are_every_script_in_the_directory(tmp_path: Path) -> None:
    root = tree(tmp_path, [TWO, ONE], recipe(ONE, TWO), hooks(ONE, TWO))
    assert GATE.gate_scripts(root / "scripts" / "gates") == [ONE, TWO]


# --- behavior 3: an exemption naming no gate script is named ------------------


@pytest.mark.parametrize(("exempt", "faults"), [({}, []), ({TWO: REASON}, []), ({GHOST: REASON}, [GHOST])])
def test_an_exemption_stands_only_while_its_gate_does(exempt: dict[str, str], faults: list[str]) -> None:
    assert GATE.stale([ONE, TWO], exempt) == faults


# --- behavior 4: a comment wires nothing --------------------------------------


def test_a_script_named_only_in_a_comment_is_unwired() -> None:
    assert GATE.unwired(commented(TWO), [TWO]) == [TWO]


# --- behavior 5: this repository wires every gate it ships --------------------


def test_this_repository_wires_every_gate_of_its_own() -> None:
    assert GATE.main() == 0
