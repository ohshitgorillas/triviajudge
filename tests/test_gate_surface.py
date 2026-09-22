"""The gate driver's three entry points, each driven in process over a judge that answers a table.

``gate.run`` is asked for the exit code the comment gate reaches when its
collect finds nothing staged, from a directory inside a work tree and from one
inside none. ``gate.judged`` is asked what it leaves behind after the markdown
gate has ruled on two lines: the ids at the path ``--out`` names, and the
digests in the cache file. ``gate.verdicts`` is asked how many judge calls an
empty line list costs.

The judge is a ``claude`` executable on a ``PATH`` this file builds. It reads
no prose: it prints the reply a table beside it stores for the id set its body
carries, and appends that id set to a log, so a case reads back what was asked.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from triviajudge import comment_trivia, core, gate, md_trivia
from triviajudge.core import Line

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

GIT = shutil.which("git")

#: A judge answering the one reply its table stores for the ids its body carries.
FAKE_JUDGE = '''#!{interpreter}
"""A judge that decides nothing: it prints the stored reply for the ids it was handed."""

import json
import os
import re
import sys
from pathlib import Path

beside = Path(__file__).resolve().parent
plan = json.loads((beside / "answers.json").read_text(encoding="utf-8"))
body = " ".join(sys.argv[1:])
if not os.isatty(0):
    body += sys.stdin.read()
carried = [one for one in plan["ids"] if re.search(re.escape(one) + r"\\D", body + " ")]
with (beside / "calls.jsonl").open("a", encoding="utf-8") as log:
    log.write(json.dumps(carried) + "\\n")
replies = [row["reply"] for row in plan["rows"] if row["carries"] == carried]
print(json.dumps({{"result": json.dumps(replies[0] if replies else [])}}))
'''

TWO_LINES = [Line("a.md", 1, "line one text"), Line("a.md", 2, "line two text")]

TWO_IDS = [line.id for line in TWO_LINES]

#: ``sha1`` of the first line's text, and of the second's.
FIRST_DIGEST = "ea665d3b89412af71b8db778845534c22807fb97"
SECOND_DIGEST = "b471c332584ed6c40e540677f12f3f33ffda133a"


def built_bin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A directory holding git and the judge, made the whole of ``PATH`` beside an empty HOME."""
    if GIT is None:
        raise RuntimeError("git is not on PATH, so no checkout can be built")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "git").symlink_to(GIT)
    judge = bin_dir / "claude"
    judge.write_text(FAKE_JUDGE.format(interpreter=sys.executable), encoding="utf-8")
    judge.chmod(0o755)
    planned(bin_dir, [])
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
        "GIT_AUTHOR_EMAIL": "probe@example.invalid",
        "GIT_COMMITTER_NAME": "gate probe",
        "GIT_COMMITTER_EMAIL": "probe@example.invalid",
    }
    for name, value in built.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("INNER", raising=False)
    return bin_dir


def planned(bin_dir: Path, rows: list[dict[str, object]]) -> None:
    """Store the replies the judge answers with, over the id universe these cases use."""
    plan = {"ids": TWO_IDS, "rows": rows}
    (bin_dir / "answers.json").write_text(json.dumps(plan), encoding="utf-8")


def verdict(number: int, word: str) -> dict[str, str]:
    """One object of the judge's answer: the id ruled on, the word it got, a reason."""
    return {
        "id": f"a.md:{number}",
        "verdict": word,
        "reason": "the rate the panel asks for",
    }


def one_reply(bin_dir: Path, words: tuple[str, str]) -> None:
    """Have the judge answer the two-line body with one verdict object per id."""
    reply = [verdict(number, word) for number, word in enumerate(words, 1)]
    planned(bin_dir, [{"carries": TWO_IDS, "reply": reply}])


def bodies(bin_dir: Path) -> list[list[str]]:
    """The ids each body the judge received carried, in the order the calls arrived."""
    log = bin_dir / "calls.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def out_ids(path: Path) -> list[str]:
    """The ids the JSON at ``--out`` carries, however each of its entries spells itself."""
    entries = json.loads(path.read_text(encoding="utf-8"))
    return [entry if isinstance(entry, str) else entry["id"] for entry in entries]


def committed_tree(root: Path) -> Path:
    """A real checkout under ``root``, tracking one file in one commit, nothing staged."""
    if GIT is None:
        raise RuntimeError("git is not on PATH, so no checkout can be built")
    root.mkdir()
    (root / "a.md").write_text("the panel holds the staged rate\n", encoding="utf-8")
    for command in (("init", "-q"), ("add", "-A"), ("commit", "-qm", "tracked")):
        subprocess.run([GIT, *command], cwd=root, check=True, capture_output=True)
    return root


def arguments(*, stop: bool, out: Path | None) -> argparse.Namespace:
    """The parsed arguments a gate run carries: no files, no head, no line list."""
    return argparse.Namespace(
        files=[],
        head=False,
        stop=stop,
        lines=None,
        out=None if out is None else str(out),
    )


@pytest.fixture(autouse=True)
def forgotten_root() -> Iterator[None]:
    """Neither this module nor the next sees a work tree another case cached."""
    core.root.cache_clear()
    yield
    core.root.cache_clear()


@pytest.fixture
def bin_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The judge's directory, with a checkout beside it that the gate runs in."""
    built = built_bin(tmp_path, monkeypatch)
    monkeypatch.chdir(committed_tree(tmp_path / "repo"))
    return built


# --- behavior 1: with nothing staged, the work tree decides the exit code -----


@pytest.mark.parametrize(
    ("tracked", "stop", "code"),
    [
        (True, False, 0),
        (False, False, 1),
        (False, True, 2),
    ],
    ids=[
        "inside a work tree",
        "inside no work tree",
        "inside no work tree under stop",
    ],
)
def test_the_comment_gate_with_nothing_staged_exits_zero_only_inside_a_work_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tracked: bool,
    stop: bool,
    code: int,
) -> None:
    built_bin(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    if tracked:
        where = committed_tree(tmp_path / "repo")
    else:
        where = tmp_path / "loose"
        where.mkdir()
    monkeypatch.chdir(where)
    assert gate.run(arguments(stop=stop, out=None), comment_trivia.gate()) == code


# --- behavior 2: the --out file names the flagged lines, and no others --------


@pytest.mark.parametrize(
    ("words", "ids"),
    [
        (("trivia", "clean"), ["a.md:1"]),
        (("clean", "trivia"), ["a.md:2"]),
    ],
    ids=["the first line alone is trivia", "the second line alone is trivia"],
)
def test_the_out_file_carries_the_ids_the_judge_flagged_and_no_others(
    bin_dir: Path, tmp_path: Path, words: tuple[str, str], ids: list[str]
) -> None:
    one_reply(bin_dir, words)
    out = tmp_path / "flags.json"
    args = arguments(stop=False, out=out)
    markdown = md_trivia.gate(None)
    stream = io.StringIO()
    gate.judged(args, markdown, TWO_LINES, stream)
    assert out_ids(out) == ids


# --- behavior 3: the cache keeps the digests of the lines the judge passed ----


@pytest.mark.parametrize(
    ("words", "digests"),
    [
        (("trivia", "clean"), [SECOND_DIGEST]),
        (("clean", "trivia"), [FIRST_DIGEST]),
    ],
    ids=["the first line alone is trivia", "the second line alone is trivia"],
)
def test_the_cache_keeps_the_digest_of_the_line_the_judge_passed_alone(
    bin_dir: Path, tmp_path: Path, words: tuple[str, str], digests: list[str]
) -> None:
    one_reply(bin_dir, words)
    cache = tmp_path / "clean.json"
    args = arguments(stop=True, out=None)
    markdown = md_trivia.gate(cache)
    stream = io.StringIO()
    gate.judged(args, markdown, TWO_LINES, stream)
    assert json.loads(cache.read_text(encoding="utf-8")) == digests


# --- behavior 4: a line list of no lines costs no judge call ------------------


@pytest.mark.parametrize(
    ("lines", "asked"),
    [
        ([], []),
        (TWO_LINES[:1], [["a.md:1"]]),
    ],
    ids=["no lines at all", "one line"],
)
def test_the_judge_is_called_once_for_one_line_and_not_at_all_for_none(
    bin_dir: Path, lines: list[Line], asked: list[list[str]]
) -> None:
    gate.verdicts(
        lines,
        "prompt",
        exhaustive=False,
        batch=0,
        parallel=1,
        model="a-model",
        timeout=30,
    )
    assert bodies(bin_dir) == asked
