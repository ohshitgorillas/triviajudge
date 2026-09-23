"""The sweep: batching, scoping, the parallel cap, the failure path, the baseline cache.

``triviajudge.sweep`` judges the whole tree instead of what a change adds, so
what is pinned here is the machinery that keeps a whole-tree run affordable and
survivable.

``batched`` splits one gate's candidates into calls of at most ``sweep_batch``
lines, because ``transport.ask`` carries every line it is given in one call.
``wanted`` is the ``--paths`` filter, and an empty prefix list is the whole
tree rather than nothing. ``workers`` caps concurrency at half the host's
cores, whatever it is asked for.

``report`` is the part a commit gate does not have: a batch whose call failed
is printed with the files it covers and the run continues, and its lines reach
neither the flag list nor the baseline. A batch that answered contributes its
flags, and the lines it did not flag are the ones ``--baseline`` may remember.

``write_baseline`` appends digests to ``sweep-clean.json``, the file the
markdown gate reads at ``Stop`` beside its own cache, so the amnesty is one
file and deleting it revokes the whole amnesty.

Every phrase a judge would rule on lives in a string literal, never in a
comment or docstring of this file.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterator
from fnmatch import fnmatch
from pathlib import Path

import pytest

from triviajudge import core, sweep
from triviajudge.config import Settings
from triviajudge.core import Line, digest

LINES = [Line("doc.md", number, f"line {number}") for number in range(1, 8)]


# --- behavior 1: one gate's candidates become calls of at most `size` lines ---


@pytest.mark.parametrize(("size", "sizes"), [(3, [3, 3, 1]), (7, [7]), (100, [7])])
def test_candidates_are_split_into_calls_of_at_most_the_batch_size(
    size: int, sizes: list[int]
) -> None:
    batches = sweep.batched(sweep.MD, "prompt", LINES, size)
    assert [len(batch.lines) for batch in batches] == sizes


def test_a_batch_names_its_gate_its_number_and_the_files_it_covers() -> None:
    lines = [Line("b.md", 1, "one"), Line("a.md", 2, "two"), Line("a.md", 3, "three")]
    batch = sweep.batched(sweep.COMMENTS, "prompt", lines, 10)[0]
    assert (batch.name, batch.paths) == ("comments#1", ["a.md", "b.md"])


def test_no_candidates_is_no_calls() -> None:
    assert sweep.batched(sweep.MD, "prompt", [], 50) == []


# --- behavior 2: --paths narrows, and no prefix is the whole tree ------------


@pytest.mark.parametrize(
    ("path", "prefixes", "kept"),
    [
        ("docs/plan.md", (), True),
        ("docs/plan.md", ("docs/",), True),
        ("docs/plan.md", ("src/",), False),
        ("docs/plan.md", ("src/", "docs/"), True),
    ],
)
def test_a_path_is_judged_when_it_sits_under_a_named_prefix(
    path: str, prefixes: tuple[str, ...], kept: bool
) -> None:
    assert sweep.wanted(path, prefixes) is kept


# --- behavior 3: concurrency is capped at half the host's cores --------------


def test_concurrency_is_at_least_one_and_at_most_half_the_cores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("triviajudge.gate.os.cpu_count", lambda: 8)
    assert [sweep.workers(asked) for asked in (0, 1, 4, 64)] == [1, 1, 4, 4]


# --- behavior 4: a failed batch is reported and the run continues ------------


def reported(
    capsys: pytest.CaptureFixture[str],
) -> tuple[list[dict[str, str]], list[Line], str]:
    """One ``report`` over a batch that answered beside a batch whose call failed."""
    lines = [
        Line("a.md", 1, "first"),
        Line("a.md", 2, "second"),
        Line("b.md", 1, "third"),
    ]
    good, bad = sweep.batched(sweep.MD, "prompt", lines, 2)
    results: list[sweep.Result] = [
        (good, [{"id": "a.md:2", "reason": "dated event"}], ""),
        (bad, None, "claude exited 1"),
    ]
    flags, passed = sweep.report(results)
    return flags, passed, capsys.readouterr().err


def test_a_failed_batch_costs_the_run_its_own_lines_and_nothing_else(
    capsys: pytest.CaptureFixture[str],
) -> None:
    flags, passed, _err = reported(capsys)
    assert ([flag["id"] for flag in flags], [line.id for line in passed]) == (
        ["a.md:2"],
        ["a.md:1"],
    )


def test_a_failed_batch_is_named_for_rerun_with_the_files_it_covers(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _flags, _passed, err = reported(capsys)
    assert "--paths b.md" in err


# --- behavior 5: --baseline writes the digests the markdown gate reads -------


def test_the_baseline_adds_passed_digests_without_dropping_the_ones_already_there(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = tmp_path / sweep.CACHE_NAME
    cache.write_text(json.dumps(["already-here"]) + "\n", encoding="utf-8")
    monkeypatch.setattr(sweep, "cache_path", lambda _name: cache)
    line = Line("a.md", 1, "the rate the panel asks for")
    sweep.write_baseline([line, line])
    assert json.loads(cache.read_text(encoding="utf-8")) == [
        "already-here",
        digest(line),
    ]


# --- behavior 6: the candidates are the tracked tree, screened by each gate ---


PROSE_MARKDOWN = "the panel holds the staged rate\n\n# a heading\n"
DATED_COMMENT = "value = 1  # added 2025-11-04 for the resampler panel\n"
CLEAN_COMMENT = "value = 2  # the lane returns the staged model\n"


def tracked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, files: dict[str, str]
) -> None:
    """Point the sweep at a throwaway tree whose tracked list is exactly ``files``."""
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def fake_git(*args: str) -> str:
        pattern = args[-1] if args[-2:-1] == ("--",) else None
        return "\n".join(
            rel for rel in sorted(files) if pattern is None or fnmatch(rel, pattern)
        )

    monkeypatch.setattr("triviajudge.sweep.git", fake_git)
    monkeypatch.setattr("triviajudge.sweep.root", lambda: tmp_path)


def test_the_markdown_candidates_are_the_prose_lines_of_the_tracked_markdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracked(
        monkeypatch,
        tmp_path,
        {"docs/plan.md": PROSE_MARKDOWN, "src/sample.py": CLEAN_COMMENT},
    )
    assert [line.id for line in sweep.md_candidates(())] == ["docs/plan.md:1"]


def test_a_prefix_keeps_the_markdown_outside_it_out_of_the_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracked(
        monkeypatch,
        tmp_path,
        {"docs/plan.md": PROSE_MARKDOWN, "notes/plan.md": PROSE_MARKDOWN},
    )
    assert [line.id for line in sweep.md_candidates(("notes/",))] == ["notes/plan.md:1"]


def test_a_dated_comment_is_screened_out_of_the_candidates_and_complained_about(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracked(monkeypatch, tmp_path, {"src/sample.py": DATED_COMMENT})
    _lines, complaints = sweep.comment_candidates(())
    assert "2025-11-04" in complaints[0]


def test_a_file_the_sweep_cannot_read_is_named_and_the_run_goes_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tracked(monkeypatch, tmp_path, {"src/sample.py": CLEAN_COMMENT})
    (tmp_path / "src/sample.py").write_bytes(b"value = 1  # \xff\xfe\n")
    sweep.comment_candidates(())
    assert "src/sample.py" in capsys.readouterr().err


# --- behavior 7: the run is asked for, and an unanswered question is a no -----


@pytest.mark.parametrize(
    ("answer", "asked"), [("y", True), ("YES", True), ("", False), ("n", False)]
)
def test_the_run_starts_only_on_a_yes(
    answer: str, asked: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt: answer)
    assert (
        sweep.consent(
            sweep.batched(sweep.MD, "prompt", LINES, 50), "a-model", 1, assumed=False
        )
        is asked
    )


def test_a_closed_stdin_is_a_no(monkeypatch: pytest.MonkeyPatch) -> None:
    def closed(_prompt: str) -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", closed)
    assert (
        sweep.consent(
            sweep.batched(sweep.MD, "prompt", LINES, 50), "a-model", 1, assumed=False
        )
        is False
    )


def assumed_consent(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> str:
    """What ``consent`` prints when the answer is assumed, with the question left unasked."""
    monkeypatch.setattr(
        "builtins.input", lambda _prompt: pytest.fail("the question was asked")
    )
    sweep.consent(
        sweep.batched(sweep.MD, "prompt", LINES, 3), "a-model", 4, assumed=True
    )
    return capsys.readouterr().out


def test_yes_skips_the_question_and_says_what_the_run_costs(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert "7 line(s), 3 call(s) at a-model" in assumed_consent(monkeypatch, capsys)


def test_the_consent_line_names_the_concurrency_the_run_will_spend(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert "4 concurrent `claude` process(es)" in assumed_consent(monkeypatch, capsys)


def test_the_consent_line_names_what_the_configured_backend_spends(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "triviajudge.sweep.settings",
        lambda: Settings(backend="local", base_url="http://127.0.0.1:8080"),
    )
    sweep.consent(
        sweep.batched(sweep.MD, "prompt", LINES, 3), "a-model", 4, assumed=True
    )
    assert "http://127.0.0.1:8080" in capsys.readouterr().out


# --- behavior 8: a failed call costs its batch, not the run ------------------


def test_a_call_that_raises_answers_with_no_flags_and_the_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(*_args: object, **_kwargs: object) -> list[dict[str, str]]:
        raise RuntimeError("claude exited 1")

    monkeypatch.setattr("triviajudge.sweep.verdicts", refuse)
    batch = sweep.batched(sweep.MD, "prompt", LINES, 50)[0]
    assert sweep.judge(batch, "a-model") == (batch, None, "claude exited 1")


def test_every_batch_is_asked_when_the_calls_run_concurrently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("triviajudge.sweep.verdicts", lambda *_args, **_kwargs: [])
    batches = sweep.batched(sweep.MD, "prompt", LINES, 2)
    assert [
        batch.name for batch, _flags, _why in sweep.run_batches(batches, "a-model", 4)
    ] == [
        "md#1",
        "md#2",
        "md#3",
        "md#4",
    ]


# --- behavior 9: the gate selection and --limit decide what is asked ---------


def namespace(**overrides: object) -> argparse.Namespace:
    """The arguments a sweep run carries, with everything the flags leave alone at its default."""
    args = {"md": False, "comments": False, "paths": [], "limit": None}
    return argparse.Namespace(**{**args, **overrides})


GIT = shutil.which("git")

THREE_PROSE_LINES = (
    "the panel holds the staged rate\n"
    "the lane returns the staged model\n"
    "the resampler runs at the rate the panel asks for\n"
)

#: The print-mode envelope a ``claude`` that flags nothing answers with.
NO_FLAGS_ENVELOPE = json.dumps({"result": "[]"})


def git_run(root: Path, *args: str) -> None:
    """Run one git command in the throwaway checkout, resolving git from the PATH the test built."""
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("git is not on the PATH the test built")
    subprocess.run([git, *args], cwd=root, check=True, capture_output=True)


def scrubbed_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An environment built from nothing: a PATH carrying git alone, a HOME under ``tmp_path``, no git config."""
    if GIT is None:
        raise RuntimeError("git is not on PATH, so no checkout can be built")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    (bin_dir / "git").symlink_to(GIT)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("LC_ALL", "C")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "sweep probe")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "sweep@example.invalid")
    monkeypatch.delenv("INNER", raising=False)
    return bin_dir


def committed_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, files: dict[str, str]
) -> Path:
    """A real throwaway checkout tracking exactly ``files`` in one commit, entered as the working directory."""
    root = tmp_path / "repo"
    root.mkdir()
    git_run(root, "init", "-q")
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    git_run(root, "add", "-A")
    git_run(root, "commit", "-qm", "tracked")
    monkeypatch.chdir(root)
    return root


@pytest.fixture
def checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Callable[[dict[str, str]], Path]]:
    """A builder of real checkouts, with the cached root forgotten on either side of the test."""
    scrubbed_environment(tmp_path, monkeypatch)
    core.root.cache_clear()
    yield lambda files: committed_checkout(tmp_path, monkeypatch, files)
    core.root.cache_clear()


def gates_of(args: argparse.Namespace) -> set[str]:
    """The gates the batches ``collect`` hands over for one argument set."""
    batches, _complaints = sweep.collect(args, 50)
    return {batch.gate for batch in batches}


def lines_handed_over(limit: int) -> int:
    """How many markdown lines ``collect`` hands over under one ``--limit``."""
    batches, _complaints = sweep.collect(namespace(md=True, limit=limit), 50)
    return sum(len(batch.lines) for batch in batches)


def test_markdown_only_asks_no_comment_batches(
    checkout: Callable[[dict[str, str]], Path],
) -> None:
    checkout({"docs/plan.md": PROSE_MARKDOWN, "src/sample.py": CLEAN_COMMENT})
    assert (gates_of(namespace(md=True)), gates_of(namespace())) == (
        {sweep.MD},
        {sweep.MD, sweep.COMMENTS},
    )


def test_comments_only_asks_no_markdown_batches(
    checkout: Callable[[dict[str, str]], Path],
) -> None:
    checkout({"docs/plan.md": PROSE_MARKDOWN, "src/sample.py": CLEAN_COMMENT})
    assert (gates_of(namespace(comments=True)), gates_of(namespace())) == (
        {sweep.COMMENTS},
        {sweep.MD, sweep.COMMENTS},
    )


@pytest.mark.parametrize(
    ("first", "ids"),
    [
        (
            "The schema was reviewed on 2026-03-14 by the owner",
            ["docs/plan.md:2"],
        ),
        (
            "the lane returns the staged model",
            ["docs/plan.md:1", "docs/plan.md:2"],
        ),
    ],
    ids=["dated first line screened out", "clean first line handed over"],
)
def test_a_markdown_line_the_screen_refuses_is_not_handed_to_the_judge(
    checkout: Callable[[dict[str, str]], Path], first: str, ids: list[str]
) -> None:
    checkout({"docs/plan.md": f"{first}\nthe panel holds the staged rate\n"})
    batches, _complaints = sweep.collect(namespace(md=True), 20)
    assert [line.id for batch in batches for line in batch.lines] == ids


def test_the_limit_caps_what_one_gate_hands_over(
    checkout: Callable[[dict[str, str]], Path],
) -> None:
    checkout({"docs/plan.md": THREE_PROSE_LINES})
    assert (lines_handed_over(2), lines_handed_over(3)) == (2, 3)


# --- behavior 10: the whole run, from the argument list to the exit code -----


def sweep_run(monkeypatch: pytest.MonkeyPatch, flags: list[str]) -> int:
    """The exit code of one sweep, driven by the flags a caller types."""
    monkeypatch.setattr(sys, "argv", ["triviajudge-sweep", *flags])
    return sweep.main()


def test_a_tree_with_nothing_to_judge_asks_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracked(monkeypatch, tmp_path, {})
    monkeypatch.setattr(
        "triviajudge.sweep.verdicts",
        lambda *_args, **_kwargs: pytest.fail("a call was made"),
    )
    assert sweep_run(monkeypatch, ["--md", "--yes"]) == 0


def test_a_declined_question_asks_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracked(monkeypatch, tmp_path, {"docs/plan.md": PROSE_MARKDOWN})
    monkeypatch.setattr("builtins.input", lambda _prompt: "n")
    monkeypatch.setattr(
        "triviajudge.sweep.verdicts",
        lambda *_args, **_kwargs: pytest.fail("a call was made"),
    )
    assert sweep_run(monkeypatch, ["--md"]) == 0


def test_a_flagged_line_fails_the_run_under_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracked(monkeypatch, tmp_path, {"docs/plan.md": PROSE_MARKDOWN})
    monkeypatch.setattr(
        "triviajudge.sweep.verdicts",
        lambda *_args, **_kwargs: [
            {"id": "docs/plan.md:1", "reason": "narrates a decision"}
        ],
    )
    assert sweep_run(monkeypatch, ["--md", "--yes", "--check"]) == 1


def test_the_out_file_carries_the_flags_the_run_printed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracked(monkeypatch, tmp_path, {"docs/plan.md": PROSE_MARKDOWN})
    monkeypatch.setattr(
        "triviajudge.sweep.verdicts",
        lambda *_args, **_kwargs: [
            {"id": "docs/plan.md:1", "reason": "narrates a decision"}
        ],
    )
    out = tmp_path / "flags.json"
    sweep_run(monkeypatch, ["--md", "--yes", "--out", str(out)])
    assert (
        json.loads(out.read_text(encoding="utf-8"))["flags"][0]["id"]
        == "docs/plan.md:1"
    )


def test_the_baseline_remembers_the_lines_no_judge_flagged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracked(monkeypatch, tmp_path, {"docs/plan.md": PROSE_MARKDOWN})
    cache = tmp_path / sweep.CACHE_NAME
    monkeypatch.setattr(sweep, "cache_path", lambda _name: cache)
    monkeypatch.setattr("triviajudge.sweep.verdicts", lambda *_args, **_kwargs: [])
    sweep_run(monkeypatch, ["--md", "--yes", "--baseline"])
    first = Line("docs/plan.md", 1, PROSE_MARKDOWN.splitlines()[0])
    assert json.loads(cache.read_text(encoding="utf-8")) == [digest(first)]


def test_a_failed_batch_is_named_on_the_way_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def refuse(*_args: object, **_kwargs: object) -> list[dict[str, str]]:
        raise RuntimeError("claude exited 1")

    tracked(monkeypatch, tmp_path, {"docs/plan.md": PROSE_MARKDOWN})
    monkeypatch.setattr("triviajudge.sweep.verdicts", refuse)
    sweep_run(monkeypatch, ["--md", "--yes"])
    assert "md#1" in capsys.readouterr().err


def fake_claude(bin_dir: Path, envelope: str) -> None:
    """A ``claude`` executable on the test-built PATH printing one fixed print-mode envelope."""
    script = bin_dir / "claude"
    script.write_text(f"#!/bin/sh\nprintf '%s\\n' '{envelope}'\n", encoding="utf-8")
    script.chmod(0o755)


def exit_code(monkeypatch: pytest.MonkeyPatch, flags: list[str]) -> int:
    """The exit code of one sweep, whether ``main`` returns it or raises it."""
    try:
        return sweep_run(monkeypatch, flags)
    except SystemExit as exc:
        return int(exc.code or 0)


def test_a_directory_in_no_work_tree_is_refused_rather_than_swept(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    checkout: Callable[[dict[str, str]], Path],
) -> None:
    fake_claude(tmp_path / "bin", NO_FLAGS_ENVELOPE)
    bare = tmp_path / "bare"
    bare.mkdir()
    monkeypatch.chdir(bare)
    outside = exit_code(monkeypatch, ["--md", "--yes"])
    core.root.cache_clear()
    checkout({"docs/plan.md": PROSE_MARKDOWN})
    inside = exit_code(monkeypatch, ["--md", "--yes"])
    assert (outside, inside) == (1, 0)
