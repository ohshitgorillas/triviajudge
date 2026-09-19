"""The shared machinery both trivia gates run on: input, transport, verdict.

A gate is a prompt, a way of collecting candidates, and a decision about
whether the judge runs at ``Stop``. Everything else — reading what a change
added, calling the model, remembering what it passed, printing the verdict and
choosing the exit code — is the same for every gate and lives here.

Transport is one call per run carrying every candidate, over whichever backend
the judged repository names. ``claude`` is the default and runs the CLI in
print mode; ``local`` posts to an OpenAI-compatible server and asks it for a
schema-constrained answer. The model is small because the question is small
and the answer is a short list. Both backends reach the same validation, and a
transport that fails, or an answer that is not the JSON asked for, fails the
gate rather than passing it: a judge that cannot speak is not a judge that
approves.

The repository under judgment is found from the current working directory, not
from this file's own location, so an installed package judges the tree it is
run in.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

from triviajudge.config import settings

if TYPE_CHECKING:
    from collections.abc import Callable

CACHE_CAP = 20000

#: Seconds a local ``git`` call may take. It reads objects on this machine, so anything past this is a
#: wedged process rather than a slow one, and a hook that captures output has no way to say it is waiting.
GIT_TIMEOUT = 30

#: The two transports ``settings().backend`` names. Where under ``base_url`` the ``local``
#: one posts is ``chat_path`` in the same table, because the endpoint is a property of the
#: server rather than of the gate.
CLAUDE_BACKEND = "claude"
LOCAL_BACKEND = "local"

#: The answer's shape, sent as ``response_format`` so the server constrains decoding to it. A
#: small local model asked in prose alone answers with a preamble or a wrapper object often
#: enough to be unusable as a gate, and ``strict`` is what stops it inventing a third key.
FLAGS_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {"id": {"type": "string"}, "reason": {"type": "string"}},
        "required": ["id", "reason"],
        "additionalProperties": False,
    },
}
FLAGS_FORMAT = {"type": "json_schema", "json_schema": {"name": "flags", "strict": True, "schema": FLAGS_SCHEMA}}

#: Set in the environment of the judge's own ``claude`` call, and read by any gate the
#: inner session's hooks start. The inner session runs in the same working directory as
#: the outer one, so without it a hook mode that shells out to the CLI re-enters itself.
#: ``stop_hook_active`` cannot serve here: it marks the outer turn, not the inner process.
INNER = "TRIVIAJUDGE_INNER"

HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


class NotARepositoryError(RuntimeError):
    """Raised when the working directory is in no git work tree."""


@dataclass(frozen=True)
class Line:
    """One added line, addressed as the judge will echo it back."""

    path: str
    number: int
    text: str

    @property
    def id(self) -> str:
        """``path:line``, the id sent to the judge and printed on a flag."""
        return f"{self.path}:{self.number}"


def inner_session() -> bool:
    """Whether this process runs under a judge's own ``claude`` call, where a hook mode does nothing."""
    return bool(os.environ.get(INNER))


def binary(name: str) -> str:
    """Absolute path of a tool on PATH, or a RuntimeError naming what is missing."""
    if (path := shutil.which(name)) is None:
        raise RuntimeError(f"`{name}` not on PATH")
    return path


@cache
def root() -> Path:
    """The work tree the current directory sits in, or a NotARepositoryError naming that it does not."""
    cmd = [binary("git"), "rev-parse", "--show-toplevel"]
    proc = subprocess.run(  # noqa: S603 — argv is git's own path and two read-only flags, written here
        cmd, capture_output=True, text=True, check=False, timeout=GIT_TIMEOUT
    )
    if proc.returncode != 0:
        raise NotARepositoryError(f"{Path.cwd()} is in no git work tree; every input mode reads git objects")
    return Path(proc.stdout.strip())


def git(*args: str) -> str:
    """Stdout of a read-only git command run at the repository root."""
    cmd = [binary("git"), *args]
    finished = subprocess.run(  # noqa: S603 — argv is git's own path and the caller's read-only flags
        cmd, check=True, capture_output=True, text=True, cwd=root(), timeout=GIT_TIMEOUT
    )
    return finished.stdout


def git_diff(*args: str) -> str:
    """Zero-context diff, so every ``+`` line is an added line."""
    return git("diff", "-U0", "--no-color", *args)


def added_lines(diff: str) -> list[Line]:
    """Every added line in a unified diff, with the path and new-file line number."""
    out: list[Line] = []
    path = ""
    number = 0
    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            path = raw[4:].removeprefix("b/")
        elif match := HUNK.match(raw):
            number = int(match.group(1))
        elif raw.startswith("+"):
            out.append(Line(path, number, raw[1:]))
            number += 1
        elif not raw.startswith("-"):
            number += 1
    return out


def from_records(path: Path) -> list[Line]:
    """Calibration input: one ``path:line<TAB>text`` record per line."""
    out: list[Line] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        ident, _, text = raw.partition("\t")
        file, _, number = ident.rpartition(":")
        out.append(Line(file, int(number), text))
    return out


def ask(lines: list[Line], prompt: str, model: str | None = None, timeout: float | None = None) -> list[dict[str, str]]:
    """One call for every line; the parsed JSON array it answers with.

    ``model`` overrides the configured one, for a caller that asks a different
    judge than the gates do. ``timeout`` kills a call that never answers and
    reports it as a failure, for a caller that makes many calls and must not
    wait on one of them forever.

    The configured ``backend`` chooses the transport. An unknown one is a
    refusal rather than a fallback to the CLI: a judge nobody asked for is not
    the judge the repository asked for.
    """
    body = prompt + "\n\nLINES:\n" + "\n".join(f"{line.id}\t{line.text}" for line in lines)
    backend = settings().backend
    if backend == CLAUDE_BACKEND:
        return _ask_cli(body, model, timeout)
    if backend == LOCAL_BACKEND:
        return _ask_http(body, model, timeout)
    raise RuntimeError(f"unknown backend {backend!r}; it is {CLAUDE_BACKEND!r} or {LOCAL_BACKEND!r}")


def _ask_cli(body: str, model: str | None, timeout: float | None) -> list[dict[str, str]]:
    """Ask the ``claude`` CLI in print mode and parse the envelope it prints."""
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"} | {INNER: "1"}
    try:
        proc = subprocess.run(  # noqa: S603 — argv is judge_argv(), built from the configured model alone
            judge_argv(model),
            input=body,
            capture_output=True,
            text=True,
            env=env,
            cwd=root(),
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"claude did not answer within {timeout}s") from exc
    if proc.returncode != 0:
        raise RuntimeError(f"claude exited {proc.returncode}: {proc.stderr.strip() or proc.stdout.strip()}")
    return parsed(proc.stdout)


def _headers(api_key_env: str) -> dict[str, str]:
    """The request headers, carrying a bearer token when the table names a variable holding one."""
    headers = {"Content-Type": "application/json"}
    if api_key_env:
        token = os.environ.get(api_key_env, "")
        if not token:
            raise RuntimeError(f"api_key_env names {api_key_env}, which is unset")
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _ask_http(body: str, model: str | None, timeout: float | None) -> list[dict[str, str]]:
    """Ask an OpenAI-compatible server for a schema-constrained answer and parse what it sends."""
    conf = settings()
    if not conf.base_url:
        raise RuntimeError(f"backend {LOCAL_BACKEND!r} needs base_url, and the table names none")
    url = conf.base_url.rstrip("/") + "/" + conf.chat_path.lstrip("/")
    payload = {
        "model": model or conf.model,
        "messages": [{"role": "user", "content": body}],
        "temperature": 0,
        "response_format": FLAGS_FORMAT,
    }
    request = urllib.request.Request(  # noqa: S310 — base_url is the judged repository's own table, not input
        url, data=json.dumps(payload).encode("utf-8"), headers=_headers(conf.api_key_env), method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 — as above
            envelope = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        with exc:  # the error is itself the response, so reading its body also closes the handle
            raise RuntimeError(f"{url} answered {exc.code}: {exc.read().decode(errors='replace')[:200]}") from exc
    except OSError as exc:
        raise RuntimeError(f"{url} did not answer: {exc}") from exc
    return flags_from(_answer(envelope))


def _answer(envelope: dict[str, object]) -> str:
    """The assistant text inside a chat-completions envelope, or a RuntimeError naming what came."""
    if error := envelope.get("error"):
        raise RuntimeError(f"the server reported an error: {error}")
    choices = envelope.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("the server answered with no choices")
    message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
    return str(message.get("content", ""))


def judge_argv(model: str | None) -> list[str]:
    """The CLI call the judge is asked with: one turn, no tools, no settings, JSON out."""
    return [
        binary("claude"),
        "-p",
        "--model",
        model or settings().model,
        "--tools",
        "",
        "--setting-sources",
        "",
        "--no-session-persistence",
        "--output-format",
        "json",
    ]


def parsed(stdout: str) -> list[dict[str, str]]:
    """The flags inside the CLI's JSON envelope, or a RuntimeError naming what came back instead."""
    envelope = json.loads(stdout)
    if envelope.get("is_error"):
        raise RuntimeError(f"claude reported an error: {envelope.get('result')}")
    return flags_from(str(envelope.get("result", "")))


def flags_from(text: str) -> list[dict[str, str]]:
    """The flags one backend's answer text carries, fence and all.

    The envelope differs per backend and the judge's own text does not, so the
    fence strip and the list check are shared and the unwrap is not.
    """
    answer = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    flags = json.loads(answer)
    if not isinstance(flags, list):
        raise TypeError(f"judge answered with {type(flags).__name__}, not a list")
    return [dict(item) for item in flags]


def report(lines: list[Line], flags: list[dict[str, str]], out: TextIO) -> bool:
    """Print every flag against its line; whether anything was flagged."""
    by_id = {line.id: line for line in lines}
    for flag in flags:
        line = by_id.get(str(flag.get("id")))
        where = line.id if line else f"?:{flag.get('id')}"
        print(f"{where}: {flag.get('reason', '').strip()}", file=out)
        if line:
            print(f"    {line.text.strip()}", file=out)
    if flags:
        print(f"\n{len(flags)} line(s) narrate history. State what holds now, or delete the remark.", file=out)
    else:
        print(f"[ok] {len(lines)} line(s) state what holds now", file=out)
    return bool(flags)


def stop_already_ran() -> bool:
    """Read whether the Stop payload on stdin says this hook has already blocked this turn."""
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return False
    return bool(payload.get("stop_hook_active"))


def digest(line: Line) -> str:
    """Hash of the line's text alone, so a passed line stays passed wherever it moves."""
    return hashlib.sha1(line.text.strip().encode("utf-8"), usedforsecurity=False).hexdigest()


def clean_cache(cache_path: Path) -> list[str]:
    """Digests of lines the judge has already passed, oldest first; empty when there is no cache."""
    try:
        seen = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [str(item) for item in seen] if isinstance(seen, list) else []


def remember_clean(lines: list[Line], flags: list[dict[str, str]], cache_path: Path) -> None:
    """Append every line the judge passed to the cache, capped at the newest ``CACHE_CAP``."""
    flagged = {str(flag.get("id")) for flag in flags}
    seen = clean_cache(cache_path)
    known = set(seen)
    for line in lines:
        if line.id not in flagged and digest(line) not in known:
            seen.append(digest(line))
            known.add(digest(line))
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(seen[-CACHE_CAP:]) + "\n", encoding="utf-8")


@dataclass(frozen=True)
class Gate:
    """What one trivia gate brings to the shared run flow: its text, its input, its cache.

    ``cache`` is last and optional because a gate that does not judge at
    ``Stop`` never reaches the only call that writes one.
    """

    prompt: str
    collect: Callable[[argparse.Namespace], tuple[list[Line], list[str]]]
    empty: str
    judge_at_stop: bool
    cache: Path | None = None


def parse_args(doc: str, noun: str) -> argparse.Namespace:
    """Read the five input modes both trivia gates take."""
    parser = argparse.ArgumentParser(description=doc, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="*", help=f"staged {noun} (pre-commit)")
    parser.add_argument("--head", action="store_true", help=f"judge the {noun} HEAD added")
    parser.add_argument("--stop", action="store_true", help="judge the working tree; reads a Stop payload on stdin")
    parser.add_argument("--lines", help="calibration records, path:line<TAB>text")
    parser.add_argument("--out", help="write the judge's raw answer here")
    return parser.parse_args()


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


def screened(args: argparse.Namespace, gate: Gate, lines: list[Line], complaints: list[str], out: TextIO) -> int:
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
        flags = ask(lines, gate.prompt)
    except (RuntimeError, TypeError, ValueError, OSError) as exc:
        print(f"trivia judge unavailable, refusing to pass: {exc}", file=sys.stderr)
        return fail
    if args.out:
        Path(args.out).write_text(json.dumps(flags, indent=2) + "\n", encoding="utf-8")
    if args.stop and gate.cache is not None:
        remember_clean(lines, flags, gate.cache)
    return fail if report(lines, flags, out) else 0
