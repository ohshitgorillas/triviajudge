"""The hook timeout gate: the harness must not kill a gate before its own bound fires.

A hook's timeout is compared with the largest timeout constant the module it runs
can reach — the engine's, which every mode calls into, and the module's own.
"""

import json
from pathlib import Path

import check_hook_timeouts as GATE

ENGINE = "GIT_TIMEOUT = 30\n"

NO_CONSTANT = "PROMPT = 'judge these lines'\n"

OWN_CONSTANT = "CALL_TIMEOUT = 600\n"

RUNNER = '"${CLAUDE_PLUGIN_ROOT}/hooks/run-gate.sh" md_trivia'


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
    path = tmp_path / "hooks.json"
    path.write_text(table(gate, timeout), encoding="utf-8")
    return tmp_path, path


# --- behavior 1: the engine's constant binds every mode ---------------------


def test_a_timeout_above_the_engine_s_constant_passes(tmp_path: Path) -> None:
    assert GATE.check(*tree(tmp_path, NO_CONSTANT, "md_trivia", 120)) == 0


def test_a_timeout_equal_to_the_constant_passes(tmp_path: Path) -> None:
    assert GATE.check(*tree(tmp_path, NO_CONSTANT, "md_trivia", 30)) == 0


def test_a_timeout_under_the_engine_s_constant_fails(tmp_path: Path) -> None:
    assert GATE.check(*tree(tmp_path, NO_CONSTANT, "md_trivia", 10)) == 1


# --- behavior 2: the module's own constants count too -----------------------


def test_a_constant_the_module_itself_states_is_reached(tmp_path: Path) -> None:
    assert GATE.check(*tree(tmp_path, OWN_CONSTANT, "md_trivia", 120)) == 1


def test_the_longest_wait_names_the_constant_that_sets_it(tmp_path: Path) -> None:
    root, _ = tree(tmp_path, OWN_CONSTANT, "md_trivia", 120)
    assert GATE.longest(root, "md_trivia") == ("md_trivia.CALL_TIMEOUT", 600.0)


# --- behavior 3: a hook naming no module cannot be judged -------------------


def test_a_hook_naming_no_module_is_named(tmp_path: Path) -> None:
    assert GATE.check(*tree(tmp_path, NO_CONSTANT, "nowhere", 120)) == 1


def test_this_repository_s_hooks_cover_the_waits_their_modules_make() -> None:
    assert GATE.check(GATE.ROOT) == 0
