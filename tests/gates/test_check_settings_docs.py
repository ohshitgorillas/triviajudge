"""Behavior of the gate that pairs the settings surface with the prose documenting it.

The pairing runs both ways, and the documented block is also handed to the
reader function a judged repository's own table meets, so a block that does not
parse, a key that function refuses or a value it cannot coerce is a refusal here.

The gate reads this repository's own documentation on its pass path; the two
drift directions are driven by replacing the field set the documentation is
paired against.
"""

import sys
from pathlib import Path

import check_settings_docs as GATE
import pytest

TABLE = "[tool.triviajudge]"

#: A documented block naming one real setting: legal TOML, and a pairing that omits the rest.
ONE_SETTING = f'{TABLE}\nmd_skip = ["CHANGELOG.md"]'

#: A block that never closes its list, so the reader cannot parse it at all.
UNPARSEABLE = f"{TABLE}\nmd_skip = ["

#: A block naming a key the reader refuses outright.
UNKNOWN_KEY = f"{TABLE}\nghost_setting = 1"

#: A block whose value the reader cannot coerce into the field's type.
UNCOERCIBLE = f"{TABLE}\nmd_skip = 5"

#: A fenced block carrying no settings table at all.
OTHER_BLOCK = "make check\nmake trivia"

NO_TABLE = "# Settings\n\nthe table is documented somewhere else entirely\n"


def fenced(*blocks: str) -> str:
    """A document whose fenced code blocks hold each body in turn."""
    return "".join(f"```toml\n{body}\n```\n\n" for body in blocks)


def written(root: Path, text: str) -> Path:
    """A document at ``root`` carrying ``text``."""
    path = root / "SETTINGS.md"
    path.write_text(text, encoding="utf-8")
    return path


# --- behavior 1: this repository documents its own settings both ways ---------


def test_this_repository_documents_every_setting_it_carries() -> None:
    assert GATE.check(GATE.README) == 0


# --- behavior 2: an undocumented surface is a refusal, not an empty pairing ---


def test_a_document_with_no_settings_block_is_refused(tmp_path: Path) -> None:
    assert GATE.check(written(tmp_path, NO_TABLE)) == 1


def test_a_document_with_no_settings_block_documents_nothing(tmp_path: Path) -> None:
    assert GATE.documented(written(tmp_path, NO_TABLE)) == set()


# --- behavior 3: the documented block is judged by the reader it instructs ----


@pytest.mark.parametrize("body", [UNPARSEABLE, UNKNOWN_KEY, UNCOERCIBLE])
def test_a_block_the_reader_refuses_is_refused_here(tmp_path: Path, body: str) -> None:
    assert GATE.check(written(tmp_path, fenced(body))) == 1


def test_a_block_the_reader_accepts_names_the_settings_it_states(tmp_path: Path) -> None:
    assert GATE.documented(written(tmp_path, fenced(ONE_SETTING))) == {"md_skip"}


# --- behavior 4: the block carrying the table is the one that is read ---------


def test_a_fenced_block_without_the_table_is_passed_over() -> None:
    assert GATE.documented_block(fenced(OTHER_BLOCK, ONE_SETTING)) == ONE_SETTING


def test_a_document_with_no_fenced_block_has_none() -> None:
    assert GATE.documented_block(NO_TABLE) is None


# --- behavior 5: the pairing fails in both directions ------------------------


def test_a_setting_the_document_omits_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    known = GATE.fields() | {"ghost_setting"}
    monkeypatch.setattr(GATE, "fields", lambda: known)
    assert GATE.check(written(tmp_path, fenced(ONE_SETTING))) == 1


def test_a_documented_key_no_field_carries_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(GATE, "fields", set)
    assert GATE.check(written(tmp_path, fenced(ONE_SETTING))) == 1


# --- behavior 6: argv names the document, and its absence means this repository ---


@pytest.mark.parametrize("named", [True, False])
def test_the_document_under_test_is_the_one_argv_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, named: bool
) -> None:
    document = written(tmp_path, NO_TABLE)
    monkeypatch.setattr(sys, "argv", ["check_settings_docs.py", *([str(document)] if named else [])])
    assert GATE.main() == (1 if named else 0)
