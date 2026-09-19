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

Cost is the thing to hold. ``core.ask`` sends one call for every line it is
given, whichever backend carries it, so a whole tree in one call is a call
nobody can afford to lose. Sweep
splits the candidates into batches of ``sweep_batch`` and asks once per batch.
A batch that fails is reported with the files it covers and the run continues:
a commit gate fails closed because a commit is one decision, and a sweep is
hundreds, so one dead call must not throw away the rest.

Two modes ship together. The default reports flags and writes no cache. With
``--baseline`` every line a successful batch passed is written by digest to
``sweep-clean.json``, a file of its own that the markdown gate reads at
``Stop`` beside its own cache. One file holds the whole amnesty, so deleting
it revokes the whole amnesty.

Usage:

* ``triviajudge-sweep`` counts the candidates, prints the call count, asks, and
  judges both gates' candidates
* ``triviajudge-sweep --md`` or ``--comments`` for one gate alone
* ``triviajudge-sweep --paths PREFIX`` narrows to a subtree, repeatable
* ``triviajudge-sweep --limit N`` judges the first N candidates
* ``triviajudge-sweep --baseline`` writes every passed line to the sweep cache
* ``triviajudge-sweep --check`` exits 1 when anything is flagged
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from triviajudge import comment_trivia, md_trivia
from triviajudge.config import SWEEP_CACHE, cache_path, settings
from triviajudge.core import CLAUDE_BACKEND, Line, NotARepositoryError, ask, clean_cache, digest, git, root

#: The cache a ``--baseline`` run writes, read by the markdown gate at ``Stop``.
CACHE_NAME = SWEEP_CACHE

#: Seconds one batch's CLI call may take before it is killed and reported as a failed batch.
CALL_TIMEOUT = 600

MD = "md"
COMMENTS = "comments"


@dataclass(frozen=True)
class Batch:
    """One CLI call's worth of candidates, addressed so a failure names what to rerun."""

    gate: str
    index: int
    prompt: str
    lines: list[Line] = field(compare=False)

    @property
    def name(self) -> str:
        """``gate#index``, printed on a failure."""
        return f"{self.gate}#{self.index}"

    @property
    def paths(self) -> list[str]:
        """Every distinct file the batch covers, for the rerun line."""
        return sorted({line.path for line in self.lines})


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
    """Every markdown line in the tree that carries prose, through the markdown gate's own screen."""
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
        cands.extend(comment_trivia.parsed(rel, text, set(range(1, len(text.splitlines()) + 1))))
    return comment_trivia.screen(cands)


def batched(gate: str, prompt: str, lines: list[Line], size: int) -> list[Batch]:
    """Split one gate's candidates into calls of at most ``size`` lines."""
    chunks = [lines[start : start + size] for start in range(0, len(lines), size)]
    return [Batch(gate, index, prompt, chunk) for index, chunk in enumerate(chunks, start=1)]


def workers(asked: int) -> int:
    """Concurrent calls to run, at least one and at most half the cores this host has."""
    return max(1, min(asked, (os.cpu_count() or 2) // 2))


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
        return batch, ask(batch.lines, batch.prompt, model=model, timeout=CALL_TIMEOUT), ""
    except (RuntimeError, TypeError, ValueError, OSError) as exc:
        return batch, None, str(exc)


#: What one asked batch came back with: the batch, its flags (None when the call failed) and the failure text.
Result = tuple[Batch, list[dict[str, str]] | None, str]


def run_batches(batches: list[Batch], model: str, parallel: int) -> list[Result]:
    """Ask every batch, in order or in parallel, and keep the answer each one gave."""
    if parallel <= 1:
        return [judge(batch, model) for batch in batches]
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        return list(pool.map(lambda batch: judge(batch, model), batches))


def flagged_ids(flags: list[dict[str, str]]) -> set[str]:
    """The ids a batch's answer flagged."""
    return {str(flag.get("id")) for flag in flags}


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
    path.write_text(json.dumps(seen) + "\n", encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    """Read the gate selection, the scoping flags and the two output modes."""
    parser = argparse.ArgumentParser(description=__doc__ or "", formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--md", action="store_true", help="sweep markdown only")
    parser.add_argument("--comments", action="store_true", help="sweep comments and docstrings only")
    parser.add_argument("--paths", action="append", default=[], metavar="PREFIX", help="limit to a path prefix")
    parser.add_argument("--batch", type=int, help="lines per call (default sweep_batch)")
    parser.add_argument("--limit", type=int, help="judge at most this many candidates per gate")
    parser.add_argument("--parallel", type=int, help="concurrent calls (default sweep_parallel)")
    parser.add_argument("--model", help="model to ask (default sweep_model)")
    parser.add_argument("--yes", action="store_true", help="skip the confirmation")
    parser.add_argument("--baseline", action="store_true", help=f"write every passed line to {CACHE_NAME}")
    parser.add_argument("--check", action="store_true", help="exit 1 when anything is flagged")
    parser.add_argument("--out", help="write the flags, complaints and failures here as JSON")
    return parser.parse_args()


def collect(args: argparse.Namespace, size: int) -> tuple[list[Batch], list[str]]:
    """The batches to ask and the complaints the pattern screen already answered for."""
    prefixes = tuple(args.paths)
    both = not args.md and not args.comments
    batches: list[Batch] = []
    complaints: list[str] = []
    if args.md or both:
        lines = md_candidates(prefixes)[: args.limit]
        batches.extend(batched(MD, md_trivia.PROMPT, lines, size))
    if args.comments or both:
        lines, complaints = comment_candidates(prefixes)
        batches.extend(batched(COMMENTS, comment_trivia.PROMPT, lines[: args.limit], size))
    return batches, complaints


def report(results: list[Result]) -> tuple[list[dict[str, str]], list[Line]]:
    """Print every flag and every failed batch; answer with the flags and the lines that passed."""
    flags: list[dict[str, str]] = []
    passed: list[Line] = []
    for batch, answer, error in results:
        if answer is None:
            print(f"batch {batch.name} failed ({len(batch.lines)} line(s)): {error}", file=sys.stderr)
            rerun = " ".join(f"--paths {path}" for path in batch.paths)
            print(f"  rerun: triviajudge-sweep --{batch.gate} {rerun}", file=sys.stderr)
            continue
        ids = flagged_ids(answer)
        by_id = {line.id: line for line in batch.lines}
        for flag in answer:
            ident = str(flag.get("id"))
            where = ident if ident in by_id else f"?:{ident}"
            print(f"{where}: {str(flag.get('reason', '')).strip()}")
            flags.append({"id": ident, "reason": str(flag.get("reason", "")).strip()})
        passed.extend(line for line in batch.lines if line.id not in ids)
    return flags, passed


def main() -> int:
    """Sweep the tree, report what the judges flagged, and answer with the exit code."""
    args = parse_args()
    try:
        config = settings()
        size = args.batch or config.sweep_batch
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
    return finish(args, run_batches(batches, model, parallel), complaints)


def finish(args: argparse.Namespace, results: list[Result], complaints: list[str]) -> int:
    """Report what the judges flagged, what failed and what the baseline took, and answer with the exit code."""
    flags, passed = report(results)
    failed = [batch.name for batch, answer, _ in results if answer is None]
    if failed:
        print(f"\n{len(failed)} batch(es) failed and were not judged: {', '.join(failed)}", file=sys.stderr)
    if args.baseline:
        print(f"\n{len(passed)} passed line(s) written to {write_baseline(passed)}")
    print(f"\n{len(flags)} flag(s), {len(complaints)} pattern complaint(s)")
    if args.out:
        record = {"flags": flags, "screen": complaints, "failed": failed}
        Path(args.out).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    if args.check and (flags or complaints or failed):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
