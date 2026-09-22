"""The run flow a gate shares: collect, screen, judge, and the chunked ask beneath it.

A judge reads a bounded number of the lines it is handed. Past that bound its
recall falls and which lines it reads changes from call to call, so one call
carrying every candidate answers about a different subset each run. ``verdicts``
is the answer to that: it splits the lines into chunks of ``batch``, asks each
chunk its own call, runs those calls concurrently, and unions the flags.

``exhaustive`` is the second half of it. Under a schema that asks for one hit
per offending line, an answer that stops early is well-formed, so nothing forces
a reading of every line. Under a schema that asks for one verdict per input id,
a short answer is visible: ``verdicts`` compares the ids it got against the ids
it sent, asks the gap once more as its own call, and reports an id still
unanswered as a flag of its own rather than as a pass. A gate whose prompt asks
for hits alone sets ``exhaustive=False`` and reads its answer as the judge gave
it.

Both knobs default to off on ``Gate``, so a gate that names neither makes one
call for every line it collected and reads the hits it comes back with.
"""

from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

from triviajudge.config import settings
from triviajudge.core import (
    Gate,
    Line,
    NotARepositoryError,
    inner_session,
    remember_clean,
    report,
)
from triviajudge.transport import ask

if TYPE_CHECKING:
    import argparse
    from collections.abc import Callable
    from typing import TextIO

#: The verdict word an exhaustive answer carries for a line that offends. The
#: prompt asking for a verdict names this word and one other, and any word but
#: this one passes the line, so a garbled verdict flags nothing.
FLAGGING = "trivia"

#: The reason on a flag standing for a line the judge returned no verdict for,
#: after the gap was asked a second time. Failing the line closed is what keeps a
#: dropped id from reading as a pass.
NO_VERDICT = "no verdict returned"


def workers(asked: int) -> int:
    """Concurrent calls to run, at least one and at most half the cores this host has."""
    return max(1, min(asked, (os.cpu_count() or 2) // 2))


def chunked(lines: list[Line], size: int) -> list[list[Line]]:
    """Split the lines into calls of at most ``size``; a size of 0 is one call carrying all of them."""
    if not lines:
        return []
    if size <= 0:
        return [lines]
    return [lines[start : start + size] for start in range(0, len(lines), size)]


def flagging(answer: list[dict[str, str]]) -> list[dict[str, str]]:
    """The flags an exhaustive answer carries: the objects whose verdict is the flagging word."""
    return [
        {"id": str(item.get("id")), "reason": str(item.get("reason", "")).strip()}
        for item in answer
        if str(item.get("verdict", "")).strip().lower() == FLAGGING
    ]


def unanswered(lines: list[Line], answer: list[dict[str, str]]) -> list[Line]:
    """The lines an exhaustive answer carries no object for, in the order they were sent."""
    answered = {str(item.get("id")) for item in answer}
    return [line for line in lines if line.id not in answered]


def covered(
    lines: list[Line],
    answer: list[dict[str, str]],
    prompt: str,
    model: str | None,
    timeout: float | None,
) -> list[dict[str, str]]:
    """The flags of an exhaustive answer, with the ids it skipped asked once more and then flagged."""
    flags = flagging(answer)
    missing = unanswered(lines, answer)
    if not missing:
        return flags
    again = ask(missing, prompt, model, timeout, exhaustive=True)
    still = [
        {"id": line.id, "reason": NO_VERDICT} for line in unanswered(missing, again)
    ]
    return flags + flagging(again) + still


def asked(
    lines: list[Line],
    prompt: str,
    *,
    exhaustive: bool,
    model: str | None,
    timeout: float | None,
) -> list[dict[str, str]]:
    """One call's flags, read against the ids it was sent where the schema is exhaustive."""
    answer = ask(lines, prompt, model, timeout, exhaustive=exhaustive)
    if not exhaustive:
        return answer
    return covered(lines, answer, prompt, model, timeout)


def spread(
    one: Callable[[list[Line]], list[dict[str, str]]],
    groups: list[list[Line]],
    at_once: int,
) -> list[list[dict[str, str]]]:
    """Every chunk's answer, run concurrently where there is more than one chunk and room for it."""
    if at_once > 1 and len(groups) > 1:
        with ThreadPoolExecutor(max_workers=at_once) as pool:
            return list(pool.map(one, groups))
    return [one(group) for group in groups]


def verdicts(  # noqa: PLR0913 — every argument is one knob a caller sets independently: what to ask, how to read the answer, how to split it, how many at once, and the two the transport takes
    lines: list[Line],
    prompt: str,
    *,
    exhaustive: bool,
    batch: int,
    parallel: int,
    model: str | None = None,
    timeout: float | None = None,
) -> list[dict[str, str]]:
    """Ask the judge about the lines in chunks of ``batch``, and union what the chunks flag.

    ``parallel`` is how many of those chunks are in flight at once, capped at
    half the cores. A caller that pools the calls itself passes 1, so the two
    pools never multiply.
    """
    groups = chunked(lines, batch)
    if not groups:
        return []
    one = partial(
        asked, prompt=prompt, exhaustive=exhaustive, model=model, timeout=timeout
    )
    answers = spread(one, groups, workers(parallel))
    return [flag for answer in answers for flag in answer]


def run(args: argparse.Namespace, gate: Gate) -> int:
    """Print what the screen refused, judge what it left, and answer with the exit code."""
    out = sys.stderr if args.stop else sys.stdout
    if args.stop and inner_session():
        return 0
    try:
        lines, complaints = gate.collect(args)
    except NotARepositoryError as exc:
        print(f"trivia judge: {exc}", file=sys.stderr)
        return 2 if args.stop else 1
    return screened(args, gate, lines, complaints, out)


def screened(
    args: argparse.Namespace,
    gate: Gate,
    lines: list[Line],
    complaints: list[str],
    out: TextIO,
) -> int:
    """Print what the pattern screen refused, then judge whatever it left."""
    for complaint in complaints:
        print(complaint, file=out)
    if args.stop and not gate.judge_at_stop:
        return 2 if complaints else 0
    if not lines:
        if not args.stop:
            print(gate.empty)
        return 0
    return judged(args, gate, lines, out)


def judged(args: argparse.Namespace, gate: Gate, lines: list[Line], out: TextIO) -> int:
    """Ask the judge about the lines the screen left, and answer with the exit code."""
    fail = 2 if args.stop else 1
    try:
        flags = verdicts(
            lines,
            gate.prompt,
            exhaustive=gate.exhaustive,
            batch=gate.batch,
            parallel=settings().gate_parallel,
        )
    except (RuntimeError, TypeError, ValueError, OSError) as exc:
        print(f"trivia judge unavailable, refusing to pass: {exc}", file=sys.stderr)
        return fail
    if args.out:
        Path(args.out).write_text(json.dumps(flags, indent=2) + "\n", encoding="utf-8")
    if args.stop and gate.cache is not None:
        remember_clean(lines, flags, gate.cache)
    return fail if report(lines, flags, out) else 0
