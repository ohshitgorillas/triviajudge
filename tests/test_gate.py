"""The gate's judging pass: how many lines one judge call carries.

``triviajudge.gate.verdicts`` stands between a gate's candidate lines and the
judge. A call that carries every candidate at once is the shape the owner asked
to be rid of, so what is pinned here is that the ``batch`` the caller names
decides how the lines are split, and that the flags coming back are the ones the
judge answered each chunk with.

The judge is the real seam: a ``claude`` executable on a ``PATH`` this file
builds, answering one print-mode envelope per row of a table written beside it
and keyed by the ids the body it received carries. No row matches a body the
table does not name, and such a body is answered with no flags at all. Each
call appends the ids its body carried to a log beside that table, so a case can
read back what was asked and in what order.

Under ``exhaustive`` the judge answers one object per id it was asked about,
carrying the verdict it reached for that id, so what is pinned there is which
of those ids come back flagged, and that an id the answer skipped is asked once
more and then flagged rather than passed.

Every phrase a judge would rule on lives in a string literal, never in a comment
or docstring of this file.
"""

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from triviajudge import core, gate
from triviajudge.core import Line

GIT = shutil.which("git")

LINES = [Line("a.md", number, f"line {number}") for number in range(1, 46)]

#: A ``claude`` answering from the table beside it, keyed by which ids the body carries.
FAKE_JUDGE = '''#!{interpreter}
"""A judge that reads no prose: it answers the row its input's id set names, or nothing."""

import json
import os
import re
import sys
from pathlib import Path

table = json.loads((Path(__file__).resolve().parent / "table.json").read_text(encoding="utf-8"))
body = " ".join(sys.argv[1:])
if not os.isatty(0):
    body += sys.stdin.read()
carried = [one for one in table["universe"] if re.search(re.escape(one) + r"(?![0-9])", body)]
with (Path(__file__).resolve().parent / "calls.jsonl").open("a", encoding="utf-8") as log:
    log.write(json.dumps(carried) + "\\n")
rows = [row["answer"] for row in table["rows"] if row["ids"] == carried]
print(json.dumps({{"result": json.dumps(rows[0] if rows else [])}}))
'''


def row(first: int, last: int, flagged: int) -> dict[str, object]:
    """One table row: the ids a body carries, and the single flag the judge answers it with."""
    return {
        "ids": [f"a.md:{number}" for number in range(first, last + 1)],
        "answer": [{"id": f"a.md:{flagged}", "reason": "the rate the panel asks for"}],
    }


#: Six bodies the judge knows: the three chunks of 20 and the three chunks of 15.
TABLE: dict[str, object] = {
    "universe": [line.id for line in LINES],
    "rows": [
        row(1, 20, 1),
        row(21, 40, 21),
        row(41, 45, 41),
        row(1, 15, 1),
        row(16, 30, 16),
        row(31, 45, 31),
    ],
}


def built_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A directory holding git and the fake judge, made the whole of ``PATH`` beside an empty HOME."""
    if GIT is None:
        raise RuntimeError("git is not on PATH, so no checkout can be built")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "git").symlink_to(GIT)
    (bin_dir / "table.json").write_text(json.dumps(TABLE), encoding="utf-8")
    judge = bin_dir / "claude"
    judge.write_text(FAKE_JUDGE.format(interpreter=sys.executable), encoding="utf-8")
    judge.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    built = {
        "PATH": str(bin_dir),
        "HOME": str(home),
        "LC_ALL": "C",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_CEILING_DIRECTORIES": str(tmp_path),
        "GIT_AUTHOR_NAME": "gate probe",
        "GIT_AUTHOR_EMAIL": "gate@example.invalid",
        "GIT_COMMITTER_NAME": "gate probe",
        "GIT_COMMITTER_EMAIL": "gate@example.invalid",
    }
    for name, value in built.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("INNER", raising=False)
    return bin_dir


def committed_tree(root: Path) -> Path:
    """A real checkout under ``root``, tracking one file in one commit."""
    if GIT is None:
        raise RuntimeError("git is not on PATH, so no checkout can be built")
    root.mkdir()
    (root / "a.md").write_text("the panel holds the staged rate\n", encoding="utf-8")
    for command in (("init", "-q"), ("add", "-A"), ("commit", "-qm", "tracked")):
        subprocess.run([GIT, *command], cwd=root, check=True, capture_output=True)
    return root


@pytest.fixture
def checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A checkout the gate runs in, with the judge on its PATH and the cached root forgotten."""
    built_path(tmp_path, monkeypatch)
    core.root.cache_clear()
    root = committed_tree(tmp_path / "repo")
    monkeypatch.chdir(root)
    yield root
    core.root.cache_clear()


@pytest.fixture
def bin_dir(checkout: Path) -> Path:
    """The directory the judge, its table and its call log sit in, beside the checkout."""
    return checkout.parent / "bin"


FOUR = LINES[:4]

THREE_IDS = [line.id for line in LINES[:3]]

FOUR_IDS = [line.id for line in FOUR]


def verdict(number: int, word: str) -> dict[str, str]:
    """One object of an exhaustive answer: the id judged, the verdict it got, the reason."""
    return {
        "id": f"a.md:{number}",
        "verdict": word,
        "reason": "the rate the panel asks for",
    }


def answered(bin_dir: Path, rows: list[dict[str, object]]) -> None:
    """Replace the judge's table with the rows one case wants, over the same id universe."""
    table = {"universe": [line.id for line in LINES], "rows": rows}
    (bin_dir / "table.json").write_text(json.dumps(table), encoding="utf-8")


def bodies(bin_dir: Path) -> list[list[str]]:
    """The ids each body the judge received carried, in the order the calls arrived."""
    log = (bin_dir / "calls.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in log.splitlines()]


def judged(lines: list[Line]) -> list[dict[str, str]]:
    """One exhaustive pass over ``lines``, unbatched and one call at a time."""
    return gate.verdicts(
        lines,
        "prompt",
        exhaustive=True,
        batch=0,
        parallel=1,
        model="a-model",
        timeout=30,
    )


# --- behavior 1: the batch size decides how many lines one judge call carries ---


@pytest.mark.parametrize(
    ("size", "flagged"),
    [
        (20, ["a.md:1", "a.md:21", "a.md:41"]),
        (15, ["a.md:1", "a.md:16", "a.md:31"]),
    ],
    ids=["twenty lines to a call", "fifteen lines to a call"],
)
@pytest.mark.usefixtures("checkout")
def test_the_lines_reach_the_judge_in_chunks_of_the_batch_size_the_caller_named(size: int, flagged: list[str]) -> None:
    flags = gate.verdicts(
        LINES,
        "prompt",
        exhaustive=False,
        batch=size,
        parallel=1,
        model="a-model",
        timeout=30,
    )
    assert [flag["id"] for flag in flags] == flagged


# --- behavior 2: an exhaustive answer flags the ids it called trivia, and no others ---


@pytest.mark.parametrize(
    ("words", "flagged"),
    [
        (("clean", "trivia", "clean"), ["a.md:2"]),
        (("trivia", "clean", "trivia"), ["a.md:1", "a.md:3"]),
    ],
    ids=["the middle line alone is trivia", "the outer two lines are trivia"],
)
def test_the_ids_the_exhaustive_answer_called_trivia_are_the_ids_that_come_back_flagged(
    bin_dir: Path, words: tuple[str, str, str], flagged: list[str]
) -> None:
    answered(
        bin_dir,
        [
            {
                "ids": THREE_IDS,
                "answer": [verdict(number, word) for number, word in enumerate(words, 1)],
            }
        ],
    )
    assert [flag["id"] for flag in judged(LINES[:3])] == flagged


# --- behavior 3: an id no answer ever judged is flagged, never passed --------


@pytest.mark.parametrize(
    ("second", "flagged"),
    [
        ([verdict(3, "trivia"), verdict(4, "clean")], ["a.md:2", "a.md:3"]),
        ([], ["a.md:2", "a.md:3", "a.md:4"]),
    ],
    ids=[
        "the second answer judges both stragglers",
        "the second answer judges neither",
    ],
)
def test_an_id_the_judge_never_ruled_on_comes_back_flagged(
    bin_dir: Path, second: list[dict[str, str]], flagged: list[str]
) -> None:
    answered(
        bin_dir,
        [
            {"ids": FOUR_IDS, "answer": [verdict(1, "clean"), verdict(2, "trivia")]},
            {"ids": ["a.md:3", "a.md:4"], "answer": second},
        ],
    )
    assert [flag["id"] for flag in judged(FOUR)] == flagged


# --- behavior 4: the ids an answer skipped are asked once more, and no further ---


@pytest.mark.parametrize(
    ("first", "asked"),
    [
        (
            [verdict(1, "clean"), verdict(2, "trivia")],
            [["a.md:1", "a.md:2", "a.md:3", "a.md:4"], ["a.md:3", "a.md:4"]],
        ),
        (
            [verdict(1, "clean"), verdict(2, "trivia"), verdict(3, "clean")],
            [["a.md:1", "a.md:2", "a.md:3", "a.md:4"], ["a.md:4"]],
        ),
    ],
    ids=["two of the four are judged", "three of the four are judged"],
)
def test_the_second_call_carries_the_ids_the_first_answer_skipped_and_the_calls_stop_there(
    bin_dir: Path, first: list[dict[str, str]], asked: list[list[str]]
) -> None:
    answered(bin_dir, [{"ids": FOUR_IDS, "answer": first}])
    judged(FOUR)
    assert bodies(bin_dir) == asked
