"""The hook timeout gate: the harness must not kill a gate before its own bound fires.

A hook's timeout is compared with the largest timeout constant the module it runs
can reach — the engine's, which every mode calls into, and the module's own.

Each case asserts the verdict, not its size: the finding names the event, the
hook, its timeout and the constant that outruns it, and the run prints that line
followed by the refusal. The finding text and both verdict lines are seeded here,
so a reworded sentence or a constant read off the wrong module fails.
"""

import json
import sys
from pathlib import Path

import check_hook_timeouts as GATE
import pytest

ENGINE = "GIT_TIMEOUT = 30\n"

NO_CONSTANT = "PROMPT = 'judge these lines'\n"

OWN_CONSTANT = "CALL_TIMEOUT = 600\n"

RUNNER = '"${CLAUDE_PLUGIN_ROOT}/hooks/run-gate.sh" md_trivia'

ENGINE_FAULT = (
    "{path}: Stop hook md_trivia has timeout 10s, under core.GIT_TIMEOUT at 30s"
)

OWN_FAULT = (
    "{path}: Stop hook md_trivia has timeout 120s, under md_trivia.CALL_TIMEOUT at 600s"
)

NO_MODULE_FAULT = "{path}: Stop hook nowhere names no module under triviajudge/"

REFUSAL_TAIL = (
    "\n1 hook(s) undercut a wait they can make. Raise the timeout to the constant,\n"
    "or lower the constant: a killed hook prints no line about the call that was waiting.\n"
)

CLEAN_LINE = "[ok] every hook timeout covers the longest wait its module can make\n"


def table(gate: str, timeout: int) -> str:
    """One hook table naming a gate at a timeout."""
    command = RUNNER.replace("md_trivia", gate)
    hook = {"type": "command", "command": command, "timeout": timeout}
    return json.dumps({"hooks": {"Stop": [{"hooks": [hook]}]}})


def tree(tmp_path: Path, module: str, gate: str, timeout: int) -> tuple[Path, Path]:
    """Build a throwaway package and hook table, and answer with the root and the table."""
    package = tmp_path / GATE.PACKAGE
    package.mkdir()
    (package / "core.py").write_text(ENGINE, encoding="utf-8")
    (package / "md_trivia.py").write_text(module, encoding="utf-8")
    path = tmp_path / GATE.TABLE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(table(gate, timeout), encoding="utf-8")
    return tmp_path, path


# --- behavior 1: the engine's constant binds every mode ---------------------


def test_a_timeout_above_the_engine_s_constant_leaves_nothing_to_report(
    tmp_path: Path,
) -> None:
    assert GATE.faults(*tree(tmp_path, NO_CONSTANT, "md_trivia", 120)) == []


def test_a_timeout_equal_to_the_engine_s_constant_leaves_nothing_to_report(
    tmp_path: Path,
) -> None:
    assert GATE.faults(*tree(tmp_path, NO_CONSTANT, "md_trivia", 30)) == []


def test_a_timeout_under_the_engine_s_constant_names_the_constant_it_undercuts(
    tmp_path: Path,
) -> None:
    root, path = tree(tmp_path, NO_CONSTANT, "md_trivia", 10)
    assert GATE.faults(root, path) == [ENGINE_FAULT.format(path=path)]


# --- behavior 2: the module's own constants count too -----------------------


def test_a_constant_the_module_itself_states_is_the_one_the_finding_names(
    tmp_path: Path,
) -> None:
    root, path = tree(tmp_path, OWN_CONSTANT, "md_trivia", 120)
    assert GATE.faults(root, path) == [OWN_FAULT.format(path=path)]


def test_the_longest_wait_names_the_constant_that_sets_it(tmp_path: Path) -> None:
    root, _ = tree(tmp_path, OWN_CONSTANT, "md_trivia", 120)
    assert GATE.longest(root, "md_trivia") == ("md_trivia.CALL_TIMEOUT", 600.0)


# --- behavior 3: a hook naming no module cannot be judged -------------------


def test_a_hook_naming_no_module_is_reported_as_naming_none(tmp_path: Path) -> None:
    root, path = tree(tmp_path, NO_CONSTANT, "nowhere", 120)
    assert GATE.faults(root, path) == [NO_MODULE_FAULT.format(path=path)]


# --- behavior 4: what the run prints is the verdict ------------------------


def test_check_prints_the_undercut_line_and_the_refusal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, path = tree(tmp_path, NO_CONSTANT, "md_trivia", 10)
    code = GATE.check(root, path)
    assert (code, capsys.readouterr().out) == (
        1,
        ENGINE_FAULT.format(path=path) + "\n" + REFUSAL_TAIL,
    )


def test_check_prints_the_clean_line_when_every_timeout_covers_its_module(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = GATE.check(*tree(tmp_path, NO_CONSTANT, "md_trivia", 120))
    assert (code, capsys.readouterr().out) == (0, CLEAN_LINE)


# --- behavior 5: argv names the table, and its absence names the repository -


def test_main_names_the_undercut_hook_in_the_table_argv_gave(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root, path = tree(tmp_path, OWN_CONSTANT, "md_trivia", 120)
    monkeypatch.setattr(GATE, "ROOT", root)
    monkeypatch.setattr(sys, "argv", ["check_hook_timeouts.py", str(path)])
    code = GATE.main()
    assert (code, capsys.readouterr().out) == (
        1,
        OWN_FAULT.format(path=path) + "\n" + REFUSAL_TAIL,
    )


def test_main_with_no_argv_reads_the_table_under_the_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root, path = tree(tmp_path, NO_CONSTANT, "md_trivia", 10)
    monkeypatch.setattr(GATE, "ROOT", root)
    monkeypatch.setattr(sys, "argv", ["check_hook_timeouts.py"])
    code = GATE.main()
    assert (code, capsys.readouterr().out) == (
        1,
        ENGINE_FAULT.format(path=path) + "\n" + REFUSAL_TAIL,
    )


def test_this_repository_s_hooks_cover_the_waits_their_modules_make(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = GATE.check(GATE.ROOT)
    assert (code, capsys.readouterr().out) == (0, CLEAN_LINE)
