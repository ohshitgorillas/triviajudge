# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `triviajudge-archaeology`, a pattern gate over comments in `.py`, `.js` and `.css`
  files. Refuses ISO dates in prose, past-behavior narration, refactor archaeology,
  replacement narration, commit citations, process archaeology, and a past-tense verb
  sharing a sentence with a literal length. Takes `history-ok: <reason>`, reason required.
- `triviajudge-md`, a model judge over the markdown lines a change adds. Five input
  modes: staged files, `--head`, `--lines` for calibration, `--stop` for an agent
  harness, and a bare invocation.
- `triviajudge-comments`, the same judge over the comments and docstrings a change
  adds. A docstring is one candidate with its lines joined; a `#` comment is one
  candidate per line. The pattern gate screens first and the judge reads only what
  survives. Under `--stop` it runs the screen alone and makes no model call.
- A clean-line cache for the markdown judge, keyed by the hash of a line's stripped
  text, so a passed line stays passed wherever it moves. Capped at the newest 20000.
- `[tool.triviajudge]` configuration read from the repository being judged, or a
  `.triviajudge.toml` at its root: `md_skip`, `comment_skip`, `suffixes`, `excluded`,
  `cache_dir` and `model`. An absent table gives defaults; an unparseable one fails
  the gate; an empty key is honoured.
- A `.pre-commit-hooks.yaml` manifest carrying the three hook ids.
- Tests for the engine: diff line-numbering, the digest, the cache's read and write
  paths, the optional gate cache, and the root discovery on both sides of its boundary.

### Changed

- The repository root is found from the current working directory rather than by
  counting parents from the gate's own file, so an installed package judges the tree
  it is run in. A directory in no work tree is refused rather than inferred.
- `Gate.cache` is optional and last in the field list. A gate that does not judge at
  `Stop` never reaches the only call that writes a cache, so it carries none.
