"""The engine both gates run on: diff reading, the clean-line cache, the root, the verdict.

``triviajudge.core`` is the half of the old markdown gate that has nothing to
do with markdown. Four seams are exercised here.

``added_lines(diff)`` turns a zero-context unified diff into the lines it adds,
carrying the path and the new-file line number. Its numbering is the part that
breaks silently: a hunk header resets it, a removed line does not advance it,
and an unchanged line does.

``digest``, ``clean_cache`` and ``remember_clean`` are the cache. A digest is
taken over the line's stripped text alone, so a line the judge passed stays
passed after it moves. A cache that is absent, unreadable or holding something
other than a list reads as empty rather than raising, because a gate that
cannot read its cache should judge, not fail.

``Gate`` carries an optional cache, and ``judged`` writes one only under
``--stop`` and only when the field is set, which is what lets a gate that does
not judge at ``Stop`` carry none at all.

``root()`` answers with the work tree the current directory sits in, and raises
``NotARepositoryError`` outside one rather than inferring a tree.
"""

import io
import json
import os
import subprocess
import sys
import urllib.error
from email.message import Message
from pathlib import Path
from typing import cast

import pytest

from triviajudge import core
from triviajudge.config import Settings

EMPTY_DIFF = ""

ONE_ADDED_LINE = (
    "diff --git a/doc.md b/doc.md\n"
    "--- a/doc.md\n"
    "+++ b/doc.md\n"
    "@@ -0,0 +1 @@\n"
    "+the resampler runs at the rate the panel asks for\n"
)

TWO_FILES_TWO_HUNKS = (
    "diff --git a/one.md b/one.md\n"
    "--- a/one.md\n"
    "+++ b/one.md\n"
    "@@ -0,0 +4 @@\n"
    "+first added line\n"
    "+second added line\n"
    "diff --git a/two.md b/two.md\n"
    "--- a/two.md\n"
    "+++ b/two.md\n"
    "@@ -0,0 +9 @@\n"
    "+third added line\n"
)

A_REMOVAL_BESIDE_AN_ADDITION = (
    "diff --git a/doc.md b/doc.md\n"
    "--- a/doc.md\n"
    "+++ b/doc.md\n"
    "@@ -3,2 +3,1 @@\n"
    "-the line that went away\n"
    "+the line that stands now\n"
)


def ids_of(diff: str) -> list[str]:
    """The ``path:line`` of every line the diff adds."""
    return [line.id for line in core.added_lines(diff)]


# --- behavior 1: a diff becomes the lines it adds, addressed by new-file number ---


@pytest.mark.parametrize(
    ("diff", "ids"),
    [
        (EMPTY_DIFF, []),
        (ONE_ADDED_LINE, ["doc.md:1"]),
        (TWO_FILES_TWO_HUNKS, ["one.md:4", "one.md:5", "two.md:9"]),
        (A_REMOVAL_BESIDE_AN_ADDITION, ["doc.md:3"]),
    ],
)
def test_the_added_lines_of_a_diff_carry_their_new_file_numbers(diff: str, ids: list[str]) -> None:
    assert ids_of(diff) == ids


# --- behavior 2: a digest follows the text, not the place ---------------------


def test_the_same_text_at_two_addresses_has_one_digest() -> None:
    here = core.Line("one.md", 4, "  the rate the panel asks for  ")
    moved = core.Line("other.md", 91, "the rate the panel asks for")
    assert core.digest(here) == core.digest(moved)


def test_different_text_has_a_different_digest() -> None:
    assert core.digest(core.Line("a.md", 1, "one")) != core.digest(core.Line("a.md", 1, "two"))


# --- behavior 3: an unreadable cache reads as empty, never as an error --------


@pytest.mark.parametrize(
    ("content", "seen"),
    [
        (None, []),
        ("not json at all", []),
        ('{"digests": []}', []),
        ('["abc", "def"]', ["abc", "def"]),
    ],
)
def test_the_clean_cache_reads_as_empty_unless_it_holds_a_list(
    tmp_path: Path, content: str | None, seen: list[str]
) -> None:
    cache = tmp_path / "clean.json"
    if content is not None:
        cache.write_text(content, encoding="utf-8")
    assert core.clean_cache(cache) == seen


# --- behavior 4: what the judge passed is remembered, what it flagged is not --


def test_only_the_lines_the_judge_passed_reach_the_cache(tmp_path: Path) -> None:
    cache = tmp_path / "nested" / "clean.json"
    passed = core.Line("doc.md", 1, "the rate the panel asks for")
    flagged = core.Line("doc.md", 2, "approved 2026-07-04")
    core.remember_clean([passed, flagged], [{"id": "doc.md:2", "reason": "dated event"}], cache)
    assert json.loads(cache.read_text(encoding="utf-8")) == [core.digest(passed)]


def test_the_cache_keeps_only_the_newest_entries(tmp_path: Path) -> None:
    cache = tmp_path / "clean.json"
    cache.write_text(json.dumps([f"old-{n}" for n in range(core.CACHE_CAP)]) + "\n", encoding="utf-8")
    core.remember_clean([core.Line("doc.md", 1, "a line the judge passed")], [], cache)
    assert len(json.loads(cache.read_text(encoding="utf-8"))) == core.CACHE_CAP


# --- behavior 5: a gate carries a cache only if it has one -------------------


def test_a_gate_declares_no_cache_by_default() -> None:
    gate = core.Gate("prompt", lambda _args: ([], []), "[ok] nothing added", judge_at_stop=False)
    assert gate.cache is None


# --- behavior 6: the root is the tree the cwd sits in, or a refusal ----------


def test_the_root_is_the_work_tree_the_directory_sits_in(tmp_path: Path) -> None:
    git = os.environ.get("GIT", "git")
    subprocess.run([git, "init", "-q", str(tmp_path / "repo")], check=True, capture_output=True)
    inside = tmp_path / "repo" / "deep" / "deeper"
    inside.mkdir(parents=True)
    core.root.cache_clear()
    cwd = Path.cwd()
    try:
        os.chdir(inside)
        assert core.root().resolve() == (tmp_path / "repo").resolve()
    finally:
        os.chdir(cwd)
        core.root.cache_clear()


def test_a_directory_in_no_work_tree_is_refused_rather_than_inferred(tmp_path: Path) -> None:
    outside = tmp_path / "bare"
    outside.mkdir()
    core.root.cache_clear()
    cwd = Path.cwd()
    try:
        os.chdir(outside)
        with pytest.raises(core.NotARepositoryError):
            core.root()
    finally:
        os.chdir(cwd)
        core.root.cache_clear()


# --- behavior 7: a calibration record is one line, addressed as the judge sees it ---


def test_a_record_carries_the_path_the_number_and_the_text(tmp_path: Path) -> None:
    records = tmp_path / "lines.tsv"
    records.write_text("docs/plan.md:12\tthe panel holds the staged rate\n", encoding="utf-8")
    assert core.from_records(records) == [core.Line("docs/plan.md", 12, "the panel holds the staged rate")]


# --- behavior 8: a call that does not answer is a refusal, never a pass ------


def refusing_run(**answer: object) -> object:
    """A ``subprocess.run`` stand-in answering with one fixed result."""

    class Finished:
        returncode = int(str(answer.get("returncode", 0)))
        stdout = str(answer.get("stdout", ""))
        stderr = str(answer.get("stderr", ""))

    def run(*_args: object, **_kwargs: object) -> Finished:
        return Finished()

    return run


def test_a_call_that_never_answers_is_a_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    def expire(*_args: object, **_kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="claude", timeout=600)

    monkeypatch.setattr("triviajudge.core.binary", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("triviajudge.core.root", Path.cwd)
    monkeypatch.setattr("triviajudge.core.subprocess.run", expire)
    with pytest.raises(RuntimeError, match="did not answer within 600s"):
        core.ask([core.Line("doc.md", 1, "a line")], "prompt", timeout=600)


def test_a_call_that_exits_nonzero_is_a_refusal_naming_what_it_said(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("triviajudge.core.binary", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("triviajudge.core.root", Path.cwd)
    monkeypatch.setattr("triviajudge.core.subprocess.run", refusing_run(returncode=1, stderr="no credit"))
    with pytest.raises(RuntimeError, match="claude exited 1: no credit"):
        core.ask([core.Line("doc.md", 1, "a line")], "prompt")


# --- behavior 9: the envelope is read, and anything but a flag list is refused ---


def test_a_fenced_answer_is_read_as_the_flag_list_it_wraps() -> None:
    envelope = json.dumps({"result": '```json\n[{"id": "doc.md:1", "reason": "narrates a decision"}]\n```'})
    assert core.parsed(envelope) == [{"id": "doc.md:1", "reason": "narrates a decision"}]


def test_an_error_envelope_is_a_refusal() -> None:
    with pytest.raises(RuntimeError, match="claude reported an error: over quota"):
        core.parsed(json.dumps({"is_error": True, "result": "over quota"}))


def test_an_answer_that_is_not_a_list_is_a_refusal() -> None:
    with pytest.raises(RuntimeError, match="judge answered with dict, not a list"):
        core.parsed(json.dumps({"result": '{"id": "doc.md:1"}'}))


# --- behavior 10: a flag naming no line is still printed -----------------------


def test_a_flag_naming_no_line_is_printed_against_its_id(capsys: pytest.CaptureFixture[str]) -> None:
    core.report([core.Line("doc.md", 1, "a line")], [{"id": "gone.md:9", "reason": "narrates"}], sys.stdout)
    assert "?:gone.md:9: narrates" in capsys.readouterr().out


def test_nothing_flagged_says_how_many_lines_hold_now(capsys: pytest.CaptureFixture[str]) -> None:
    core.report([core.Line("doc.md", 1, "a line")], [], sys.stdout)
    assert "[ok] 1 line(s) state what holds now" in capsys.readouterr().out


# --- behavior 11: a Stop payload that is not JSON is not a second run ---------


@pytest.mark.parametrize(("stdin", "already"), [("", False), ("{}", False), ('{"stop_hook_active": true}', True)])
def test_the_stop_payload_decides_whether_this_hook_already_blocked(
    stdin: str, already: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
    assert core.stop_already_ran() is already


# --- behavior 12: the configured backend chooses the transport ----------------


def local_settings(**over: object) -> object:
    """A settings stand-in on the ``local`` backend, overridable per field."""
    fields: dict[str, object] = {"backend": "local", "base_url": "http://127.0.0.1:8080", "api_key_env": ""}
    fields.update(over)
    return lambda: Settings(**fields)  # type: ignore[arg-type]


class Answer:
    """A ``urlopen`` answer carrying one raw body."""

    def __init__(self, body: str) -> None:
        self.body = body

    def __enter__(self) -> "Answer":
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
            sent["url"] = request.full_url  # type: ignore[attr-defined]
            sent["headers"] = dict(request.headers)  # type: ignore[attr-defined]
            sent["payload"] = json.loads(request.data.decode("utf-8"))  # type: ignore[attr-defined]
            sent["timeout"] = timeout
        return Answer(envelope)

    return urlopen


def test_the_local_backend_posts_the_question_and_reads_the_array_back(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, object] = {}
    monkeypatch.setattr("triviajudge.core.settings", local_settings())
    monkeypatch.setattr(
        "triviajudge.core.urllib.request.urlopen",
        answering_post('[{"id": "doc.md:1", "reason": "narrates a decision"}]', sent),
    )
    flags = core.ask([core.Line("doc.md", 1, "a line")], "prompt", model="qwen3-4b", timeout=30)
    assert flags == [{"id": "doc.md:1", "reason": "narrates a decision"}]
    assert sent["url"] == "http://127.0.0.1:8080/v1/chat/completions"
    assert sent["timeout"] == 30
    payload = cast("dict[str, object]", sent["payload"])
    assert payload["model"] == "qwen3-4b"
    assert payload["response_format"]["type"] == "json_schema"  # type: ignore[index]
    assert "doc.md:1\ta line" in payload["messages"][0]["content"]  # type: ignore[index]


def test_the_table_names_where_under_base_url_the_question_is_posted(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, object] = {}
    monkeypatch.setattr(
        "triviajudge.core.settings",
        local_settings(base_url="https://example.invalid/v1beta/openai", chat_path="chat/completions"),
    )
    monkeypatch.setattr("triviajudge.core.urllib.request.urlopen", answering_post("[]", sent))
    assert core.ask([core.Line("doc.md", 1, "a line")], "prompt") == []
    assert sent["url"] == "https://example.invalid/v1beta/openai/chat/completions"


def test_a_fenced_local_answer_is_read_as_the_flag_list_it_wraps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("triviajudge.core.settings", local_settings())
    monkeypatch.setattr(
        "triviajudge.core.urllib.request.urlopen",
        answering_post('```json\n[{"id": "doc.md:1", "reason": "narrates"}]\n```'),
    )
    assert core.ask([core.Line("doc.md", 1, "a line")], "prompt") == [{"id": "doc.md:1", "reason": "narrates"}]


def test_a_local_answer_that_is_not_a_list_is_a_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("triviajudge.core.settings", local_settings())
    monkeypatch.setattr("triviajudge.core.urllib.request.urlopen", answering_post('{"id": "doc.md:1"}'))
    with pytest.raises(RuntimeError, match="judge answered with dict, not a list"):
        core.ask([core.Line("doc.md", 1, "a line")], "prompt")


def test_a_non_200_is_a_refusal_naming_the_code(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_args: object, **_kwargs: object) -> None:
        raise urllib.error.HTTPError(
            "http://127.0.0.1:8080/v1/chat/completions",
            503,
            "Service Unavailable",
            Message(),
            io.BytesIO(b"no model loaded"),
        )

    monkeypatch.setattr("triviajudge.core.settings", local_settings())
    monkeypatch.setattr("triviajudge.core.urllib.request.urlopen", refuse)
    with pytest.raises(RuntimeError, match="answered 503: no model loaded"):
        core.ask([core.Line("doc.md", 1, "a line")], "prompt")


def test_a_dead_socket_is_a_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_args: object, **_kwargs: object) -> None:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("triviajudge.core.settings", local_settings())
    monkeypatch.setattr("triviajudge.core.urllib.request.urlopen", refuse)
    with pytest.raises(RuntimeError, match="did not answer: "):
        core.ask([core.Line("doc.md", 1, "a line")], "prompt")


def test_an_envelope_carrying_an_error_is_a_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("triviajudge.core.settings", local_settings())
    monkeypatch.setattr(
        "triviajudge.core.urllib.request.urlopen", raw_post(json.dumps({"error": {"message": "context length"}}))
    )
    with pytest.raises(RuntimeError, match="the server reported an error"):
        core.ask([core.Line("doc.md", 1, "a line")], "prompt")


def test_an_envelope_carrying_no_choices_is_a_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("triviajudge.core.settings", local_settings())
    monkeypatch.setattr("triviajudge.core.urllib.request.urlopen", raw_post(json.dumps({})))
    with pytest.raises(RuntimeError, match="answered with no choices"):
        core.ask([core.Line("doc.md", 1, "a line")], "prompt")


def test_the_token_variable_is_sent_as_a_bearer_header(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, object] = {}
    monkeypatch.setenv("JUDGE_TOKEN", "sk-local")
    monkeypatch.setattr("triviajudge.core.settings", local_settings(api_key_env="JUDGE_TOKEN"))
    monkeypatch.setattr("triviajudge.core.urllib.request.urlopen", answering_post("[]", sent))
    core.ask([core.Line("doc.md", 1, "a line")], "prompt")
    assert cast("dict[str, str]", sent["headers"])["Authorization"] == "Bearer sk-local"


def test_a_token_variable_that_is_unset_is_a_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JUDGE_TOKEN", raising=False)
    monkeypatch.setattr("triviajudge.core.settings", local_settings(api_key_env="JUDGE_TOKEN"))
    with pytest.raises(RuntimeError, match="api_key_env names JUDGE_TOKEN, which is unset"):
        core.ask([core.Line("doc.md", 1, "a line")], "prompt")


def test_the_local_backend_without_a_base_url_is_a_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("triviajudge.core.settings", local_settings(base_url=""))
    with pytest.raises(RuntimeError, match="needs base_url"):
        core.ask([core.Line("doc.md", 1, "a line")], "prompt")


def test_an_unknown_backend_is_a_refusal_rather_than_the_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("triviajudge.core.settings", lambda: Settings(backend="ollama"))
    with pytest.raises(RuntimeError, match="unknown backend 'ollama'"):
        core.ask([core.Line("doc.md", 1, "a line")], "prompt")
