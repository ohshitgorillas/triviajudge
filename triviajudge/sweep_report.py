"""What a sweep prints and answers with: each batch's flags as it lands, the stop and the exit code.

``triviajudge.sweep`` asks the batches and writes what lands to disk; this
module holds the batch itself, the printing and the ``Stopped`` a run raises
when it ends before every batch answered, so what landed survives the unwind.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from triviajudge.core import Line

#: The exit code of a run stopped by Ctrl-C or SIGTERM.
INTERRUPTED = 130


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


#: What one asked batch came back with: the batch, its flags (None when the call failed) and the failure text.
Result = tuple[Batch, list[dict[str, str]] | None, str]


@dataclass
class Stopped(Exception):  # noqa: N818 — the name is what happened to the run, and "StoppedError" would call an interrupt an error
    """A run that ended before every batch answered, carrying the flags, passed lines and batch names that landed first."""

    flags: list[dict[str, str]]
    passed: list[Line]
    landed: list[str]
    reason: str
    interrupted: bool


def flagged_ids(flags: list[dict[str, str]]) -> set[str]:
    """The ids a batch's answer flagged."""
    return {str(flag.get("id")) for flag in flags}


def reported(result: Result) -> tuple[list[dict[str, str]], list[Line]]:
    """Print one batch's flags, or its failure, flushed; answer with its flags and passed lines."""
    batch, answer, error = result
    if answer is None:
        print(
            f"batch {batch.name} failed ({len(batch.lines)} line(s)): {error}",
            file=sys.stderr,
        )
        rerun = " ".join(f"--paths {path}" for path in batch.paths)
        print(
            f"  rerun: triviajudge-sweep --{batch.gate} {rerun}",
            file=sys.stderr,
            flush=True,
        )
        return [], []
    ids = flagged_ids(answer)
    by_id = {line.id: line for line in batch.lines}
    flags: list[dict[str, str]] = []
    for flag in answer:
        ident = str(flag.get("id"))
        where = ident if ident in by_id else f"?:{ident}"
        print(f"{where}: {str(flag.get('reason', '')).strip()}", flush=True)
        flags.append({"id": ident, "reason": str(flag.get("reason", "")).strip()})
    return flags, [line for line in batch.lines if line.id not in ids]


def report(results: Iterable[Result]) -> tuple[list[dict[str, str]], list[Line]]:
    """Print every flag and failed batch as it arrives; answer with the flags and passed lines, or raise ``Stopped``.

    A stop anywhere upstream reaches this loop through its ``for``, so one
    ``try`` covers every frame.
    """
    flags: list[dict[str, str]] = []
    passed: list[Line] = []
    names: list[str] = []
    try:
        for result in results:
            batch_flags, batch_passed = reported(result)
            flags.extend(batch_flags)
            passed.extend(batch_passed)
            names.append(result[0].name)
    except KeyboardInterrupt as exc:
        raise Stopped(flags, passed, names, "interrupted", True) from exc  # noqa: FBT003 — the dataclass field is positional
    except Exception as exc:
        reason = str(exc) or type(exc).__name__
        raise Stopped(flags, passed, names, reason, False) from exc  # noqa: FBT003 — the dataclass field is positional
    return flags, passed


def unfinished(
    batches: list[Batch], kept: list[Result], done: list[str]
) -> tuple[list[str], list[str]]:
    """The batches that failed, and those that got no answer before the run ended."""
    failed = [batch.name for batch, answer, _ in kept if answer is None]
    return failed, [batch.name for batch in batches if batch.name not in done]


def announce(failed: list[str], unjudged: list[str], stop: Stopped | None) -> None:
    """Print the batches that failed, those that got no answer, and why the run stopped."""
    for names, what in (
        (failed, "failed and were"),
        (unjudged, "got no answer and were"),
    ):
        if names:
            print(
                f"\n{len(names)} batch(es) {what} not judged: {', '.join(names)}",
                file=sys.stderr,
            )
    if stop is not None:
        print(f"run stopped: {stop.reason}", file=sys.stderr)


def exit_code(stop: Stopped | None, *, check: bool, found: bool) -> int:
    """130 on an interrupt and 1 on an exception, whatever ``--check`` says; else 1 only when checking and anything was found."""
    if stop is not None:
        return INTERRUPTED if stop.interrupted else 1
    return 1 if check and found else 0
