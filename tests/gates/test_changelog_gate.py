"""The offline changelog gate: bullet shape and heading order under ``[Unreleased]``.

Four rules over the section as a whole — the word cap, the bold lead, the second
person, and one heading per kind in Keep a Changelog order. Everything below the
next ``##`` heading has shipped and is never read.
"""

from pathlib import Path

import check_changelog as GATE

OPENING = "# Changelog\n\n## [Unreleased]\n\n"

IN_SHAPE = "### Internal\n\n- **A gate holds the section's shape.** It makes no model call.\n"

NO_LEAD = "### Internal\n\n- A gate holds the section's shape, and opens with no bold clause.\n"

ADDRESSED = "### Internal\n\n- **A gate holds the shape.** It refuses your bullet before the judge reads it.\n"

OVER_THE_CAP = "### Internal\n\n- **A gate holds the shape.** " + ("word " * 80) + "\n"

TWICE = "### Added\n\n- **One thing lands.** With a reason.\n\n### Added\n\n- **A second thing lands.** Also.\n"

OUT_OF_ORDER = "### Fixed\n\n- **One thing holds.** With a reason.\n\n### Added\n\n- **A thing lands.** Also.\n"

NO_KIND = "### Notes\n\n- **One thing holds.** With a reason.\n"

SPANNED = "- **A gate.** `one two three` four"

RELEASED = "\n## [0.1.0]\n\n### Notes\n\n- a released bullet addressing your reading of it\n"


def changelog(tmp_path: Path, section: str, tail: str = "") -> Path:
    """Put one changelog in a throwaway tree, with the given section body and tail."""
    path = tmp_path / "CHANGELOG.md"
    path.write_text(OPENING + section + tail, encoding="utf-8")
    return path


# --- behavior 1: one bullet's shape -----------------------------------------


def test_a_bullet_in_shape_passes(tmp_path: Path) -> None:
    assert GATE.check(changelog(tmp_path, IN_SHAPE)) == 0


def test_a_bullet_opening_with_no_bold_lead_fails(tmp_path: Path) -> None:
    assert GATE.check(changelog(tmp_path, NO_LEAD)) == 1


def test_a_bullet_addressing_the_reader_fails(tmp_path: Path) -> None:
    assert GATE.check(changelog(tmp_path, ADDRESSED)) == 1


def test_a_bullet_past_the_word_cap_fails(tmp_path: Path) -> None:
    assert GATE.check(changelog(tmp_path, OVER_THE_CAP)) == 1


def test_a_code_span_costs_no_words() -> None:
    assert GATE.length(SPANNED) == 3


# --- behavior 2: one heading per kind, in order -----------------------------


def test_a_second_heading_of_one_kind_fails(tmp_path: Path) -> None:
    assert GATE.check(changelog(tmp_path, TWICE)) == 1


def test_a_kind_sitting_out_of_keep_a_changelog_order_fails(tmp_path: Path) -> None:
    assert GATE.check(changelog(tmp_path, OUT_OF_ORDER)) == 1


def test_a_heading_naming_no_kind_fails(tmp_path: Path) -> None:
    assert GATE.check(changelog(tmp_path, NO_KIND)) == 1


# --- behavior 3: a released section is history ------------------------------


def test_a_released_section_is_never_read(tmp_path: Path) -> None:
    assert GATE.check(changelog(tmp_path, IN_SHAPE, RELEASED)) == 0


def test_this_repository_holds_its_own_changelog_in_shape() -> None:
    assert GATE.check(GATE.ROOT / "CHANGELOG.md") == 0
