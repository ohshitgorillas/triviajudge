"""The trivia judge over Python comments and docstrings.

``triviajudge.comment_trivia`` reads the added lines of a Python file, turns
them into candidates for the judge, screens the candidates the regex gate
already answers for, and only then spends a judge call on what is left. A ``#``
comment is one candidate per line; a docstring is one candidate per block, so
the judge reads the block the way a person does.

Three seams are exercised here: ``candidates(path, text, added)``,
``screen(cands)``, and the module's exit code, driven the way a hook or a commit
drives it. Every phrase fed to the gate lives in a Python string literal, never
in a comment or docstring of this file, so this file is clean by the rule it
pins.

Cases identify a candidate by the markers this module planted in the source it
handed over, never by wording the gate composes: a block candidate carries all
three of its block's markers, a per-line candidate carries one.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from conftest import coverage_environment

from triviajudge import comment_trivia as GATE
from triviajudge.archaeology import PRAGMA

REPO_ROOT = Path(__file__).resolve().parents[1]

GIT = shutil.which("git")

SAMPLE_PATH = "src/sample.py"

CANDIDATES = GATE.candidates
SCREEN = GATE.screen


#: Markers planted in the sample sources, in the order a projection reports them.
MARKERS = (
    "ALPHA",
    "BRAVO",
    "CHARLIE",
    "CLEANBLOCK",
    "DATEDLINE",
    "DELTA",
    "ECHO",
    "FOXTROT",
    "GOLF",
    "HOTEL",
    "PRAGMABLOCK",
)

ONE_COMMENT_ONE_DOCSTRING = (
    '"""ALPHA the panel model\n'
    "BRAVO the staged config\n"
    'CHARLIE the lane result"""\n'
    "\n"
    "value = 1  # DELTA keep in sync with the schema\n"
)

TWO_COMMENTS_TWO_DOCSTRINGS = ONE_COMMENT_ONE_DOCSTRING + (
    "\n"
    "\n"
    "def helper() -> int:\n"
    '    """ECHO the second block\n'
    "    FOXTROT the staged config\n"
    '    GOLF the lane result"""\n'
    "    return value  # HOTEL the caller wants an int\n"
)

A_REASON = "history-ok: the wire format pins this and the daemon rejects anything else"

DATED_AND_PRAGMA_AND_CLEAN = (
    '"""PRAGMABLOCK the panel model\n'
    "added 2025-11-04 for the resampler panel\n"
    f'{A_REASON}"""\n'
    "\n"
    "value = 1  # DATEDLINE added 2025-11-04 for the resampler panel\n"
    "\n"
    "\n"
    "def helper() -> int:\n"
    '    """CLEANBLOCK the panel model\n'
    "    reads the staged config and hands back the panel model\n"
    '    keep in sync with the schema"""\n'
    "    return value\n"
)

EVERY_CANDIDATE_DATED = (
    '"""INDIA the panel model added 2025-11-04\n'
    "JULIET the staged config\n"
    'KILO the lane result"""\n'
    "\n"
    "value = 1  # LIMA added 2025-11-04 for the resampler panel\n"
)

ONE_CLEAN_COMMENT = "value = 1  # MIKE keep in sync with the schema\n"


def markers_in(text: str) -> tuple[str, ...]:
    """The markers this module planted that ``text`` carries, in ``MARKERS`` order."""
    return tuple(marker for marker in MARKERS if marker in text)


def shape_of(cands: list[Any]) -> list[tuple[str, ...]]:
    """One marker tuple per candidate, sorted, so grouping shows and order does not."""
    return sorted(markers_in(cand.text) for cand in cands)


def every_line_of(text: str) -> set[int]:
    """The line numbers of ``text``, the added set of a file that is entirely new."""
    return set(range(1, len(text.splitlines()) + 1))


def shape_of_candidates(source: str) -> list[tuple[str, ...]]:
    """The marker shape of the candidates the gate pulls out of an all-added file."""
    return shape_of(list(CANDIDATES(SAMPLE_PATH, source, every_line_of(source))))


def kept_shape(source: str) -> list[tuple[str, ...]]:
    """The marker shape of the candidates the screen leaves for the judge."""
    kept, _complaints = SCREEN(
        list(CANDIDATES(SAMPLE_PATH, source, every_line_of(source)))
    )
    return shape_of(list(kept))


def child_environment(tmp_path: Path) -> dict[str, str]:
    """An environment whose PATH carries git and nothing else, so ``claude`` is missing."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    link = bin_dir / "git"
    if not link.exists():
        link.symlink_to(str(GIT))
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return {
        **coverage_environment(),
        "PATH": str(bin_dir),
        "HOME": str(home),
        "LC_ALL": "C",
        "PYTHONPATH": str(REPO_ROOT),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_AUTHOR_NAME": "comment trivia probe",
        "GIT_AUTHOR_EMAIL": "probe@example.invalid",
        "GIT_COMMITTER_NAME": "comment trivia probe",
        "GIT_COMMITTER_EMAIL": "probe@example.invalid",
    }


def git_init(root: Path, env: dict[str, str]) -> None:
    """Make ``root`` a repository, with git resolved from the environment's own PATH."""
    subprocess.run(
        ["/usr/bin/env", "git", "init", "-q"],
        cwd=root,
        env=env,
        check=True,
        capture_output=True,
    )


def git_add_all(root: Path, env: dict[str, str]) -> None:
    """Stage everything sitting in ``root``."""
    subprocess.run(
        ["/usr/bin/env", "git", "add", "-A"],
        cwd=root,
        env=env,
        check=True,
        capture_output=True,
    )


def git_commit(root: Path, env: dict[str, str]) -> None:
    """Turn what is staged into the checkout's one commit, so a diff has a HEAD to read."""
    subprocess.run(
        ["/usr/bin/env", "git", "commit", "-qm", "baseline"],
        cwd=root,
        env=env,
        check=True,
        capture_output=True,
    )


def repo_with_staged(tmp_path: Path, source: str) -> tuple[Path, dict[str, str]]:
    """A throwaway checkout, a different work tree from the package's own, with one staged file."""
    if GIT is None:
        pytest.skip(
            "git is not on PATH, so no staged file can be presented to the gate"
        )
    env = child_environment(tmp_path)
    root = tmp_path / "repo"
    root.mkdir()
    git_init(root, env)
    (root / "baseline.txt").write_text("baseline\n", encoding="utf-8")
    git_add_all(root, env)
    git_commit(root, env)
    staged = root / SAMPLE_PATH
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_text(source, encoding="utf-8")
    git_add_all(root, env)
    return root, env


def gate_exit_code(tmp_path: Path, source: str, flags: list[str]) -> int:
    """The gate's exit code over a checkout whose one staged file carries ``source``."""
    root, env = repo_with_staged(tmp_path, source)
    finished = subprocess.run(
        [sys.executable, "-m", "triviajudge.comment_trivia", *flags],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        input="{}" if "--stop" in flags else None,
    )
    return finished.returncode


# --- behavior 1: a docstring block is one candidate, a comment line is one ----


@pytest.mark.parametrize(
    ("source", "shape"),
    [
        (
            ONE_COMMENT_ONE_DOCSTRING,
            [("ALPHA", "BRAVO", "CHARLIE"), ("DELTA",)],
        ),
        (
            TWO_COMMENTS_TWO_DOCSTRINGS,
            [
                ("ALPHA", "BRAVO", "CHARLIE"),
                ("DELTA",),
                ("ECHO", "FOXTROT", "GOLF"),
                ("HOTEL",),
            ],
        ),
    ],
)
def test_each_docstring_arrives_as_one_candidate_beside_one_per_comment_line(
    source: str, shape: list[tuple[str, ...]]
) -> None:
    assert shape_of_candidates(source) == shape


# --- behavior 2: the regex screen answers first, the judge sees the rest ------


def test_the_screen_leaves_the_judge_only_the_block_no_pattern_answered_for() -> None:
    assert kept_shape(DATED_AND_PRAGMA_AND_CLEAN) == [("CLEANBLOCK",)]


# --- behavior 3: the judge runs on the commit path, never in the Stop hook ----


@pytest.mark.parametrize(
    ("source", "flags", "code"),
    [
        (EVERY_CANDIDATE_DATED, [], 0),
        (ONE_CLEAN_COMMENT, [], 1),
        (ONE_CLEAN_COMMENT, ["--stop"], 0),
    ],
)
def test_the_exit_code_over_a_staged_file_with_no_judge_binary_on_path(
    tmp_path: Path, source: str, flags: list[str], code: int
) -> None:
    assert gate_exit_code(tmp_path, source, flags) == code


# --- behavior 4: a suffix that is not Python is read as block comments --------


JS_SOURCE = "/* NOVEMBER the panel model */\nvalue = 1;  // OSCAR the lane result\n"

BROKEN_PYTHON = "def helper(\n"

BARE_PRAGMA_COMMENT = f"value = 1  # PAPA {PRAGMA}\n"

MARKDOWN_DIFF = "diff --git a/notes.md b/notes.md\n--- a/notes.md\n+++ b/notes.md\n@@ -0,0 +1 @@\n+the panel holds the rate\n"

PYTHON_DIFF = (
    "diff --git a/src/sample.py b/src/sample.py\n"
    "--- a/src/sample.py\n"
    "+++ b/src/sample.py\n"
    "@@ -0,0 +1 @@\n"
    "+value = 1  # QUEBEC the lane result\n"
)


def test_a_javascript_comment_arrives_as_a_candidate() -> None:
    cands = CANDIDATES("src/sample.js", JS_SOURCE, every_line_of(JS_SOURCE))
    assert [cand.number for cand in cands] == [1, 2]


def test_a_file_that_does_not_parse_is_named_and_costs_the_run_nothing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    GATE.parsed(SAMPLE_PATH, BROKEN_PYTHON, every_line_of(BROKEN_PYTHON))
    assert SAMPLE_PATH in capsys.readouterr().err


def test_a_pragma_with_no_reason_is_refused_by_the_screen() -> None:
    _kept, complaints = SCREEN(
        list(
            CANDIDATES(
                SAMPLE_PATH, BARE_PRAGMA_COMMENT, every_line_of(BARE_PRAGMA_COMMENT)
            )
        )
    )
    assert "needs a reason" in complaints[0]


# --- behavior 5: only the files this gate reads reach the judge ---------------


def test_a_path_outside_the_suffixes_is_not_read_out_of_a_diff() -> None:
    assert GATE.added_by_path(MARKDOWN_DIFF) == {}


def test_a_revision_that_does_not_carry_the_file_reads_as_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(*_args: str) -> str:
        raise subprocess.CalledProcessError(1, "git")

    monkeypatch.setattr("triviajudge.comment_trivia.git", refuse)
    assert GATE.blob("HEAD", SAMPLE_PATH) == ""


# --- behavior 6: each input mode reads the lines it names --------------------


def namespace(**overrides: object) -> argparse.Namespace:
    """The arguments a gate run carries, with every mode the flags leave alone switched off."""
    args: dict[str, object] = {"stop": False, "lines": None, "head": False, "files": []}
    return argparse.Namespace(**{**args, **overrides})


def test_the_records_mode_judges_the_lines_the_file_addresses(tmp_path: Path) -> None:
    records = tmp_path / "lines.tsv"
    records.write_text(f"{SAMPLE_PATH}:1\tROMEO the lane result\n", encoding="utf-8")
    kept, _complaints = GATE.collect(namespace(lines=str(records)))
    assert [cand.id for cand in kept] == [f"{SAMPLE_PATH}:1"]


def test_the_head_mode_judges_what_the_last_commit_added(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "triviajudge.comment_trivia.git_diff", lambda *_args: PYTHON_DIFF
    )
    monkeypatch.setattr(
        "triviajudge.comment_trivia.blob",
        lambda _rev, _path: "value = 1  # QUEBEC the lane result\n",
    )
    kept, _complaints = GATE.collect(namespace(head=True))
    assert [cand.id for cand in kept] == [f"{SAMPLE_PATH}:1"]


def test_a_commit_naming_only_files_this_gate_skips_judges_nothing() -> None:
    assert GATE.collect(namespace(files=["notes.md"])) == ([], [])


def test_the_working_tree_mode_reads_an_untracked_file_whole(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / SAMPLE_PATH
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("value = 1  # SIERRA the lane result\n", encoding="utf-8")
    monkeypatch.setattr("triviajudge.comment_trivia.git_diff", lambda *_args: "")
    monkeypatch.setattr("triviajudge.comment_trivia.git", lambda *_args: SAMPLE_PATH)
    monkeypatch.setattr("triviajudge.comment_trivia.root", lambda: tmp_path)
    assert [cand.id for cand in GATE.worktree_candidates()] == [f"{SAMPLE_PATH}:1"]
