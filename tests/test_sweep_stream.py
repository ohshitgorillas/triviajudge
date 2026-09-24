"""What a stopped sweep leaves behind, batch by batch.

Each case spawns ``python -m triviajudge.sweep`` over a real checkout of three
one-line markdown files, one call per file, and stops it on a chosen call: the
fake ``claude`` sends the sweep a signal, answers with a bare list in place of
the envelope, or answers every call. What is read back is the journal, the
baseline, stdout and the ``--out`` file.

Every phrase a judge would rule on lives in a string literal, never in a
comment or docstring of this file.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import coverage_environment

from triviajudge.core import Line, digest

REPO_ROOT = Path(__file__).resolve().parents[1]

GIT = shutil.which("git")

#: The three tracked files, one prose line each, so ``--batch 1`` is one call per file.
STREAM_FILES = {
    "a.md": "the panel holds the staged rate\n",
    "b.md": "the lane returns the staged model\n",
    "c.md": "the resampler runs at the rate the panel asks for\n",
}

A_LINE = Line("a.md", 1, "the panel holds the staged rate")
B_LINE = Line("b.md", 1, "the lane returns the staged model")
C_LINE = Line("c.md", 1, "the resampler runs at the rate the panel asks for")

#: A ``claude`` that decides nothing: it looks up the id its body carries in the
#: table beside it and does what the table says for that id, which is either a
#: verdict word to answer with, a bare ``[]`` in place of the envelope, or a
#: signal to send its parent, the sweep.
TABLE_JUDGE = r"""
import json
import os
import re
import signal
import sys
from pathlib import Path

table = json.loads(
    (Path(__file__).resolve().parent / "table.json").read_text(encoding="utf-8")
)
body = " ".join(sys.argv[1:])
if not os.isatty(0):
    body += sys.stdin.read()
carried = [one for one in table if re.search(re.escape(one) + r"\D", body + " ")]
action = table[carried[0]] if carried else ""
if action in ("SIGKILL", "SIGTERM", "SIGINT"):
    os.kill(os.getppid(), getattr(signal, action))
    sys.exit(1)
if action == "bare":
    print("[]")
elif carried:
    reply = [{"id": carried[0], "verdict": action, "reason": "r"}]
    print(json.dumps({"result": json.dumps(reply)}))
else:
    print(json.dumps({"result": "[]"}))
"""


def table(word: str, stop: dict[str, str]) -> dict[str, str]:
    """Every line answered with ``word``, except the rows ``stop`` names."""
    return {
        **{line.id: word for line in (A_LINE, B_LINE, C_LINE)},
        **stop,
    }


def stream_environment(bin_dir: Path, home: Path) -> dict[str, str]:
    """An environment built from nothing: the test-built PATH, an empty HOME, no git config."""
    return {
        **coverage_environment(),
        "PATH": str(bin_dir),
        "HOME": str(home),
        "LC_ALL": "C",
        "PYTHONPATH": str(REPO_ROOT),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_CEILING_DIRECTORIES": str(bin_dir.parent),
        "GIT_AUTHOR_NAME": "sweep probe",
        "GIT_AUTHOR_EMAIL": "sweep@example.invalid",
        "GIT_COMMITTER_NAME": "sweep probe",
        "GIT_COMMITTER_EMAIL": "sweep@example.invalid",
    }


def swept(tmp_path: Path, answers: dict[str, str], flags: list[str]) -> Path:
    """Run one spawned sweep over the three-file checkout; return the checkout.

    Its stdout and stderr land in ``stdout.txt`` and ``stderr.txt`` under ``tmp_path``.
    """
    if GIT is None:
        raise RuntimeError("git is not on PATH, so no checkout can be built")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "git").symlink_to(GIT)
    judge = bin_dir / "claude"
    judge.write_text(f"#!{sys.executable}\n{TABLE_JUDGE}", encoding="utf-8")
    judge.chmod(0o755)
    (bin_dir / "table.json").write_text(json.dumps(answers), encoding="utf-8")
    home = tmp_path / "home"
    home.mkdir()
    env = stream_environment(bin_dir, home)
    root = tmp_path / "repo"
    root.mkdir()
    for rel, text in STREAM_FILES.items():
        (root / rel).write_text(text, encoding="utf-8")
    for args in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "tracked"]):
        subprocess.run([GIT, *args], cwd=root, env=env, check=True, capture_output=True)
    with (
        (tmp_path / "stdout.txt").open("w", encoding="utf-8") as out,
        (tmp_path / "stderr.txt").open("w", encoding="utf-8") as err,
    ):
        subprocess.run(
            [
                sys.executable,
                "-m",
                "triviajudge.sweep",
                "--md",
                "--yes",
                "--batch",
                "1",
                "--parallel",
                "1",
                *flags,
            ],
            cwd=root,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=err,
            check=False,
            timeout=120,
        )
    return root


def journal_paths(root: Path) -> list[object]:
    """The ``paths`` value of each JSON line of the sweep journal, ``[]`` where none exists."""
    journal = root / ".triviajudge" / "sweep-journal.jsonl"
    if not journal.exists():
        return []
    return [
        json.loads(line)["paths"]
        for line in journal.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def baseline_digests(root: Path) -> list[str]:
    """The sorted digests of ``sweep-clean.json``, ``[]`` where none exists."""
    cache = root / ".triviajudge" / "sweep-clean.json"
    if not cache.exists():
        return []
    return sorted(json.loads(cache.read_text(encoding="utf-8")))


def stdout_ids(tmp_path: Path) -> list[str]:
    """The seeded ids that open a line of the sweep's stdout, in the order printed."""
    printed = (tmp_path / "stdout.txt").read_text(encoding="utf-8").splitlines()
    ids = [line.id for line in (A_LINE, B_LINE, C_LINE)]
    return [one for row in printed for one in ids if row.startswith(one)]


def out_file_ids(path: Path) -> list[str]:
    """The ``id`` of each entry under ``flags`` in the ``--out`` file, ``[]`` where none exists."""
    if not path.exists():
        return []
    return [
        flag["id"] for flag in json.loads(path.read_text(encoding="utf-8"))["flags"]
    ]


STOP_ROWS_IDS = ["killed on the b call", "killed on the c call", "every call answered"]


@pytest.mark.parametrize(
    ("stop", "paths"),
    [
        ({"b.md:1": "SIGKILL"}, [["a.md"]]),
        ({"c.md:1": "SIGKILL"}, [["a.md"], ["b.md"]]),
        ({}, [["a.md"], ["b.md"], ["c.md"]]),
    ],
    ids=STOP_ROWS_IDS,
)
def test_the_journal_holds_each_batch_that_answered_before_the_sweep_was_killed(
    tmp_path: Path, stop: dict[str, str], paths: list[list[str]]
) -> None:
    root = swept(tmp_path, table("trivia", stop), [])
    assert journal_paths(root) == paths


@pytest.mark.parametrize(
    ("stop", "digests"),
    [
        ({"b.md:1": "SIGKILL"}, [digest(A_LINE)]),
        ({"c.md:1": "SIGKILL"}, sorted([digest(A_LINE), digest(B_LINE)])),
        ({}, sorted([digest(A_LINE), digest(B_LINE), digest(C_LINE)])),
    ],
    ids=STOP_ROWS_IDS,
)
def test_the_baseline_keeps_each_passed_batch_that_answered_before_the_sweep_was_killed(
    tmp_path: Path, stop: dict[str, str], digests: list[str]
) -> None:
    root = swept(tmp_path, table("ok", stop), ["--baseline"])
    assert baseline_digests(root) == digests


@pytest.mark.parametrize(
    ("stop", "ids"),
    [
        ({"b.md:1": "SIGKILL"}, ["a.md:1"]),
        ({"c.md:1": "SIGKILL"}, ["a.md:1", "b.md:1"]),
        ({}, ["a.md:1", "b.md:1", "c.md:1"]),
    ],
    ids=STOP_ROWS_IDS,
)
def test_stdout_holds_each_flag_that_landed_before_the_sweep_was_killed(
    tmp_path: Path, stop: dict[str, str], ids: list[str]
) -> None:
    swept(tmp_path, table("trivia", stop), [])
    assert stdout_ids(tmp_path) == ids


@pytest.mark.parametrize(
    ("stop", "ids"),
    [
        ({"b.md:1": "SIGINT"}, ["a.md:1"]),
        ({"c.md:1": "SIGINT"}, ["a.md:1", "b.md:1"]),
        ({"b.md:1": "SIGTERM"}, ["a.md:1"]),
        ({"c.md:1": "SIGTERM"}, ["a.md:1", "b.md:1"]),
        ({"c.md:1": "bare"}, ["a.md:1", "b.md:1"]),
        ({}, ["a.md:1", "b.md:1", "c.md:1"]),
    ],
    ids=[
        "interrupted on the b call",
        "interrupted on the c call",
        "terminated on the b call",
        "terminated on the c call",
        "bare list on the c call",
        "every call answered",
    ],
)
def test_the_out_file_holds_each_flag_that_landed_before_the_sweep_stopped(
    tmp_path: Path, stop: dict[str, str], ids: list[str]
) -> None:
    out = tmp_path / "out.json"
    swept(tmp_path, table("trivia", stop), ["--out", str(out)])
    assert out_file_ids(out) == ids
