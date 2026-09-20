"""The offline changelog gate: bullet shape and heading order under ``[Unreleased]``.

Four rules over the section as a whole — the word cap, the bold lead, the second
person, and one heading per kind in Keep a Changelog order. Each case seeds the
finding the gate owes it: the line the bullet or heading opens on, the rule it
broke, and the words the gate quotes back. Everything below the next ``##``
heading has shipped and is never read.
"""

import re
import sys
from pathlib import Path

import check_changelog as GATE
import pytest

#: Line 1 titles the file and line 3 opens the section, so a section body starts on line 5.
OPENING = "# Changelog\n\n## [Unreleased]\n\n"

IN_SHAPE = "### Internal\n\n- **A gate holds the section's shape.** It makes no model call.\n"

#: The same body as ``IN_SHAPE`` with its bold lead struck, and nothing else changed.
LEAD_STRUCK = IN_SHAPE.replace("**", "")

NO_LEAD = "### Internal\n\n- A gate holds the section's shape, and opens with no bold clause.\n"

ADDRESSED = "### Internal\n\n- **A gate holds the shape.** It refuses your bullet before the judge reads it.\n"

#: Five words of lead and 80 more: ten past the cap, and the count the gate must print.
OVER_THE_CAP = "### Internal\n\n- **A gate holds the shape.** " + ("word " * 80) + "\n"

#: Five words of lead and 70 more, the cap exactly, behind a code span the cap must not price.
BEHIND_A_SPAN = "### Internal\n\n- **A gate holds the shape.** `one two three four five` " + ("word " * 70) + "\n"

#: Both prose rules broken on one bullet, to pin the order the findings print in.
UNLED_AND_ADDRESSED = "### Internal\n\n- A gate holds the shape, and refuses your bullet.\n"

TWICE = "### Added\n\n- **One thing lands.** With a reason.\n\n### Added\n\n- **A second thing lands.** Also.\n"

OUT_OF_ORDER = "### Fixed\n\n- **One thing holds.** With a reason.\n\n### Added\n\n- **A thing lands.** Also.\n"

NO_KIND = "### Notes\n\n- **One thing holds.** With a reason.\n"

#: A section body breaking the bold lead, the second person and the kind rules at once.
THREE_RULES_BROKEN = "### Notes\n\n- a released bullet addressing your reading of it\n"

#: That same body, byte for byte, shipped under a released heading.
RELEASED = "\n## [0.1.0]\n\n" + THREE_RULES_BROKEN

NO_LEAD_FINDING = "line 7: no bold lead clause, which a bullet opens with as `- **…**`"

ADDRESSED_FINDING = "line 7: 'your' addresses the reader — state the change impersonally"

TWO_PROBLEMS = "2 problem(s) under ## [Unreleased]. See CONTRIBUTING.md."
ONE_PROBLEM = "1 problem(s) under ## [Unreleased]. See CONTRIBUTING.md."


def changelog(tmp_path: Path, section: str, tail: str = "") -> Path:
    """Put one changelog in a throwaway tree, with the given section body and tail."""
    path = tmp_path / "CHANGELOG.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(OPENING + section + tail, encoding="utf-8")
    return path


def verdict(path: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, list[str]]:
    """The gate's exit code over ``path``, with every finding it printed under that path."""
    code = GATE.check(path)
    printed = capsys.readouterr().out.splitlines()
    return code, [line.removeprefix(f"{path}:") for line in printed if line.startswith(f"{path}:")]


def numbers(finding: str) -> list[int]:
    """Every number a finding names, in the order it names them: the line it opens on first."""
    return [int(found) for found in re.findall(r"\d+", finding)]


def flagged_lines(path: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, list[int]]:
    """The gate's exit code over ``path``, with the line each of its findings opens on."""
    code, findings = verdict(path, capsys)
    return code, [numbers(finding)[0] for finding in findings]


def ok_line(path: Path) -> str:
    """What the gate prints over a file that breaks no rule."""
    return f"[ok] {path} holds its shape under ## [Unreleased]\n"


# --- behavior 1: one bullet's shape -----------------------------------------


def test_a_bullet_in_shape_draws_no_finding_and_the_file_is_called_in_shape(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    led = flagged_lines(changelog(tmp_path / "led", IN_SHAPE), capsys)
    struck = flagged_lines(changelog(tmp_path / "struck", LEAD_STRUCK), capsys)
    assert (led, struck) == ((0, []), (1, [7]))


def test_a_bullet_opening_with_no_bold_lead_is_named_by_line_and_owed_lead(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert verdict(changelog(tmp_path, NO_LEAD), capsys) == (1, [NO_LEAD_FINDING])


def test_a_bullet_addressing_the_reader_is_named_by_line_and_the_word_it_used(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert flagged_lines(changelog(tmp_path, ADDRESSED), capsys) == (1, [7])


def test_a_bullet_past_the_word_cap_is_named_by_line_word_count_and_cap(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, findings = verdict(changelog(tmp_path, OVER_THE_CAP), capsys)
    assert (code, [numbers(finding)[:2] for finding in findings]) == (1, [[7, 85]])


def test_a_code_span_is_priced_at_no_words_so_a_bullet_at_the_cap_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert verdict(changelog(tmp_path, BEHIND_A_SPAN), capsys) == (0, [])


# --- behavior 2: one heading per kind, in order -----------------------------


def test_a_second_heading_of_one_kind_names_its_line_and_the_line_it_repeats(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, findings = verdict(changelog(tmp_path, TWICE), capsys)
    assert (code, [numbers(finding)[:2] for finding in findings]) == (1, [[9, 5]])


def test_a_kind_out_of_keep_a_changelog_order_names_its_line_and_the_order(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert flagged_lines(changelog(tmp_path, OUT_OF_ORDER), capsys) == (1, [9])


def test_a_heading_naming_no_kind_names_its_line_and_the_kinds_it_could_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert flagged_lines(changelog(tmp_path, NO_KIND), capsys) == (1, [5])


# --- behavior 3: a released section is history ------------------------------


def test_a_released_section_breaking_three_rules_draws_no_finding(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, lines = flagged_lines(changelog(tmp_path / "unreleased", THREE_RULES_BROKEN), capsys)
    shipped = flagged_lines(changelog(tmp_path / "released", IN_SHAPE, RELEASED), capsys)
    assert ((code, sorted(set(lines))), shipped) == ((1, [5, 7]), (0, []))


# --- behavior 4: how a refusal reads ----------------------------------------


def test_check_prints_a_line_per_finding_then_the_count_and_refuses(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = changelog(tmp_path, UNLED_AND_ADDRESSED)
    assert (GATE.check(path), capsys.readouterr().out) == (
        1,
        f"{path}:{NO_LEAD_FINDING}\n{path}:{ADDRESSED_FINDING}\n\n{TWO_PROBLEMS}\n",
    )


def test_main_refuses_for_the_one_path_in_argv_that_breaks_a_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    held = changelog(tmp_path / "held", IN_SHAPE)
    broken = changelog(tmp_path / "broken", NO_LEAD)
    monkeypatch.setattr(sys, "argv", ["check_changelog.py", str(held), str(broken)])
    assert (GATE.main(), capsys.readouterr().out) == (
        1,
        f"{ok_line(held)}{broken}:{NO_LEAD_FINDING}\n\n{ONE_PROBLEM}\n",
    )
