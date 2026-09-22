"""The call to the judge: the backend it goes to, the answer it reads back.

``triviajudge.transport`` is the half of the engine that talks to a model.
Three seams are exercised here.

``ask`` on the ``claude`` backend runs the CLI. A call that times out or exits
nonzero is a refusal, never an empty flag list, because a judge that did not
answer has passed nothing.

``parsed`` reads the CLI's JSON envelope. An answer fenced in markdown is read
as the list it wraps; an error envelope, or an answer that is anything but a
list, is refused.

``ask`` on the ``local`` backend posts a chat-completions request to the
configured ``base_url``, carrying the model, the timeout, a schema-shaped
response format and a bearer token when a variable is named. A non-200, a dead
socket, an envelope carrying an error or no choices, an unset token variable, a
missing ``base_url`` and an unknown backend are each a refusal rather than a
fall back to the CLI.

A refusal is matched on the value the test put in — the timeout it asked for,
the stderr its fake wrote, the variable name it named — never on the sentence
the gate wraps around it.
"""

import io
import json
import subprocess
import urllib.error
from email.message import Message
from pathlib import Path
from typing import Self, cast

import pytest

from triviajudge import core, transport
from triviajudge.config import Settings

# --- behavior 1: a call that does not answer is a refusal, never a pass ------


def refusing_run(**answer: object) -> object:
    """A ``subprocess.run`` stand-in answering with one fixed result."""

    class Finished:
        returncode = int(str(answer.get("returncode", 0)))
        stdout = str(answer.get("stdout", ""))
        stderr = str(answer.get("stderr", ""))

    def run(*_args: object, **_kwargs: object) -> Finished:
        return Finished()

    return run


def test_a_call_that_never_answers_is_a_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def expire(*_args: object, **_kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="claude", timeout=600)

    monkeypatch.setattr("triviajudge.transport.binary", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("triviajudge.transport.root", Path.cwd)
    monkeypatch.setattr("triviajudge.transport.settings", Settings)
    monkeypatch.setattr("triviajudge.transport.subprocess.run", expire)
    with pytest.raises(RuntimeError, match="600s"):
        transport.ask([core.Line("doc.md", 1, "a line")], "prompt", timeout=600)


def test_a_call_that_exits_nonzero_is_a_refusal_naming_what_it_said(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("triviajudge.transport.binary", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("triviajudge.transport.root", Path.cwd)
    monkeypatch.setattr("triviajudge.transport.settings", Settings)
    monkeypatch.setattr(
        "triviajudge.transport.subprocess.run",
        refusing_run(returncode=1, stderr="no credit"),
    )
    with pytest.raises(RuntimeError, match="no credit"):
        transport.ask([core.Line("doc.md", 1, "a line")], "prompt")


# --- behavior 2: the envelope is read, and anything but a flag list is refused ---


def test_a_fenced_answer_is_read_as_the_flag_list_it_wraps() -> None:
    envelope = json.dumps(
        {
            "result": '```json\n[{"id": "doc.md:1", "reason": "narrates a decision"}]\n```'
        }
    )
    assert transport.parsed(envelope) == [
        {"id": "doc.md:1", "reason": "narrates a decision"}
    ]


def test_an_error_envelope_is_a_refusal() -> None:
    with pytest.raises(RuntimeError, match="over quota"):
        transport.parsed(json.dumps({"is_error": True, "result": "over quota"}))


def test_an_answer_that_is_not_a_list_is_a_refusal() -> None:
    with pytest.raises(TypeError, match="dict"):
        transport.parsed(json.dumps({"result": '{"id": "doc.md:1"}'}))


# --- behavior 3: the configured backend chooses the transport ----------------


def local_settings(**over: object) -> object:
    """A settings stand-in on the ``local`` backend, overridable per field."""
    fields: dict[str, object] = {
        "backend": "local",
        "base_url": "http://127.0.0.1:8080",
        "api_key_env": "",
    }
    fields.update(over)
    return lambda: Settings(**fields)  # type: ignore[arg-type]  # — the case names its own fields


class Answer:
    """A ``urlopen`` answer carrying one raw body."""

    def __init__(self, body: str) -> None:
        self.body = body

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body.encode("utf-8")


def raw_post(body: str) -> object:
    """A ``urlopen`` stand-in answering with one body verbatim, envelope and all."""
    return lambda *_args, **_kwargs: Answer(body)


def answering_post(body: str, sent: dict[str, object] | None = None) -> object:
    """A ``urlopen`` stand-in answering with one chat-completions envelope, keeping the request."""
    envelope = json.dumps({"choices": [{"message": {"content": body}}]})

    def urlopen(request: object, timeout: float | None = None) -> Answer:
        if sent is not None:
            sent["url"] = request.full_url  # type: ignore[attr-defined]  # — a Request reaches the fake
            sent["headers"] = dict(request.headers)  # type: ignore[attr-defined]  # — as above
            sent["payload"] = json.loads(request.data.decode("utf-8"))  # type: ignore[attr-defined]  # — as above
            sent["timeout"] = timeout
        return Answer(envelope)

    return urlopen


ONE_FLAG = '[{"id": "doc.md:1", "reason": "narrates a decision"}]'


def local_call(
    monkeypatch: pytest.MonkeyPatch, body: str, sent: dict[str, object]
) -> list[dict[str, str]]:
    """One ``ask`` over the local backend, keeping what the request carried in ``sent``."""
    monkeypatch.setattr("triviajudge.transport.settings", local_settings())
    monkeypatch.setattr(
        "triviajudge.transport.urllib.request.urlopen", answering_post(body, sent)
    )
    return transport.ask(
        [core.Line("doc.md", 1, "a line")], "prompt", model="qwen3-4b", timeout=30
    )


def sent_payload(sent: dict[str, object]) -> dict[str, object]:
    """The JSON body of the request the local backend posted."""
    return cast("dict[str, object]", sent["payload"])


def test_the_local_backend_reads_the_array_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert local_call(monkeypatch, ONE_FLAG, {}) == [
        {"id": "doc.md:1", "reason": "narrates a decision"}
    ]


def test_the_local_backend_posts_to_the_chat_completions_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: dict[str, object] = {}
    local_call(monkeypatch, ONE_FLAG, sent)
    assert sent["url"] == "http://127.0.0.1:8080/v1/chat/completions"


def test_the_timeout_the_caller_asked_for_reaches_the_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: dict[str, object] = {}
    local_call(monkeypatch, ONE_FLAG, sent)
    assert sent["timeout"] == 30


def test_the_payload_names_the_model_the_caller_asked_for(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: dict[str, object] = {}
    local_call(monkeypatch, ONE_FLAG, sent)
    assert sent_payload(sent)["model"] == "qwen3-4b"


def test_the_payload_asks_the_server_for_a_schema_shaped_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: dict[str, object] = {}
    local_call(monkeypatch, ONE_FLAG, sent)
    assert sent_payload(sent)["response_format"]["type"] == "json_schema"  # type: ignore[index]  # — a JSON envelope


def test_the_payload_carries_the_lines_to_judge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: dict[str, object] = {}
    local_call(monkeypatch, ONE_FLAG, sent)
    assert "doc.md:1\ta line" in sent_payload(sent)["messages"][0]["content"]  # type: ignore[index]  # — as above


def test_the_table_names_where_under_base_url_the_question_is_posted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: dict[str, object] = {}
    monkeypatch.setattr(
        "triviajudge.transport.settings",
        local_settings(
            base_url="https://example.invalid/v1beta/openai",
            chat_path="chat/completions",
        ),
    )
    monkeypatch.setattr(
        "triviajudge.transport.urllib.request.urlopen", answering_post("[]", sent)
    )
    transport.ask([core.Line("doc.md", 1, "a line")], "prompt")
    assert sent["url"] == "https://example.invalid/v1beta/openai/chat/completions"


def test_a_fenced_local_answer_is_read_as_the_flag_list_it_wraps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("triviajudge.transport.settings", local_settings())
    monkeypatch.setattr(
        "triviajudge.transport.urllib.request.urlopen",
        answering_post('```json\n[{"id": "doc.md:1", "reason": "narrates"}]\n```'),
    )
    assert transport.ask([core.Line("doc.md", 1, "a line")], "prompt") == [
        {"id": "doc.md:1", "reason": "narrates"}
    ]


def test_a_local_answer_that_is_not_a_list_is_a_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("triviajudge.transport.settings", local_settings())
    monkeypatch.setattr(
        "triviajudge.transport.urllib.request.urlopen",
        answering_post('{"id": "doc.md:1"}'),
    )
    with pytest.raises(TypeError, match="dict"):
        transport.ask([core.Line("doc.md", 1, "a line")], "prompt")


def test_a_non_200_is_a_refusal_naming_the_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(*_args: object, **_kwargs: object) -> None:
        raise urllib.error.HTTPError(
            "http://127.0.0.1:8080/v1/chat/completions",
            503,
            "Service Unavailable",
            Message(),
            io.BytesIO(b"no model loaded"),
        )

    monkeypatch.setattr("triviajudge.transport.settings", local_settings())
    monkeypatch.setattr("triviajudge.transport.urllib.request.urlopen", refuse)
    with pytest.raises(RuntimeError, match="503"):
        transport.ask([core.Line("doc.md", 1, "a line")], "prompt")


def test_a_dead_socket_is_a_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_args: object, **_kwargs: object) -> None:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("triviajudge.transport.settings", local_settings())
    monkeypatch.setattr("triviajudge.transport.urllib.request.urlopen", refuse)
    with pytest.raises(RuntimeError, match="connection refused"):
        transport.ask([core.Line("doc.md", 1, "a line")], "prompt")


def test_an_envelope_carrying_an_error_is_a_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("triviajudge.transport.settings", local_settings())
    monkeypatch.setattr(
        "triviajudge.transport.urllib.request.urlopen",
        raw_post(json.dumps({"error": {"message": "context length"}})),
    )
    with pytest.raises(RuntimeError, match="context length"):
        transport.ask([core.Line("doc.md", 1, "a line")], "prompt")


def test_an_envelope_carrying_no_choices_is_a_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("triviajudge.transport.settings", local_settings())
    monkeypatch.setattr(
        "triviajudge.transport.urllib.request.urlopen", raw_post(json.dumps({}))
    )
    with pytest.raises(RuntimeError, match="choices"):
        transport.ask([core.Line("doc.md", 1, "a line")], "prompt")


def test_the_token_variable_is_sent_as_a_bearer_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: dict[str, object] = {}
    credential = "sk-local"
    monkeypatch.setenv("JUDGE_TOKEN", credential)
    monkeypatch.setattr(
        "triviajudge.transport.settings", local_settings(api_key_env="JUDGE_TOKEN")
    )
    monkeypatch.setattr(
        "triviajudge.transport.urllib.request.urlopen", answering_post("[]", sent)
    )
    transport.ask([core.Line("doc.md", 1, "a line")], "prompt")
    assert (
        cast("dict[str, str]", sent["headers"])["Authorization"]
        == f"Bearer {credential}"
    )


def test_a_token_variable_that_is_unset_is_a_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("JUDGE_TOKEN", raising=False)
    monkeypatch.setattr(
        "triviajudge.transport.settings", local_settings(api_key_env="JUDGE_TOKEN")
    )
    with pytest.raises(RuntimeError, match="JUDGE_TOKEN"):
        transport.ask([core.Line("doc.md", 1, "a line")], "prompt")


def test_the_local_backend_without_a_base_url_is_a_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("triviajudge.transport.settings", local_settings(base_url=""))
    with pytest.raises(RuntimeError, match="base_url"):
        transport.ask([core.Line("doc.md", 1, "a line")], "prompt")


def test_an_unknown_backend_is_a_refusal_rather_than_the_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "triviajudge.transport.settings", lambda: Settings(backend="ollama")
    )
    with pytest.raises(RuntimeError, match="ollama"):
        transport.ask([core.Line("doc.md", 1, "a line")], "prompt")
