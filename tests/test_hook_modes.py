"""The three hook modes: the archaeology payload mode, the recursion guard, the markdown switch.

Three seams are exercised here, each the way a hook drives it.

``triviajudge-archaeology --post-tool-use`` takes a ``PostToolUse`` payload on
stdin and checks the lines the working tree adds to the one file
``tool_input.file_path`` names. Added lines are the scope, so a phrase sitting
in ``HEAD`` is not the running agent's to answer for; a suffix the gate cannot
read a comment out of, a payload naming no file, and a payload that is not
JSON are each a pass rather than an error, because a ``PostToolUse`` hook
blocks the turn on what it can prove and nothing else.

``core.INNER`` is the recursion guard. The markdown judge shells out to the
``claude`` CLI from inside a ``Stop`` hook, and the inner session shares the
working directory, so its own ``Stop`` hooks fire the same gate. ``transport.ask`` sets
the variable in the child's environment and every hook mode reads it and does
nothing, which ``stop_hook_active`` cannot do: that flag marks the outer turn,
not the inner process.

``md_judge_at_stop`` decides whether the markdown gate calls the judge at
``Stop`` at all. False makes the hook a no-op and leaves the commit and HEAD
modes as the gate.

Every phrase fed to a gate lives in a string literal, never in a comment or
docstring of this file, so this file is clean by the rule it pins.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest
from conftest import coverage_environment

from triviajudge import core, transport

REPO_ROOT = Path(__file__).resolve().parents[1]

GIT = shutil.which("git")

DATED_COMMENT = "value = 1  # approved 2026-07-04\n"
CLEAN_COMMENT = "other = 2  # the lane returns the staged model\n"
DATED_MARKDOWN = "the hand-back passed on 2026-07-04\n"

#: The root-level settings file, named once so every mode reads the same name.
SETTINGS_FILE = ".triviajudge.toml"


def child_environment(tmp_path: Path) -> dict[str, str]:
    """An environment whose PATH carries git and nothing else, so ``claude`` is missing."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    link = bin_dir / "git"
    if not link.exists():
        link.symlink_to(str(GIT))
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    return {
        **coverage_environment(),
        "PATH": str(bin_dir),
        "HOME": str(home),
        "LC_ALL": "C",
        "PYTHONPATH": str(REPO_ROOT),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_AUTHOR_NAME": "hook mode probe",
        "GIT_AUTHOR_EMAIL": "probe@example.invalid",
        "GIT_COMMITTER_NAME": "hook mode probe",
        "GIT_COMMITTER_EMAIL": "probe@example.invalid",
    }


def git_run(root: Path, env: dict[str, str], *args: str) -> None:
    """Run one git command in the throwaway checkout, resolving git from that environment's PATH."""
    subprocess.run(
        ["/usr/bin/env", "git", *args],
        cwd=root,
        env=env,
        check=True,
        capture_output=True,
    )


def write(root: Path, files: dict[str, str]) -> None:
    """Put every named file into the checkout, making the directories it needs."""
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def committed_repo(
    tmp_path: Path, files: dict[str, str]
) -> tuple[Path, dict[str, str]]:
    """A throwaway checkout, a different work tree from the package's own, holding ``files`` in one commit."""
    if GIT is None:
        pytest.skip("git is not on PATH, so no checkout can be presented to the gate")
    env = child_environment(tmp_path)
    root = tmp_path / "repo"
    root.mkdir()
    git_run(root, env, "init", "-q")
    write(root, {"baseline.txt": "baseline\n", **files})
    git_run(root, env, "add", "-A")
    git_run(root, env, "commit", "-qm", "baseline")
    return root, env


def payload_for(root: Path, name: str | None) -> str:
    """The stdin a ``PostToolUse`` hook receives after an edit to ``name``, or one naming no file."""
    body: dict[str, object] = {"hook_event_name": "PostToolUse", "tool_name": "Edit"}
    if name is not None:
        body["tool_input"] = {"file_path": str(root / name)}
    return json.dumps(body)


def gate_run(
    module: str, flags: list[str], root: Path, env: dict[str, str], stdin: str
) -> subprocess.CompletedProcess[str]:
    """Run one gate module in the checkout, with the stdin its hook mode reads."""
    return subprocess.run(
        [sys.executable, "-m", f"triviajudge.{module}", *flags],
        cwd=root,
        env=env,
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


# --- behavior 1: the payload mode judges the lines the working tree adds ------


def test_a_dated_comment_the_working_tree_adds_is_refused(tmp_path: Path) -> None:
    root, env = committed_repo(tmp_path, {"src/sample.py": CLEAN_COMMENT})
    write(root, {"src/sample.py": CLEAN_COMMENT + DATED_COMMENT})
    finished = gate_run(
        "archaeology",
        ["--post-tool-use"],
        root,
        env,
        payload_for(root, "src/sample.py"),
    )
    assert finished.returncode == 2


def test_a_dated_comment_in_an_untracked_file_is_refused(tmp_path: Path) -> None:
    root, env = committed_repo(tmp_path, {})
    write(root, {"src/fresh.py": DATED_COMMENT})
    finished = gate_run(
        "archaeology", ["--post-tool-use"], root, env, payload_for(root, "src/fresh.py")
    )
    assert finished.returncode == 2


def test_a_dated_comment_already_in_head_is_not_the_running_turns_to_answer_for(
    tmp_path: Path,
) -> None:
    root, env = committed_repo(tmp_path, {"src/sample.py": DATED_COMMENT})
    write(root, {"src/sample.py": DATED_COMMENT + CLEAN_COMMENT})
    finished = gate_run(
        "archaeology",
        ["--post-tool-use"],
        root,
        env,
        payload_for(root, "src/sample.py"),
    )
    assert finished.returncode == 0


# --- behavior 2: what the payload mode declines to read is a pass ------------


@pytest.mark.parametrize("name", ["notes.md", "triviajudge/archaeology.py"])
def test_a_file_outside_the_gates_reach_is_passed(tmp_path: Path, name: str) -> None:
    root, env = committed_repo(tmp_path, {})
    write(root, {name: DATED_COMMENT})
    finished = gate_run(
        "archaeology", ["--post-tool-use"], root, env, payload_for(root, name)
    )
    assert finished.returncode == 0


@pytest.mark.parametrize(
    "stdin", ["", "not json at all", '{"hook_event_name": "PostToolUse"}']
)
def test_a_payload_naming_no_readable_file_is_passed(
    tmp_path: Path, stdin: str
) -> None:
    root, env = committed_repo(tmp_path, {})
    finished = gate_run("archaeology", ["--post-tool-use"], root, env, stdin)
    assert finished.returncode == 0


def test_a_payload_naming_a_file_that_is_not_there_is_passed(tmp_path: Path) -> None:
    root, env = committed_repo(tmp_path, {})
    finished = gate_run(
        "archaeology",
        ["--post-tool-use"],
        root,
        env,
        payload_for(root, "src/absent.py"),
    )
    assert finished.returncode == 0


# --- behavior 3: the judge's own session runs no hook mode -------------------


def test_the_judge_sets_the_guard_in_the_environment_of_its_own_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, str] = {}

    class Finished:
        returncode = 0
        stdout = json.dumps({"result": "[]"})
        stderr = ""

    def fake_run(_cmd: list[str], **kwargs: object) -> Finished:
        seen.update(cast("dict[str, str]", kwargs["env"]))
        return Finished()

    monkeypatch.setattr(transport, "binary", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(transport, "root", Path.cwd)
    monkeypatch.setattr("triviajudge.transport.subprocess.run", fake_run)
    transport.ask([core.Line("doc.md", 1, "a line")], "prompt")
    assert seen[core.INNER] == "1"


@pytest.mark.parametrize("module", ["md_trivia", "comment_trivia"])
def test_a_stop_gate_under_the_guard_does_nothing(tmp_path: Path, module: str) -> None:
    root, env = committed_repo(tmp_path, {})
    write(root, {"notes.md": DATED_MARKDOWN, "src/sample.py": DATED_COMMENT})
    finished = gate_run(module, ["--stop"], root, {**env, core.INNER: "1"}, "{}")
    assert (finished.returncode, finished.stderr) == (0, "")


def test_the_archaeology_payload_mode_under_the_guard_does_nothing(
    tmp_path: Path,
) -> None:
    root, env = committed_repo(tmp_path, {})
    write(root, {"src/sample.py": DATED_COMMENT})
    stdin = payload_for(root, "src/sample.py")
    finished = gate_run(
        "archaeology", ["--post-tool-use"], root, {**env, core.INNER: "1"}, stdin
    )
    assert finished.returncode == 0


def test_without_the_guard_the_markdown_gate_reaches_for_a_judge_it_cannot_find(
    tmp_path: Path,
) -> None:
    root, env = committed_repo(tmp_path, {})
    write(root, {"notes.md": DATED_MARKDOWN})
    finished = gate_run("md_trivia", ["--stop"], root, env, "{}")
    assert "not on PATH" in finished.stderr


# --- behavior 4: the markdown judge at Stop is the repository's switch --------


def test_the_markdown_gate_makes_no_call_at_stop_when_the_repository_turns_it_off(
    tmp_path: Path,
) -> None:
    root, env = committed_repo(tmp_path, {SETTINGS_FILE: "md_judge_at_stop = false\n"})
    write(root, {"notes.md": DATED_MARKDOWN})
    finished = gate_run("md_trivia", ["--stop"], root, env, "{}")
    assert (finished.returncode, "not on PATH" in finished.stderr) == (0, False)
