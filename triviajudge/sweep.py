"""Sweep: run the two judges over every line the repository holds, not over what a change adds.

The gates judge added lines. Sweep judges the tree. It is the one deliberate
exception to that scope rule, and it is exempt because it is an explicit user
act: a console script the owner runs, never a hook, never wired into
``hooks.json``. Nothing here fires on a turn or a commit, so "no gate
re-litigates shipped prose" stays true of every hook mode.

Collection is whole-file, through the filters the gates already use:
``prose_only`` and ``md_skip`` for markdown, ``in_scope`` and the docstring and
comment readers for source. The archaeology patterns screen the comment
candidates first, as they do at commit. Their complaints are free — no model
call carries them — and they never reach the judge.

Cost is the thing to hold. ``triviajudge.transport.ask`` sends one call for every line it is
given, whichever backend carries it, so a whole tree in one call is a call
nobody can afford to lose. Sweep
splits the candidates into batches of ``gate_batch`` and asks once per batch.
A batch that fails is reported with the files it covers and the run continues:
a commit gate fails closed because a commit is one decision, and a sweep is
hundreds, so one dead call must not throw away the rest.

Two modes ship together. The default reports flags and writes no cache. With
``--baseline`` every line a successful batch passed is written by digest to
``sweep-clean.json``, a file of its own that the markdown gate reads at
``Stop`` beside its own cache. One file holds the whole amnesty, so deleting
it revokes the whole amnesty.

Results arrive piecemeal. Each batch prints as it answers and appends a line
to ``sweep-journal.jsonl``, and ``--baseline`` takes its passed lines, before
the next is read. Ctrl-C or SIGTERM stops the run with the summary and
``--out`` written for what landed, the unanswered batches named as not judged,
and exit 130; an exception that escapes a batch does the same and exits 1.

Usage:

* ``triviajudge-sweep`` counts the candidates, prints the call count, asks, and
  judges both gates' candidates
* ``triviajudge-sweep --md`` or ``--comments`` for one gate alone
* ``triviajudge-sweep --paths PREFIX`` narrows to a subtree, repeatable
* ``triviajudge-sweep --limit N`` judges the first N candidates
* ``triviajudge-sweep --baseline`` writes every passed line to the sweep cache
* ``triviajudge-sweep --check`` exits 1 when anything is flagged, on a run that
  was not stopped
"""

from __future__ import annotations

import argparse
import contextlib
import json
import signal
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING

from triviajudge import comment_trivia, md_screen, md_trivia
from triviajudge.config import SWEEP_CACHE, cache_path, settings
from triviajudge.core import (
    Line,
    NotARepositoryError,
    clean_cache,
    digest,
    git,
    root,
)
from triviajudge.gate import verdicts
from triviajudge.gate import workers as workers  # noqa: PLC0414 — the alias is the explicit re-export: one cap covers the gate path and the sweep, and callers of a sweep read it here
from triviajudge.sweep_report import (
    Batch,
    Stopped,
    announce,
    exit_code,
    flagged_ids,
    unfinished,
)
from triviajudge.sweep_report import Result as Result  # noqa: PLC0414 — the alias is the explicit re-export: callers of a sweep name a batch's answer here
from triviajudge.sweep_report import report as report  # noqa: PLC0414 — the alias is the explicit re-export: callers of a sweep report its results here
from triviajudge.transport import CLAUDE_BACKEND

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable, Iterator

#: The cache a ``--baseline`` run writes, read by the markdown gate at ``Stop``.
CACHE_NAME = SWEEP_CACHE

#: One JSON line per answered batch, appended as it lands; no gate reads it.
JOURNAL_NAME = "sweep-journal.jsonl"

#: Seconds one batch's CLI call may take before it is killed and reported as a failed batch.
CALL_TIMEOUT = 600

MD = "md"
COMMENTS = "comments"


def repo_files(pattern: str | None = None) -> list[str]:
    """Every tracked file, repo-relative, narrowed by a git pathspec."""
    limit = ["--", pattern] if pattern else []
    return git("ls-files", *limit).split()


def wanted(path: str, prefixes: tuple[str, ...]) -> bool:
    """Whether a path is inside one of the ``--paths`` prefixes; no prefix means the whole tree."""
    return not prefixes or path.startswith(prefixes)


def file_lines(rel: str) -> list[Line]:
    """Every line of one file, numbered from one."""
    text = (root() / rel).read_text(encoding="utf-8").splitlines()
    return [Line(rel, number, line) for number, line in enumerate(text, start=1)]


def md_candidates(prefixes: tuple[str, ...]) -> list[Line]:
    """Every markdown line in the tree that carries prose; screened by ``md_screen.screen`` in ``collect``."""
    out: list[Line] = []
    for rel in repo_files("*.md"):
        if wanted(rel, prefixes):
            out.extend(file_lines(rel))
    return md_trivia.prose_only(out)


def comment_candidates(prefixes: tuple[str, ...]) -> tuple[list[Line], list[str]]:
    """Every comment and docstring in the tree, screened by the archaeology patterns first."""
    cands: list[Line] = []
    for rel in repo_files():
        if not wanted(rel, prefixes) or not comment_trivia.in_scope(rel):
            continue
        try:
            text = (root() / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"{rel}: not read ({exc})", file=sys.stderr)
            continue
        cands.extend(
            comment_trivia.parsed(rel, text, set(range(1, len(text.splitlines()) + 1)))
        )
    return comment_trivia.screen(cands)


def batched(gate: str, prompt: str, lines: list[Line], size: int) -> list[Batch]:
    """Split one gate's candidates into calls of at most ``size`` lines."""
    chunks = [lines[start : start + size] for start in range(0, len(lines), size)]
    return [
        Batch(gate, index, prompt, chunk) for index, chunk in enumerate(chunks, start=1)
    ]


def transport() -> str:
    """What one concurrent call spends, in the words of the configured backend.

    A consent line that names a `claude` process under a backend that starts no
    process tells the owner the wrong thing about what the run costs.
    """
    conf = settings()
    if conf.backend == CLAUDE_BACKEND:
        return "`claude` process(es)"
    return f"request(s) to {conf.base_url}"


def consent(batches: list[Batch], model: str, parallel: int, *, assumed: bool) -> bool:
    """Print what the run will spend and read the answer; ``--yes`` assumes it."""
    lines = sum(len(batch.lines) for batch in batches)
    print(f"{lines} line(s), {len(batches)} call(s) at {model}")
    if parallel > 1:
        print(f"{parallel} concurrent {transport()}, {CALL_TIMEOUT}s timeout each")
    if assumed:
        return True
    try:
        answer = input("run? [y/N] ")
    except EOFError:
        return False
    return answer.strip().lower() in {"y", "yes"}


def judge(batch: Batch, model: str) -> tuple[Batch, list[dict[str, str]] | None, str]:
    """Ask one batch; a failure answers with None and the shortest message that says why."""
    try:
        flags = verdicts(
            batch.lines,
            batch.prompt,
            exhaustive=batch.gate == MD,
            batch=0,
            parallel=1,
            model=model,
            timeout=CALL_TIMEOUT,
        )
        return batch, flags, ""
    except (RuntimeError, TypeError, ValueError, OSError) as exc:
        return batch, None, str(exc)


def run_batches(batches: list[Batch], model: str, parallel: int) -> Generator[Result]:
    """Ask every batch and yield each answer as it arrives: in order, or as the calls finish."""
    if parallel <= 1:
        for batch in batches:
            yield judge(batch, model)
        return
    pool = ThreadPoolExecutor(max_workers=parallel)
    try:
        futures = [pool.submit(judge, batch, model) for batch in batches]
        for future in as_completed(futures):
            yield future.result()
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def journal_path() -> Path:
    """The journal of the current run, under the root this sweep resolved."""
    return root() / settings().cache_dir / JOURNAL_NAME


def landed(
    results: Iterable[Result], journal: Path, kept: list[Result], *, baseline: bool
) -> Iterator[Result]:
    """Write each result to the journal, and to the baseline under ``--baseline``, before passing it on."""
    for batch, answer, error in results:
        entry = {
            "batch": batch.name,
            "paths": batch.paths,
            "flags": answer,
            "error": error,
        }
        with journal.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
        if baseline and answer is not None:
            ids = flagged_ids(answer)
            write_baseline([line for line in batch.lines if line.id not in ids])
        kept.append((batch, answer, error))
        yield batch, answer, error


def write_baseline(passed: list[Line]) -> Path:
    """Add every passed line's digest to the sweep cache and answer with its path."""
    path = cache_path(CACHE_NAME)
    seen = clean_cache(path)
    known = set(seen)
    for line in passed:
        if digest(line) not in known:
            seen.append(digest(line))
            known.add(digest(line))
    path.parent.mkdir(parents=True, exist_ok=True)
    # A torn file reads back empty in clean_cache and loses every older digest.
    staged = path.with_name(path.name + ".tmp")
    staged.write_text(json.dumps(seen) + "\n", encoding="utf-8")
    staged.replace(path)
    return path


def parse_args() -> argparse.Namespace:
    """Read the gate selection, the scoping flags and the two output modes."""
    parser = argparse.ArgumentParser(
        description=__doc__ or "", formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--md", action="store_true", help="sweep markdown only")
    parser.add_argument(
        "--comments", action="store_true", help="sweep comments and docstrings only"
    )
    parser.add_argument(
        "--paths",
        action="append",
        default=[],
        metavar="PREFIX",
        help="limit to a path prefix",
    )
    parser.add_argument("--batch", type=int, help="lines per call (default gate_batch)")
    parser.add_argument(
        "--limit", type=int, help="judge at most this many candidates per gate"
    )
    parser.add_argument(
        "--parallel", type=int, help="concurrent calls (default sweep_parallel)"
    )
    parser.add_argument("--model", help="model to ask (default sweep_model)")
    parser.add_argument("--yes", action="store_true", help="skip the confirmation")
    parser.add_argument(
        "--baseline",
        action="store_true",
        help=f"write every passed line to {CACHE_NAME}",
    )
    parser.add_argument(
        "--check", action="store_true", help="exit 1 when anything is flagged"
    )
    parser.add_argument(
        "--out", help="write the flags, complaints and failures here as JSON"
    )
    return parser.parse_args()


def collect(args: argparse.Namespace, size: int) -> tuple[list[Batch], list[str]]:
    """The batches to ask and the complaints the pattern screen already answered for.

    Both judges take ``size`` lines per call, the chunk their gates take, so a
    sweep reads each line the way a commit would.
    """
    prefixes = tuple(args.paths)
    both = not args.md and not args.comments
    batches: list[Batch] = []
    complaints: list[str] = []
    if args.md or both:
        lines, md_complaints = md_screen.screen(md_candidates(prefixes))
        complaints.extend(md_complaints)
        batches.extend(batched(MD, md_trivia.PROMPT, lines[: args.limit], size))
    if args.comments or both:
        lines, comment_complaints = comment_candidates(prefixes)
        complaints.extend(comment_complaints)
        batches.extend(
            batched(COMMENTS, comment_trivia.PROMPT, lines[: args.limit], size)
        )
    return batches, complaints


def main() -> int:
    """Sweep the tree, report what the judges flagged, and answer with the exit code."""
    args = parse_args()
    try:
        config = settings()
        size = args.batch or config.gate_batch
        model = args.model or config.sweep_model
        parallel = workers(args.parallel or config.sweep_parallel)
        batches, complaints = collect(args, size)
    except (NotARepositoryError, RuntimeError, OSError) as exc:
        print(f"trivia judge: {exc}", file=sys.stderr)
        return 1
    for complaint in complaints:
        print(complaint)
    if not batches:
        print("[ok] nothing to judge")
        return 1 if args.check and complaints else 0
    if not consent(batches, model, parallel, assumed=args.yes):
        print("nothing asked", file=sys.stderr)
        return 0
    journal_path().parent.mkdir(parents=True, exist_ok=True)
    journal_path().write_text("", encoding="utf-8")
    # SIGTERM raises KeyboardInterrupt, so it stops the run the way Ctrl-C does.
    previous = signal.signal(signal.SIGTERM, signal.default_int_handler)
    try:
        return finish(args, batches, run_batches(batches, model, parallel), complaints)
    finally:
        signal.signal(signal.SIGTERM, previous)


def finish(
    args: argparse.Namespace,
    batches: list[Batch],
    results: Generator[Result],
    complaints: list[str],
) -> int:
    """Report what the judges flagged, what failed, what was never judged and what the baseline took; answer with the exit code."""
    kept: list[Result] = []
    try:
        # Caught outside `closing`, so the pool is shut before the summary.
        with contextlib.closing(results):
            flags, passed = report(
                landed(results, journal_path(), kept, baseline=args.baseline)
            )
    except Stopped as exc:
        stop: Stopped | None = exc
        flags, passed, done = exc.flags, exc.passed, exc.landed
    else:
        stop, done = None, [batch.name for batch in batches]
    failed, unjudged = unfinished(batches, kept, done)
    announce(failed, unjudged, stop)
    if args.baseline:
        print(f"\n{len(passed)} passed line(s) written to {cache_path(CACHE_NAME)}")
    print(f"\n{len(flags)} flag(s), {len(complaints)} pattern complaint(s)", flush=True)
    record = {
        "flags": flags,
        "screen": complaints,
        "failed": failed,
        "unjudged": unjudged,
        "stopped": "" if stop is None else stop.reason,
    }
    if args.out:
        Path(args.out).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return exit_code(stop, check=args.check, found=bool(flags or complaints or failed))


if __name__ == "__main__":
    sys.exit(main())
