"""One call to the judge, over whichever backend the judged repository names.

Transport is one call carrying the lines it is handed. ``claude`` is the default
and runs the CLI in print mode; ``local`` posts to an OpenAI-compatible server
and asks it for a schema-constrained answer. The model is small because the
question is small and the answer is a short list. Both backends reach the same
validation, and a transport that fails, or an answer that is not the JSON asked
for, fails the gate rather than passing it: a judge that cannot speak is not a
judge that approves.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from typing import TYPE_CHECKING

from triviajudge.config import settings
from triviajudge.core import INNER, Line, binary, root

if TYPE_CHECKING:
    from collections.abc import Mapping

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
FLAGS_FORMAT = {
    "type": "json_schema",
    "json_schema": {"name": "flags", "strict": True, "schema": FLAGS_SCHEMA},
}

#: The exhaustive answer's shape, one object per input id. ``strict`` is what makes the
#: sparse schema above unusable here: it forbids the ``verdict`` key outright, so a gate
#: reading verdicts against that schema is answered without one and flags nothing at all.
VERDICTS_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "verdict": {"type": "string"},
            "reason": {"type": "string"},
        },
        "required": ["id", "verdict", "reason"],
        "additionalProperties": False,
    },
}
VERDICTS_JSON = {"name": "verdicts", "strict": True, "schema": VERDICTS_SCHEMA}
VERDICTS_FORMAT = {"type": "json_schema", "json_schema": VERDICTS_JSON}


def ask(
    lines: list[Line],
    prompt: str,
    model: str | None = None,
    timeout: float | None = None,
    *,
    exhaustive: bool = False,
) -> list[dict[str, str]]:
    """One call for every line; the parsed JSON array it answers with.

    ``model`` overrides the configured one, for a caller that asks a different
    judge than the gates do. ``timeout`` kills a call that never answers and
    reports it as a failure, for a caller that makes many calls and must not
    wait on one of them forever. ``exhaustive`` says the prompt asks for one
    verdict per input id, which the constrained backend has to be told: the
    schema it sends is what decides whether a ``verdict`` key can come back.

    The configured ``backend`` chooses the transport. An unknown one is a
    refusal rather than a fallback to the CLI: a judge nobody asked for is not
    the judge the repository asked for.
    """
    body = (
        prompt + "\n\nLINES:\n" + "\n".join(f"{line.id}\t{line.text}" for line in lines)
    )
    backend = settings().backend
    if backend == CLAUDE_BACKEND:
        return _ask_cli(body, model, timeout)
    if backend == LOCAL_BACKEND:
        return _ask_http(
            body, model, timeout, VERDICTS_FORMAT if exhaustive else FLAGS_FORMAT
        )
    raise RuntimeError(
        f"unknown backend {backend!r}; it is {CLAUDE_BACKEND!r} or {LOCAL_BACKEND!r}"
    )


def _ask_cli(
    body: str, model: str | None, timeout: float | None
) -> list[dict[str, str]]:
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
        raise RuntimeError(
            f"claude exited {proc.returncode}: {proc.stderr.strip() or proc.stdout.strip()}"
        )
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


def _ask_http(
    body: str,
    model: str | None,
    timeout: float | None,
    answer_format: Mapping[str, object],
) -> list[dict[str, str]]:
    """Ask an OpenAI-compatible server for a schema-constrained answer and parse what it sends."""
    conf = settings()
    if not conf.base_url:
        raise RuntimeError(
            f"backend {LOCAL_BACKEND!r} needs base_url, and the table names none"
        )
    url = conf.base_url.rstrip("/") + "/" + conf.chat_path.lstrip("/")
    payload = {
        "model": model or conf.model,
        "messages": [{"role": "user", "content": body}],
        "temperature": 0,
        "response_format": answer_format,
    }
    request = urllib.request.Request(  # noqa: S310 — base_url is the judged repository's own table, not input
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=_headers(conf.api_key_env),
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 — as above
            envelope = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        with exc:  # the error is itself the response, so reading its body also closes the handle
            raise RuntimeError(
                f"{url} answered {exc.code}: {exc.read().decode(errors='replace')[:200]}"
            ) from exc
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
