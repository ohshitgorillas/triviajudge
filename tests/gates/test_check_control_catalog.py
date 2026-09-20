"""Behavior of the gate that holds the gate catalog to the three tables naming it.

The catalog is judged against a tree each case builds: the package modules, the
``[project.scripts]`` table, the pre-commit manifest and the plugin's hook
wiring. Every drift the gate names is one case, and the tables name a single
gate, so one disagreement is the only difference between a refusing case and the
passing one.

A refusal is matched on the exit code and on the sentence the gate prints for
that one disagreement, seeded below as a constant.
"""

import json
from pathlib import Path
from typing import NamedTuple

import check_control_catalog as GATE
import pytest

MODULE = "md_trivia"
SCRIPT = "triviajudge-md"
ENTRY_POINT = "triviajudge.md_trivia:main"
HOOK_ID = "md-trivia"

OTHER_MODULE = "comment_trivia"
OTHER_SCRIPT = "triviajudge-comments"
OTHER_HOOK_ID = "comment-trivia"

SWEEP_MODULE = "sweep"
SWEEP_SCRIPT = "triviajudge-sweep"
SWEEP_ENTRY_POINT = "triviajudge.sweep:main"

#: One hooked gate, wired everywhere a hooked gate belongs.
HOOKED = {MODULE: GATE.Gate(script=SCRIPT, hook_id=HOOK_ID, plugin=True)}
#: One gate the catalog holds off the hook path altogether.
CONSOLE_ONLY = {SWEEP_MODULE: GATE.Gate(script=SWEEP_SCRIPT, hook_id=None, plugin=False)}

#: The verdict line for a catalog whose gates all agree, one gate deep.
AGREES = "[ok] all 1 gates agree across the three tables"
#: The tail a refusal prints under a single finding.
ONE_DISAGREEMENT = "1 catalog disagreement(s) across pyproject.toml, .pre-commit-hooks.yaml, hooks.json."

NO_MODULE = f"CATALOG['{MODULE}']: names no module at triviajudge/{MODULE}.py"
NO_SCRIPT = f"{SCRIPT}: no [project.scripts] entry"
SCRIPT_MISPOINTED = f"{SCRIPT}: [project.scripts] points at '{SWEEP_ENTRY_POINT}', not '{ENTRY_POINT}'"
SCRIPT_UNCATALOGED = f"{OTHER_SCRIPT}: a [project.scripts] entry the catalog does not carry"
NO_HOOK_ID = f"{HOOK_ID}: no id in .pre-commit-hooks.yaml, for gate {MODULE}"
HOOK_ID_MISPOINTED = f"{HOOK_ID}: runs '{OTHER_SCRIPT}', not '{SCRIPT}'"
HOOK_ID_RUNS_NOTHING = f"{HOOK_ID}: runs '', not '{SCRIPT}'"
HOOK_ID_UNCATALOGED = f"{OTHER_HOOK_ID}: a .pre-commit-hooks.yaml id the catalog does not carry"
NOT_WIRED = f"{MODULE}: hooks.json runs no such gate"
WIRED_OFF_HOOK = f"{SWEEP_MODULE}: hooks.json wires it, and the catalog holds it off the hook path"
WIRED_UNCATALOGED = f"{OTHER_MODULE}: hooks.json runs a gate the catalog does not carry"


class Tables(NamedTuple):
    """What a tree says about its gates, across the modules and the three tables."""

    #: Module files present under ``triviajudge/``.
    modules: list[str]
    #: ``[project.scripts]``, console script to entry point.
    declared: dict[str, str]
    #: ``.pre-commit-hooks.yaml``, hook id to the console script it runs.
    manifest: list[tuple[str, str]]
    #: The module names ``hooks/hooks.json`` runs.
    plugin: list[str]


#: One hooked gate, spelled the same way in all four places.
AGREED = Tables(modules=[MODULE], declared={SCRIPT: ENTRY_POINT}, manifest=[(HOOK_ID, SCRIPT)], plugin=[MODULE])
#: One console-script-only gate, absent from both hook tables as the catalog says it must be.
AGREED_OFF_HOOK = Tables(modules=[SWEEP_MODULE], declared={SWEEP_SCRIPT: SWEEP_ENTRY_POINT}, manifest=[], plugin=[])


def with_modules(modules: list[str]) -> Tables:
    """The agreeing tree, with the module files it holds replaced."""
    return Tables(modules, AGREED.declared, AGREED.manifest, AGREED.plugin)


def with_declared(declared: dict[str, str]) -> Tables:
    """The agreeing tree, with its ``[project.scripts]`` table replaced."""
    return Tables(AGREED.modules, declared, AGREED.manifest, AGREED.plugin)


def with_manifest(manifest: list[tuple[str, str]]) -> Tables:
    """The agreeing tree, with its pre-commit manifest replaced."""
    return Tables(AGREED.modules, AGREED.declared, manifest, AGREED.plugin)


def with_plugin(plugin: list[str]) -> Tables:
    """The agreeing tree, with the modules the plugin runs replaced."""
    return Tables(AGREED.modules, AGREED.declared, AGREED.manifest, plugin)


def wire(root: Path, tables: Tables) -> None:
    """Write the module files and the three tables a catalog is checked against."""
    package = root / "triviajudge"
    package.mkdir(parents=True, exist_ok=True)
    for name in tables.modules:
        (package / f"{name}.py").write_text("", encoding="utf-8")
    table = ["[project.scripts]", *(f'{name} = "{target}"' for name, target in tables.declared.items())]
    (root / "pyproject.toml").write_text("\n".join(table) + "\n", encoding="utf-8")
    ids = "".join(f"- id: {hook}\n  entry: {entry}\n" for hook, entry in tables.manifest)
    (root / ".pre-commit-hooks.yaml").write_text(ids, encoding="utf-8")
    (root / "hooks").mkdir(exist_ok=True)
    commands = [{"command": f'"$PLUGIN/hooks/run-gate.sh" {name}'} for name in tables.plugin]
    payload = {"hooks": {"Stop": [{"hooks": commands}]}}
    (root / "hooks" / "hooks.json").write_text(json.dumps(payload), encoding="utf-8")


def pointed_at(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the gate read the tree at ``root`` instead of this repository."""
    monkeypatch.setattr(GATE, "ROOT", root)
    monkeypatch.setattr(GATE, "PYPROJECT", root / "pyproject.toml")
    monkeypatch.setattr(GATE, "HOOKS_YAML", root / ".pre-commit-hooks.yaml")
    monkeypatch.setattr(GATE, "HOOKS_JSON", root / "hooks" / "hooks.json")


def spoken(capsys: pytest.CaptureFixture[str]) -> tuple[list[str], str]:
    """(the findings the gate printed, the tail it printed under them)."""
    head, _, tail = capsys.readouterr().out.partition("\n\n")
    return head.splitlines(), tail.strip()


def verdict(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    catalog: dict[str, GATE.Gate],
    tables: Tables,
) -> tuple[int, list[str], str]:
    """Judge ``catalog`` against a tree wired to ``tables``: (exit code, findings, tail)."""
    wire(root, tables)
    pointed_at(root, monkeypatch)
    code = GATE.check(catalog)
    findings, tail = spoken(capsys)
    return code, findings, tail


# --- behavior 1: agreement across all four places passes ----------------------


def test_a_hooked_gate_spelled_the_same_everywhere_agrees(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert verdict(tmp_path, monkeypatch, capsys, HOOKED, AGREED) == (0, [AGREES], "")


def test_a_console_only_gate_absent_from_both_hook_tables_agrees(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert verdict(tmp_path, monkeypatch, capsys, CONSOLE_ONLY, AGREED_OFF_HOOK) == (0, [AGREES], "")


def test_a_module_two_events_run_is_wired_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    wire(tmp_path, AGREED)
    command = {"command": f'"$PLUGIN/hooks/run-gate.sh" {MODULE}'}
    payload = {"hooks": {"Stop": [{"hooks": [command]}], "SubagentStop": [{"hooks": [command]}]}}
    (tmp_path / "hooks" / "hooks.json").write_text(json.dumps(payload), encoding="utf-8")
    pointed_at(tmp_path, monkeypatch)
    code = GATE.check(HOOKED)
    assert (code, *spoken(capsys)) == (0, [AGREES], "")


# --- behavior 2: a catalog name names a module that exists ---------------------


def test_a_catalog_name_with_no_module_file_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert verdict(tmp_path, monkeypatch, capsys, HOOKED, with_modules([])) == (1, [NO_MODULE], ONE_DISAGREEMENT)


# --- behavior 3: the [project.scripts] table disagreeing is named --------------


def test_a_gate_with_no_console_script_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert verdict(tmp_path, monkeypatch, capsys, HOOKED, with_declared({})) == (1, [NO_SCRIPT], ONE_DISAGREEMENT)


def test_a_console_script_bound_to_another_module_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tables = with_declared({SCRIPT: SWEEP_ENTRY_POINT})
    assert verdict(tmp_path, monkeypatch, capsys, HOOKED, tables) == (1, [SCRIPT_MISPOINTED], ONE_DISAGREEMENT)


def test_a_console_script_the_catalog_does_not_carry_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tables = with_declared({SCRIPT: ENTRY_POINT, OTHER_SCRIPT: ENTRY_POINT})
    assert verdict(tmp_path, monkeypatch, capsys, HOOKED, tables) == (1, [SCRIPT_UNCATALOGED], ONE_DISAGREEMENT)


# --- behavior 4: the pre-commit manifest disagreeing is named -----------------


def test_a_hooked_gate_with_no_pre_commit_id_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert verdict(tmp_path, monkeypatch, capsys, HOOKED, with_manifest([])) == (1, [NO_HOOK_ID], ONE_DISAGREEMENT)


def test_a_pre_commit_id_running_another_script_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tables = with_manifest([(HOOK_ID, OTHER_SCRIPT)])
    assert verdict(tmp_path, monkeypatch, capsys, HOOKED, tables) == (1, [HOOK_ID_MISPOINTED], ONE_DISAGREEMENT)


def test_a_pre_commit_id_carrying_no_entry_runs_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tables = with_manifest([(HOOK_ID, "")])
    assert verdict(tmp_path, monkeypatch, capsys, HOOKED, tables) == (1, [HOOK_ID_RUNS_NOTHING], ONE_DISAGREEMENT)


def test_a_pre_commit_id_the_catalog_does_not_carry_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tables = with_manifest([(HOOK_ID, SCRIPT), (OTHER_HOOK_ID, OTHER_SCRIPT)])
    assert verdict(tmp_path, monkeypatch, capsys, HOOKED, tables) == (1, [HOOK_ID_UNCATALOGED], ONE_DISAGREEMENT)


# --- behavior 5: the plugin wiring disagreeing is named -----------------------


def test_a_plugin_gate_the_hooks_json_does_not_run_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert verdict(tmp_path, monkeypatch, capsys, HOOKED, with_plugin([])) == (1, [NOT_WIRED], ONE_DISAGREEMENT)


def test_a_gate_held_off_the_hook_path_but_wired_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tables = Tables([SWEEP_MODULE], {SWEEP_SCRIPT: SWEEP_ENTRY_POINT}, [], [SWEEP_MODULE])
    assert verdict(tmp_path, monkeypatch, capsys, CONSOLE_ONLY, tables) == (1, [WIRED_OFF_HOOK], ONE_DISAGREEMENT)


def test_a_wired_module_the_catalog_does_not_carry_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    tables = with_plugin([MODULE, OTHER_MODULE])
    assert verdict(tmp_path, monkeypatch, capsys, HOOKED, tables) == (1, [WIRED_UNCATALOGED], ONE_DISAGREEMENT)
