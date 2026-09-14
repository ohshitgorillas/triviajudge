"""The table a repository states about itself, and the three readings at its edges.

``config.read`` looks for ``[tool.triviajudge]`` in ``pyproject.toml`` first and
``.triviajudge.toml`` second, and a key the table leaves out keeps its built-in
default. A file that does not parse fails rather than falling back, because
defaults would judge a different file set than the repository asked for and say
nothing about it. A key nobody knows fails too, so a typo is not silence.

A list becomes the type the field holds: ``frozenset`` for the skip lists,
``tuple`` for the ordered ones.
"""

from pathlib import Path

import pytest

from triviajudge import config

A_TABLE = '[tool.triviajudge]\nmodel = "a-model"\nexcluded = ["tests/"]\nmd_skip = ["NOTES.md"]\n'

BARE_TABLE = 'model = "a-model"\n'


def written(tmp_path: Path, name: str, text: str) -> Path:
    """Put one settings file in a throwaway tree and answer with that tree."""
    (tmp_path / name).write_text(text, encoding="utf-8")
    return tmp_path


# --- behavior 1: a repository that says nothing gets the defaults ------------


def test_a_tree_stating_nothing_is_read_at_the_defaults(tmp_path: Path) -> None:
    assert config.read(tmp_path) == config.Settings()


def test_a_pyproject_carrying_no_table_is_read_at_the_defaults(tmp_path: Path) -> None:
    assert config.read(written(tmp_path, "pyproject.toml", '[project]\nname = "x"\n')) == config.Settings()


# --- behavior 2: each source is read, pyproject first ------------------------


def test_the_pyproject_table_is_read(tmp_path: Path) -> None:
    assert config.read(written(tmp_path, "pyproject.toml", A_TABLE)).model == "a-model"


def test_the_standalone_file_is_read_when_pyproject_holds_no_table(tmp_path: Path) -> None:
    written(tmp_path, "pyproject.toml", '[project]\nname = "x"\n')
    assert config.read(written(tmp_path, ".triviajudge.toml", BARE_TABLE)).model == "a-model"


def test_a_list_becomes_the_type_the_field_holds(tmp_path: Path) -> None:
    settings = config.read(written(tmp_path, "pyproject.toml", A_TABLE))
    assert (settings.md_skip, settings.excluded) == (frozenset({"NOTES.md"}), ("tests/",))


# --- behavior 3: an unreadable table fails rather than falling back ----------


def test_a_table_that_does_not_parse_refuses_to_judge_on_defaults(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="present but unreadable"):
        config.read(written(tmp_path, "pyproject.toml", "[tool.triviajudge\nmodel =\n"))


def test_a_key_nobody_knows_fails_rather_than_passing_in_silence(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="unknown triviajudge settings: mdel"):
        config.read(written(tmp_path, "pyproject.toml", '[tool.triviajudge]\nmdel = "a-model"\n'))
