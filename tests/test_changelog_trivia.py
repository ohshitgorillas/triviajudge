"""The trivia judge over changelog entries: the section reader, the screen, and the two scopes.

``triviajudge.changelog_trivia`` reads the bullets under ``## [Unreleased]``,
screens the ones the mechanical rules already answer for, and spends a judge
call on what is left. ``--release`` is the other scope: every bullet in the
section, in one call, asking which of them must not ship beside each other.

Four seams are exercised here: the section reader with its bullets and kinds,
each rule of the pattern screen, the two scopes driven the way a commit and a
hook drive them, and the refusal ``--release`` answers a second mode with.

Cases identify a bullet by the markers this module planted in the changelog it
handed over, or by line number, never by wording the gate composes.
"""

import argparse
import subprocess
from pathlib import Path

import pytest
from test_hook_modes import child_environment, committed_repo, gate_run, git_run, write

from triviajudge import changelog_prompts as PROMPTS
from triviajudge import changelog_trivia as GATE
from triviajudge import core

#: Markers planted in the sample changelogs, in the order a projection reports them.
MARKERS = ("ALPHA", "BRAVO", "CHARLIE", "DELTA")

#: The message a missing judge binary ends a run with, seeded here so no assertion spells it.
MISSING_JUDGE = "not on PATH"

SAMPLE = (
    "# Changelog\n"
    "\n"
    "## [Unreleased]\n"
    "\n"
    "### Added\n"
    "\n"
    "- **ALPHA the panel states the staged rate.** It reads the lane model.\n"
    "\n"
    "### Fixed\n"
    "\n"
    "- **BRAVO the lane returns the staged model.**\n"
    "\n"
    "## [0.1.0] - 2026-01-01\n"
    "\n"
    "### Added\n"
    "\n"
    "- **DELTA the shipped entry nobody rewrites.**\n"
)

CONTINUED = (
    "## [Unreleased]\n"
    "\n"
    "### Fixed\n"
    "\n"
    "- **BRAVO the lane returns the staged model.**\n"
    "  CHARLIE the continuation line it carries.\n"
)

NO_BOLD_LEAD = "- the lane returns the staged model.\n"
SECOND_PERSON = "- **your lane returns the staged model.**\n"
MARKETING = "- **the lane simply returns the staged model.**\n"
BY_NEGATION = "- **the lane returns the staged model, the panel untouched.**\n"
OVER_THE_CAP = (
    "- **the lane returns the staged model.** "
    + " ".join(["lane"] * (GATE.WORD_CAP + 1))
    + "\n"
)
CLEAN_ENTRY = "- **the lane returns the staged model.**\n"
CODE_SPAN_ENTRY = "- **lane rate** `the code span here`"

STAGED_CLEAN = "## [Unreleased]\n\n### Fixed\n\n" + CLEAN_ENTRY
STAGED_REFUSED = "## [Unreleased]\n\n### Fixed\n\n" + NO_BOLD_LEAD

ALREADY_RAN = '{"stop_hook_active": true}'

ONE_ADDED_BULLET = f"diff --git a/CHANGELOG.md b/CHANGELOG.md\n--- a/CHANGELOG.md\n+++ b/CHANGELOG.md\n@@ -0,0 +5 @@\n+{CLEAN_ENTRY}"


def markers_in(text: str) -> tuple[str, ...]:
    """The markers this module planted that ``text`` carries, in ``MARKERS`` order."""
    return tuple(marker for marker in MARKERS if marker in text)


def namespace(**overrides: object) -> argparse.Namespace:
    """The arguments a gate run carries, with every mode the flags leave alone switched off."""
    args: dict[str, object] = {
        "stop": False,
        "lines": None,
        "head": False,
        "files": [],
        "release": False,
    }
    return argparse.Namespace(**{**args, **overrides})


def first_block(text: str) -> list[str]:
    """The lines of the first bullet under ``[Unreleased]``."""
    return GATE.bullets(GATE.section(text))[0][2]


def staged_run(
    tmp_path: Path,
    text: str,
    flags: list[str],
    stdin: str = "{}",
    *,
    stage: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run the gate over a throwaway checkout carrying ``text`` as its changelog."""
    root, env = committed_repo(tmp_path, {})
    write(root, {GATE.CHANGELOG: text})
    if stage:
        git_run(root, env, "add", "-A")
    return gate_run("changelog_trivia", flags, root, env, stdin)


# --- behavior 1: the section reader stops where the release history starts ----


def test_only_the_bullets_under_the_unreleased_heading_are_read() -> None:
    assert [number for number, _kind, _block in GATE.bullets(GATE.section(SAMPLE))] == [
        7,
        11,
    ]


def test_each_bullet_carries_the_kind_it_sits_under() -> None:
    assert [kind for _number, kind, _block in GATE.bullets(GATE.section(SAMPLE))] == [
        "Added",
        "Fixed",
    ]


def test_a_continuation_line_arrives_joined_to_the_bullet_it_belongs_to() -> None:
    assert markers_in(GATE.joined(first_block(CONTINUED))) == ("BRAVO", "CHARLIE")


def test_a_code_span_costs_a_bullet_no_words() -> None:
    assert GATE.words(CODE_SPAN_ENTRY) == 2


# --- behavior 2: each screen rule answers for the bullet it refuses ----------


@pytest.mark.parametrize(
    "block",
    [
        [NO_BOLD_LEAD],
        [SECOND_PERSON],
        [MARKETING],
        [BY_NEGATION],
        [OVER_THE_CAP],
        [CLEAN_ENTRY, "  " + CLEAN_ENTRY],
    ],
)
def test_a_bullet_breaking_one_rule_draws_one_complaint(block: list[str]) -> None:
    assert len(GATE.entry_faults(1, block)) == 1


def test_a_bullet_breaking_no_rule_draws_none() -> None:
    assert GATE.entry_faults(1, [CLEAN_ENTRY]) == []


@pytest.mark.parametrize(
    ("found", "count"),
    [
        ([(5, "Added"), (9, "Added")], 1),
        ([(5, "Fixed"), (9, "Added")], 1),
        ([(5, "Notes")], 1),
        ([(5, "Added"), (9, "Fixed")], 0),
    ],
)
def test_the_heading_rules_answer_for_the_section_they_read(
    found: list[tuple[int, str]], count: int
) -> None:
    assert len(GATE.heading_faults(found)) == count


# --- behavior 3: the entry scope reads the bullets a change adds -------------


def test_a_bullet_the_change_leaves_alone_does_not_reach_the_judge() -> None:
    lines, _complaints = GATE.screen(SAMPLE, {11})
    assert [line.id for line in lines] == [f"{GATE.CHANGELOG}:11"]


def test_a_bullet_the_screen_refuses_is_answered_for_and_not_sent() -> None:
    lines, complaints = GATE.screen(
        "## [Unreleased]\n\n### Fixed\n\n" + NO_BOLD_LEAD, {5}
    )
    assert (len(lines), len(complaints)) == (0, 1)


def test_the_records_mode_judges_the_bullets_the_file_addresses(tmp_path: Path) -> None:
    records = tmp_path / "lines.tsv"
    records.write_text(f"{GATE.CHANGELOG}:7\t{CLEAN_ENTRY}", encoding="utf-8")
    lines, _complaints = GATE.collect(namespace(lines=str(records)))
    assert [line.id for line in lines] == [f"{GATE.CHANGELOG}:7"]


def test_the_head_mode_judges_the_bullets_the_last_commit_added(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "triviajudge.changelog_trivia.git_diff", lambda *_args: ONE_ADDED_BULLET
    )
    monkeypatch.setattr("triviajudge.changelog_trivia.at", lambda _rev: STAGED_CLEAN)
    lines, _complaints = GATE.collect(namespace(head=True))
    assert [line.id for line in lines] == [f"{GATE.CHANGELOG}:5"]


def test_a_commit_naming_no_changelog_judges_nothing() -> None:
    assert GATE.collect(namespace(files=["notes.md"])) == ([], [])


def test_a_revision_that_does_not_carry_the_changelog_reads_as_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(*_args: str) -> str:
        raise subprocess.CalledProcessError(1, "git")

    monkeypatch.setattr("triviajudge.changelog_trivia.git", refuse)
    assert GATE.at("HEAD") == ""


# --- behavior 4: the release scope reads the whole section -------------------


def test_the_release_scope_sends_every_bullet_under_the_unreleased_heading() -> None:
    lines, _complaints = GATE.whole_section(SAMPLE)
    assert [line.number for line in lines] == [7, 11]


def test_a_bullet_reaches_the_release_judge_carrying_its_kind() -> None:
    lines, _complaints = GATE.whole_section(SAMPLE)
    assert lines[0].text.startswith("(Added)")


def test_the_release_scope_asks_its_own_question() -> None:
    assert GATE.gate(namespace(release=True)).prompt == PROMPTS.RELEASE_PROMPT


def test_the_release_scope_keeps_no_cache() -> None:
    assert GATE.gate(namespace(release=True)).cache is None


# --- behavior 5: the exit code each scope earns over a throwaway checkout -----


@pytest.mark.parametrize(
    ("text", "flags", "reached"),
    [
        (STAGED_CLEAN, [], True),
        (STAGED_REFUSED, [], False),
        (SAMPLE, ["--release"], True),
    ],
)
def test_the_exit_code_over_a_checkout_with_no_judge_binary_on_path(
    tmp_path: Path, text: str, flags: list[str], reached: bool
) -> None:
    finished = staged_run(tmp_path, text, flags)
    assert (finished.returncode, MISSING_JUDGE in finished.stderr) == (1, reached)


@pytest.mark.parametrize(("stdin", "code"), [("{}", 2), (ALREADY_RAN, 0)])
def test_the_working_tree_mode_reads_an_untracked_changelog_whole(
    tmp_path: Path, stdin: str, code: int
) -> None:
    finished = staged_run(tmp_path, SAMPLE, ["--stop"], stdin, stage=False)
    assert finished.returncode == code


def test_the_release_scope_refuses_a_mode_it_does_not_fold_into(tmp_path: Path) -> None:
    finished = gate_run(
        "changelog_trivia",
        ["--release", "--head"],
        tmp_path,
        child_environment(tmp_path),
        "",
    )
    assert GATE.RELEASE_ALONE in finished.stderr


def test_a_directory_in_no_work_tree_is_refused(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    finished = gate_run(
        "changelog_trivia", [], outside, child_environment(tmp_path), ""
    )
    assert finished.returncode == 1


def test_the_working_tree_mode_reads_what_a_tracked_changelog_gains(
    tmp_path: Path,
) -> None:
    root, env = committed_repo(tmp_path, {GATE.CHANGELOG: STAGED_CLEAN})
    write(root, {GATE.CHANGELOG: STAGED_CLEAN + CLEAN_ENTRY})
    finished = gate_run("changelog_trivia", ["--stop"], root, env, "{}")
    assert (finished.returncode, MISSING_JUDGE in finished.stderr) == (2, True)


def test_the_stop_mode_under_the_judges_own_session_does_nothing(
    tmp_path: Path,
) -> None:
    root, env = committed_repo(tmp_path, {})
    write(root, {GATE.CHANGELOG: SAMPLE})
    finished = gate_run(
        "changelog_trivia", ["--stop"], root, {**env, core.INNER: "1"}, "{}"
    )
    assert (finished.returncode, finished.stderr) == (0, "")
