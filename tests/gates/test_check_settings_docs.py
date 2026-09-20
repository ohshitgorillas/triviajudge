"""Behavior of the gate that pairs the settings surface with the prose documenting it.

The pairing runs both ways, and the documented block is also handed to the
reader function a judged repository's own table meets, so a block that does not
parse, a key that function refuses or a value it cannot coerce is a refusal here.

The gate reads this repository's own documentation on its pass path; the two
drift directions are driven by replacing the field set the documentation is
paired against. Each test reads the printed verdict rather than the exit code,
so a refusal that names the wrong setting or the wrong direction fails here.
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

#: The whole verdict this repository's own README earns, settings counted as the gate counts them.
README_OK = f"[ok] all {len(GATE.fields())} settings are documented in README.md\n"

#: What the gate says of a document carrying no block at all, after the document's own path.
NO_BLOCK = f"no fenced block carrying {TABLE} — the settings are undocumented"

#: The lead-in the gate prints before whatever ``config.read`` said in refusing the block.
REFUSED = "the documented block is one config.read refuses:"

#: What ``config.read`` says of each block it refuses; the unparseable one names a
#: temporary file of the gate's own making, so only the tail of that one is quoted.
UNPARSEABLE_SAID = "is present but unreadable, refusing to judge on defaults: Invalid value (at end of document)"
UNKNOWN_KEY_SAID = "unknown triviajudge settings: ghost_setting"
UNCOERCIBLE_SAID = "'int' object is not iterable"

#: The two drift directions, as the gate names the setting that drifted.
OMITTED = "ghost_setting: a Settings field SETTINGS.md does not document"
UNDECLARED = "md_skip: documented in SETTINGS.md, and Settings carries no such field"


def fenced(*blocks: str) -> str:
    """A document whose fenced code blocks hold each body in turn."""
    return "".join(f"```toml\n{body}\n```\n\n" for body in blocks)


def written(root: Path, text: str) -> Path:
    """A document at ``root`` carrying ``text``."""
    path = root / "SETTINGS.md"
    path.write_text(text, encoding="utf-8")
    return path


# --- behavior 1: this repository documents its own settings both ways ---------


def test_this_repository_documents_every_setting_it_carries(capsys: pytest.CaptureFixture[str]) -> None:
    GATE.check(GATE.README)
    assert capsys.readouterr().out == README_OK


# --- behavior 2: an undocumented surface is a refusal, not an empty pairing ---


def test_a_document_with_no_settings_block_is_refused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    document = written(tmp_path, NO_TABLE)
    GATE.check(document)
    assert capsys.readouterr().out == f"{document}: {NO_BLOCK}\n"


# --- behavior 3: the documented block is judged by the reader it instructs ----


def test_a_block_that_does_not_parse_is_refused_in_the_readers_words(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    GATE.check(written(tmp_path, fenced(UNPARSEABLE)))
    assert capsys.readouterr().out.endswith(f"{UNPARSEABLE_SAID}\n")


def test_a_block_naming_a_key_the_reader_refuses_names_that_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    document = written(tmp_path, fenced(UNKNOWN_KEY))
    GATE.check(document)
    assert capsys.readouterr().out == f"{document}: {REFUSED} {UNKNOWN_KEY_SAID}\n"


def test_a_block_whose_value_will_not_coerce_is_refused_in_the_readers_words(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    document = written(tmp_path, fenced(UNCOERCIBLE))
    GATE.check(document)
    assert capsys.readouterr().out == f"{document}: {REFUSED} {UNCOERCIBLE_SAID}\n"


def test_a_block_the_reader_accepts_names_the_settings_it_states(tmp_path: Path) -> None:
    assert GATE.documented(written(tmp_path, fenced(ONE_SETTING))) == {"md_skip"}


# --- behavior 4: the block carrying the table is the one that is read ---------


def test_a_fenced_block_without_the_table_is_passed_over() -> None:
    assert GATE.documented_block(fenced(OTHER_BLOCK, ONE_SETTING)) == ONE_SETTING


def test_a_document_with_no_fenced_block_has_none() -> None:
    assert GATE.documented_block(NO_TABLE) is None


# --- behavior 5: the pairing fails in both directions ------------------------


def test_a_setting_the_document_omits_is_named_as_undocumented(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    known = GATE.fields() | {"ghost_setting"}
    monkeypatch.setattr(GATE, "fields", lambda: known)
    GATE.check(written(tmp_path, fenced(ONE_SETTING)))
    assert f"{OMITTED}\n" in capsys.readouterr().out


def test_a_documented_key_no_field_carries_is_named_as_undeclared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(GATE, "fields", set)
    GATE.check(written(tmp_path, fenced(ONE_SETTING)))
    assert f"{UNDECLARED}\n" in capsys.readouterr().out


# --- behavior 6: argv names the document, and its absence means this repository ---


def test_the_document_argv_names_is_the_one_judged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    document = written(tmp_path, NO_TABLE)
    monkeypatch.setattr(sys, "argv", ["check_settings_docs.py", str(document)])
    GATE.main()
    assert capsys.readouterr().out == f"{document}: {NO_BLOCK}\n"


def test_an_empty_argv_judges_this_repositorys_own_readme(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["check_settings_docs.py"])
    GATE.main()
    assert capsys.readouterr().out == README_OK
