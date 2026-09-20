"""The release gate: the version, the plugin manifests, the changelog and the tags name one release.

Four rules are exercised here, each against a throwaway checkout the test
builds and tags itself, and each read through the line the gate prints, so a
test names which of the five statements disagrees. The declared version equals
the newest released changelog heading, and ``[Unreleased]`` never satisfies it.
Each plugin manifest states that same version at its own key, and a manifest
missing the key fails rather than being excused. A tag pointing at ``HEAD`` is
exactly ``v<version>``. Every released heading but the newest carries its tag,
the newest being the one exemption because the commit that cuts a release
exists before the tag naming it does.

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

#: The verdict over an agreeing tree of one released section, and of two.
OK_ONE = "[ok] version 0.2.0 is the newest of 1 changelog section(s); manifests and tags agree"
OK_TWO = "[ok] version 0.2.0 is the newest of 2 changelog section(s); manifests and tags agree"

#: The finding naming the version against the newest released changelog heading.
NEWEST = "pyproject.toml: version 0.3.0, newest CHANGELOG.md section [0.2.0]"

#: The finding when no heading in the changelog is a release.
NO_SECTION = "CHANGELOG.md: no released section, so nothing states what version is out"

#: The finding naming each plugin manifest that states another version.
PLUGIN = ".claude-plugin/plugin.json: version 0.1.0, pyproject.toml version 0.2.0"
MARKETPLACE = ".claude-plugin/marketplace.json: metadata.version 0.1.0, pyproject.toml version 0.2.0"

#: The finding when a manifest holds no version at the key path named for it.
NO_KEY = ".claude-plugin/marketplace.json: no metadata.version, so nothing names the release it ships"

#: The finding naming a tag on ``HEAD`` that is not ``v<version>``.
HEAD_TAG = "v0.9.9: tag on HEAD, version 0.2.0"

#: The finding naming a released section older than the newest that carries no tag.
UNTAGGED = "CHANGELOG.md: [0.1.0] is released and carries no v0.1.0 tag"


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


def verdict(root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> list[str]:
    """The lines the gate printed over this checkout, with ``git`` pointed at it."""
    monkeypatch.setattr(GATE, "ROOT", root)
    GATE.check(root)
    return capsys.readouterr().out.splitlines()


# --- behavior 1: the version, the manifests, the changelog and the tags agree --


def test_a_tree_whose_five_statements_agree_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = committed(tree(tmp_path), head="v0.2.0")
    assert verdict(root, monkeypatch, capsys) == [OK_ONE]


def test_an_untagged_head_is_no_disagreement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = committed(tree(tmp_path))
    assert verdict(root, monkeypatch, capsys) == [OK_ONE]


# --- behavior 2: the version answers to the newest released heading -----------


def test_a_version_no_changelog_section_names_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = committed(tree(tmp_path, version="0.3.0", sections=("0.2.0",), manifests="0.3.0"))
    assert NEWEST in verdict(root, monkeypatch, capsys)


def test_a_changelog_with_no_released_section_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = committed(tree(tmp_path, sections=()))
    assert NO_SECTION in verdict(root, monkeypatch, capsys)


def test_the_unreleased_heading_never_stands_for_a_release(tmp_path: Path) -> None:
    assert GATE.released(tree(tmp_path) / "CHANGELOG.md") == ["0.2.0"]


# --- behavior 3: each plugin manifest states that same version ---------------


def test_a_manifest_naming_another_version_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = committed(tree(tmp_path, manifests="0.1.0"))
    assert PLUGIN in verdict(root, monkeypatch, capsys)


@pytest.mark.parametrize("body", ["{}", '{"metadata": {}}', '{"metadata": "held"}'])
def test_a_manifest_missing_its_version_key_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], body: str
) -> None:
    root = committed(tree(tmp_path))
    (root / ".claude-plugin" / "marketplace.json").write_text(body, encoding="utf-8")
    assert NO_KEY in verdict(root, monkeypatch, capsys)


def test_both_manifests_are_reported_when_both_disagree(tmp_path: Path) -> None:
    assert GATE.manifests(tree(tmp_path, manifests="0.1.0"), "0.2.0") == [PLUGIN, MARKETPLACE]


# --- behavior 4: the tags name the same release as the tree ------------------


def test_a_tag_on_head_naming_another_version_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = committed(tree(tmp_path), head="v0.9.9")
    assert HEAD_TAG in verdict(root, monkeypatch, capsys)


def test_an_older_released_section_with_no_tag_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = committed(tree(tmp_path, version="0.2.0", sections=("0.2.0", "0.1.0")), head="v0.2.0")
    assert UNTAGGED in verdict(root, monkeypatch, capsys)


def test_an_older_released_section_carrying_its_tag_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = committed(tree(tmp_path, version="0.2.0", sections=("0.2.0", "0.1.0")), tags=("v0.1.0",), head="v0.2.0")
    assert verdict(root, monkeypatch, capsys) == [OK_TWO]


# --- behavior 5: git that cannot answer answers with nothing ----------------


def test_a_refused_git_command_yields_no_lines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(GATE, "ROOT", committed(tree(tmp_path)))
    assert GATE.git("tag", "--points-at", "v0.0.0-absent") == []


def test_an_absent_git_binary_yields_no_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    assert GATE.git("tag", "--list") == []
