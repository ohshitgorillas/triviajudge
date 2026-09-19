"""Behavior of the gate that holds the gate catalog to the three tables naming it.

The catalog is judged against a tree each case builds: the package modules, the
``[project.scripts]`` table, the pre-commit manifest and the plugin's hook
wiring. Every drift the gate names is one case in the sweep, and the tables name
a single gate, so one disagreement is the only difference between a failing case
and the passing one.

A refusal is matched on the exit code and on the names the case put in the
tables, never on the sentence the gate wraps around them.
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


# --- behavior 1: one disagreement anywhere across the three tables refuses ----


@pytest.mark.parametrize(
    ("catalog", "tables", "code"),
    [
        (HOOKED, AGREED, 0),
        (CONSOLE_ONLY, AGREED_OFF_HOOK, 0),
        (HOOKED, with_modules([]), 1),
        (HOOKED, with_declared({}), 1),
        (HOOKED, with_declared({SCRIPT: SWEEP_ENTRY_POINT}), 1),
        (HOOKED, with_declared({SCRIPT: ENTRY_POINT, OTHER_SCRIPT: ENTRY_POINT}), 1),
        (HOOKED, with_manifest([]), 1),
        (HOOKED, with_manifest([(HOOK_ID, OTHER_SCRIPT)]), 1),
        (HOOKED, with_manifest([(HOOK_ID, SCRIPT), (OTHER_HOOK_ID, OTHER_SCRIPT)]), 1),
        (HOOKED, with_plugin([]), 1),
        (CONSOLE_ONLY, Tables([SWEEP_MODULE], {SWEEP_SCRIPT: SWEEP_ENTRY_POINT}, [], [SWEEP_MODULE]), 1),
        (HOOKED, with_plugin([MODULE, OTHER_MODULE]), 1),
    ],
)
def test_the_catalog_passes_only_when_all_three_tables_agree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    catalog: dict[str, GATE.Gate],
    tables: Tables,
    code: int,
) -> None:
    wire(tmp_path, tables)
    pointed_at(tmp_path, monkeypatch)
    assert GATE.check(catalog) == code


# --- behavior 2: each table is read as the file the repository ships spells it ---


def test_the_scripts_table_is_the_console_scripts_pyproject_declares(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wire(tmp_path, AGREED)
    pointed_at(tmp_path, monkeypatch)
    assert GATE.scripts() == AGREED.declared


def test_a_hook_id_carrying_no_entry_reads_as_running_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    wire(tmp_path, AGREED)
    (tmp_path / ".pre-commit-hooks.yaml").write_text(f"- id: {HOOK_ID}\n- id: {OTHER_HOOK_ID}\n", encoding="utf-8")
    pointed_at(tmp_path, monkeypatch)
    assert GATE.manifest() == {HOOK_ID: "", OTHER_HOOK_ID: ""}


def test_a_module_two_events_run_is_wired_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    wire(tmp_path, AGREED)
    command = {"command": f'"$PLUGIN/hooks/run-gate.sh" {MODULE}'}
    payload = {"hooks": {"Stop": [{"hooks": [command]}], "SubagentStop": [{"hooks": [command]}]}}
    (tmp_path / "hooks" / "hooks.json").write_text(json.dumps(payload), encoding="utf-8")
    pointed_at(tmp_path, monkeypatch)
    assert GATE.plugin_modules() == {MODULE}


# --- behavior 3: a catalog name is a module that exists -----------------------


@pytest.mark.parametrize(("modules", "faults"), [([MODULE], 0), ([], 1)])
def test_a_catalog_name_with_no_module_is_a_fault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, modules: list[str], faults: int
) -> None:
    wire(tmp_path, with_modules(modules))
    pointed_at(tmp_path, monkeypatch)
    assert len(GATE.check_modules(HOOKED)) == faults


# --- behavior 4: this repository's own catalog agrees with its own tables ------


def test_this_repository_passes_its_own_catalog_gate() -> None:
    assert GATE.main() == 0
