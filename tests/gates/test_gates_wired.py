"""The wiring gate's two invariants over the duplication gate.

That gate is an ``npx`` invocation rather than a script under ``scripts/gates/``,
so a filename sweep cannot see it: it is named in the gate and required in both
configs. Its whole scope is a directory list in ``.jscpd.json``, and a directory
the tree does not track measures nothing.
"""

import json
from pathlib import Path

import check_gates_wired as GATE

INVOKES = "duplication:\n\tnpx jscpd\n"

COMMENTED = "duplication:\n\t# npx jscpd\n"

SILENT = "lint:\n\truff check triviajudge\n"

ONE_PATH = {"path": ["triviajudge"], "minTokens": 50}


def configured(tmp_path: Path, table: dict[str, object]) -> Path:
    """Put one duplication config in a throwaway tree that git tracks nothing in."""
    (tmp_path / GATE.CONFIG).write_text(json.dumps(table), encoding="utf-8")
    return tmp_path


# --- behavior 1: the invocation is required in both configs -----------------


def test_both_configs_invoking_the_duplication_gate_is_clean() -> None:
    assert GATE.duplication(INVOKES, INVOKES) == []


def test_a_makefile_that_never_invokes_it_is_named() -> None:
    assert len(GATE.duplication(SILENT, INVOKES)) == 1


def test_a_precommit_config_that_never_invokes_it_is_named() -> None:
    assert len(GATE.duplication(INVOKES, SILENT)) == 1


def test_a_commented_out_invocation_wires_nothing() -> None:
    assert len(GATE.duplication(COMMENTED, INVOKES)) == 1


# --- behavior 2: every configured path names a tracked directory ------------


def test_a_path_the_tree_tracks_nothing_under_is_named(tmp_path: Path) -> None:
    assert len(GATE.untracked(configured(tmp_path, ONE_PATH))) == 1


def test_this_tree_tracks_every_directory_the_duplication_gate_reads() -> None:
    assert GATE.untracked(GATE.ROOT) == []


def test_a_tracked_directory_is_listed_under_the_name_a_path_entry_spells() -> None:
    assert "triviajudge" in GATE.tracked_directories(GATE.ROOT)
