"""The release gate: the version, the plugin manifests, the changelog and the tags name one release.

Four rules are exercised here, each against a throwaway checkout the test
builds and tags itself. The declared version equals the newest released
changelog heading, and ``[Unreleased]`` never satisfies it. Each plugin
manifest states that same version at its own key, and a manifest missing the
key fails rather than being excused. A tag pointing at ``HEAD`` is exactly
``v<version>``. Every released heading but the newest carries its tag, the
newest being the one exemption because the commit that cuts a release exists
before the tag naming it does.

``git`` is read through one helper that answers with no lines when the binary is
absent or the command refuses, so the gate reports a disagreement rather than
raising.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import TYPE_CHECKING

import check_release as GATE
import pytest

if TYPE_CHECKING:
    from pathlib import Path

GIT = os.environ.get("GIT", "git")

#: Long enough for a local `git` in a one-commit repository.
GIT_TIMEOUT = 30


def run_git(cwd: Path, *args: str) -> None:
    """Run one ``git`` command in ``cwd``, insisting it succeed."""
    subprocess.run([GIT, *args], cwd=cwd, check=True, capture_output=True, timeout=GIT_TIMEOUT)


def tree(
    tmp_path: Path,
    version: str = "0.2.0",
    sections: tuple[str, ...] = ("0.2.0",),
    manifests: str | None = None,
) -> Path:
    """A checkout stating ``version``, the changelog sections given, and a manifest version."""
    root = tmp_path / "repo"
    (root / ".claude-plugin").mkdir(parents=True)
    (root / "pyproject.toml").write_text(f'[project]\nname = "held"\nversion = "{version}"\n', encoding="utf-8")
    heads = "".join(f"## [{name}]\n\nheld\n\n" for name in sections)
    (root / "CHANGELOG.md").write_text(f"# Changelog\n\n## [Unreleased]\n\nheld\n\n{heads}", encoding="utf-8")
    shown = version if manifests is None else manifests
    (root / ".claude-plugin" / "plugin.json").write_text(json.dumps({"version": shown}), encoding="utf-8")
    marketplace = {"metadata": {"version": shown}}
    (root / ".claude-plugin" / "marketplace.json").write_text(json.dumps(marketplace), encoding="utf-8")
    return root


def committed(root: Path, tags: tuple[str, ...] = (), head: str | None = None) -> Path:
    """Turn a checkout into a repository, tagging an empty first commit and then ``HEAD``."""
    run_git(root, "init", "-q")
    run_git(root, "-c", "user.email=held@held", "-c", "user.name=held", "commit", "-q", "--allow-empty", "-m", "one")
    for tag in tags:
        run_git(root, "tag", tag)
    run_git(root, "-c", "user.email=held@held", "-c", "user.name=held", "commit", "-q", "--allow-empty", "-m", "two")
    if head is not None:
        run_git(root, "tag", head)
    return root


def judged(root: Path, monkeypatch: pytest.MonkeyPatch) -> int:
    """The gate's exit code with ``git`` pointed at this checkout."""
    monkeypatch.setattr(GATE, "ROOT", root)
    return GATE.check(root)


# --- behavior 1: the version, the manifests, the changelog and the tags agree --


def test_a_tree_whose_five_statements_agree_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = committed(tree(tmp_path), head="v0.2.0")
    assert judged(root, monkeypatch) == 0


def test_an_untagged_head_is_no_disagreement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = committed(tree(tmp_path))
    assert judged(root, monkeypatch) == 0


def test_the_declared_version_is_read_off_pyproject(tmp_path: Path) -> None:
    assert GATE.declared(tree(tmp_path, version="1.4.9") / "pyproject.toml") == "1.4.9"


def test_the_released_sections_are_newest_first(tmp_path: Path) -> None:
    root = tree(tmp_path, version="0.3.0", sections=("0.3.0", "0.2.0", "0.1.0"))
    assert GATE.released(root / "CHANGELOG.md") == ["0.3.0", "0.2.0", "0.1.0"]


# --- behavior 2: the version answers to the newest released heading -----------


def test_a_version_no_changelog_section_names_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = committed(tree(tmp_path, version="0.3.0", sections=("0.2.0",), manifests="0.3.0"))
    assert judged(root, monkeypatch) == 1


def test_a_changelog_with_no_released_section_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = committed(tree(tmp_path, sections=()))
    assert judged(root, monkeypatch) == 1


def test_the_unreleased_heading_never_stands_for_a_release(tmp_path: Path) -> None:
    assert GATE.released(tree(tmp_path, sections=()) / "CHANGELOG.md") == []


# --- behavior 3: each plugin manifest states that same version ---------------


def test_a_manifest_naming_another_version_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = committed(tree(tmp_path, manifests="0.1.0"))
    assert judged(root, monkeypatch) == 1


@pytest.mark.parametrize("body", ["{}", '{"metadata": {}}', '{"metadata": "held"}'])
def test_a_manifest_missing_its_version_key_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str
) -> None:
    root = committed(tree(tmp_path))
    (root / ".claude-plugin" / "marketplace.json").write_text(body, encoding="utf-8")
    assert judged(root, monkeypatch) == 1


def test_a_manifest_key_path_is_walked_to_the_value(tmp_path: Path) -> None:
    root = tree(tmp_path, version="0.5.0")
    assert GATE.stated(root / ".claude-plugin" / "marketplace.json", ("metadata", "version")) == "0.5.0"


def test_both_manifests_are_reported_when_both_disagree(tmp_path: Path) -> None:
    assert len(GATE.manifests(tree(tmp_path, manifests="0.1.0"), "0.2.0")) == 2


# --- behavior 4: the tags name the same release as the tree ------------------


def test_a_tag_on_head_naming_another_version_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = committed(tree(tmp_path), head="v0.9.9")
    assert judged(root, monkeypatch) == 1


def test_an_older_released_section_with_no_tag_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = committed(tree(tmp_path, version="0.2.0", sections=("0.2.0", "0.1.0")), head="v0.2.0")
    assert judged(root, monkeypatch) == 1


def test_an_older_released_section_carrying_its_tag_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = committed(tree(tmp_path, version="0.2.0", sections=("0.2.0", "0.1.0")), tags=("v0.1.0",), head="v0.2.0")
    assert judged(root, monkeypatch) == 0


# --- behavior 5: git that cannot answer answers with nothing ----------------


def test_a_refused_git_command_yields_no_lines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(GATE, "ROOT", committed(tree(tmp_path)))
    assert GATE.git("tag", "--points-at", "v0.0.0-absent") == []


def test_an_absent_git_binary_yields_no_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    assert GATE.git("tag", "--list") == []


def test_the_tags_are_read_as_one_line_each(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(GATE, "ROOT", committed(tree(tmp_path), tags=("v0.1.0",), head="v0.2.0"))
    assert GATE.git("tag", "--list") == ["v0.1.0", "v0.2.0"]


# --- behavior 6: the CLI judges this repository ------------------------------


def test_the_cli_judges_the_repository_it_ships_in() -> None:
    assert GATE.main() == 0
